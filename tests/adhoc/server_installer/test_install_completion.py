# Installer regression tests; outside the Pi runtime requirements baseline.
"""Server installation completion and recovery policy at the SSH boundary."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
HAS_PARAMIKO = importlib.util.find_spec('paramiko') is not None
if HAS_PARAMIKO:
    from build_tools.server_installer import backend
    from tests.adhoc.server_installer.test_server_installer import target


class Clock:
    def __init__(self):
        self.now = 0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


@unittest.skipUnless(HAS_PARAMIKO, 'Install SSH build dependencies')
class CompletionTests(unittest.TestCase):
    def test_invalid_hardware_address_and_migration_objects_are_rejected(self):
        for change, message in (({'model': 'Raspberry Pi 5'}, 'Model B'),
                                ({'ssh_address': 'not-an-address'}, 'Ethernet')):
            with self.subTest(change=change), self.assertRaisesRegex(backend.InstallError, message):
                backend.validate_target(dict(target(), **change))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); output = root / 'migration.tgz'
            (root / 'server.json').write_text('{"users":[],"profiles":{}}', encoding='utf-8')
            with self.assertRaisesRegex(backend.InstallError, 'valid server data'):
                backend.migration_archive(root, output)
            (root / 'server.json').write_text('{"users":{},"profiles":{}}', encoding='utf-8')
            (root / 'photos').mkdir(); (root / 'photos' / 'nested').mkdir()
            with self.assertRaisesRegex(backend.InstallError, 'link or directory'):
                backend.migration_archive(root, output)
            (root / 'photos' / 'nested').rmdir()
            with (root / 'photos' / 'large.png').open('wb') as image:
                image.truncate(32*1024*1024 + 1)
            with self.assertRaisesRegex(backend.InstallError, 'supported size'):
                backend.migration_archive(root, output)

    def deployment(self):
        deployment = backend.Deployment('zmalaserver.local', emit=MagicMock())
        deployment.connect = MagicMock()
        deployment.close = MagicMock()
        deployment.command = MagicMock(return_value='')
        deployment.probe = MagicMock(return_value=dict(target(), boot_id='new'))
        deployment.wired_address = '192.168.1.42'
        return deployment

    def test_probe_reads_packaged_script_and_targets_server(self):
        deployment = backend.Deployment('zmalaserver.local')
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'remote_probe.py').write_text("Path('/opt/zmalacall/current')", encoding='utf-8')
            with patch.object(sys, 'frozen', True, create=True), patch.object(sys, '_MEIPASS', directory, create=True), patch.object(deployment, 'command', return_value='{"boot_id":"x"}') as command:
                self.assertEqual(deployment.probe(), {'boot_id': 'x'})
                command.assert_called_once_with('python3 -', "Path('/opt/zmalacall-server/current')")

    def test_requires_preflight_before_any_connection(self):
        deployment = self.deployment()
        with self.assertRaisesRegex(backend.InstallError, 'Check the Pi'):
            deployment.install('unused')
        deployment.connect.assert_not_called()

    def test_private_migration_and_checks_precede_success(self):
        deployment = self.deployment()
        deployment.info = target()
        deployment.client = MagicMock()
        sftp = deployment.client.open_sftp.return_value.__enter__.return_value
        deployment.monitor = MagicMock()
        deployment.verify_server_reboot = MagicMock()
        events = []

        def command(text, *args, **kwargs):
            events.append(text)
            if text.startswith('systemctl reboot'):
                raise EOFError('SSH closes on reboot')
            return ''

        deployment.command.side_effect = command
        deployment.monitor.side_effect = lambda *args: events.append('monitor-complete')
        deployment.verify_server_reboot.side_effect = lambda old: events.append('verified-' + old)
        with tempfile.TemporaryDirectory() as directory, patch.object(backend, 'verify_payload', return_value='trusted-digest'):
            Path(directory, 'server.json').write_text(json.dumps({'users': {}, 'profiles': {}}), encoding='utf-8')
            deployment.install('package.tar.gz', directory)
        remote = sftp.put.call_args_list[0].args[1].removesuffix('/server.tar.gz')
        self.assertEqual(events[0], 'mkdir -m 700 ' + remote)
        self.assertEqual(sftp.put.call_count, 2)
        self.assertEqual(sftp.put.call_args_list[1].args[1], remote + '/migration.tar.gz')
        sftp.chmod.assert_any_call(remote + '/migration.tar.gz', 0o600)
        sftp.chmod.assert_any_call(remote + '/progress.log', 0o600)
        checksum = deployment.command.call_args_list[1].args[1]
        self.assertIn('trusted-digest', checksum)
        self.assertIn("filter='data'", checksum)
        self.assertTrue(events[2].startswith('systemd-run'))
        self.assertIn('--data-archive', events[2])
        self.assertEqual(events[3:5], ['monitor-complete', 'rm -- ' + remote + '/migration.tar.gz'])
        self.assertEqual(events[-1], 'verified-new')
        deployment.close.assert_called_once()
        self.assertIn('SUCCESS.', deployment.emit.call_args.args[0])

    def test_failed_install_job_does_not_reboot_or_report_success(self):
        deployment = self.deployment()
        deployment.info = target()
        deployment.client = MagicMock()
        deployment.monitor = MagicMock(side_effect=backend.InstallError('dependency install failed; progress.log'))
        deployment.verify_server_reboot = MagicMock()
        with patch.object(backend, 'verify_payload', return_value='digest'), self.assertRaisesRegex(backend.InstallError, 'progress.log'):
            deployment.install('package.tar.gz')
        self.assertFalse(any('reboot' in call.args[0] for call in deployment.command.call_args_list))
        deployment.verify_server_reboot.assert_not_called()
        self.assertFalse(any('SUCCESS.' in call.args[0] for call in deployment.emit.call_args_list))

    def test_boot_change_pid_churn_and_transport_loss_delay_readiness(self):
        deployment = self.deployment()
        clock = Clock()
        probes = iter(['old', 'new', 'new', 'new', 'new', 'new'])
        deployment.probe.side_effect = lambda: {'boot_id': next(probes, 'new')}
        pids = iter(['0', '123', '124', OSError('network'), '124'])
        checks = []

        def command(text, **kwargs):
            if text.startswith('systemctl show'):
                value = next(pids, '124')
                if isinstance(value, Exception):
                    raise value
                return value
            checks.append((text, clock.now, kwargs))
            return 'healthy'

        deployment.command.side_effect = command
        with patch.object(backend, 'time', clock):
            deployment.verify_server_reboot('old')
        # PID 124 restarts its stability interval at t=18 after transport loss.
        self.assertEqual([check[1] for check in checks], [30, 30])
        self.assertIn('check-server.py', checks[0][0])
        self.assertEqual(checks[1], ('nft list table inet zmala_ssh', 30, {'sudo': True}))

    def test_readiness_and_firewall_failure_propagate(self):
        for failure in ('check-server.py', 'nft list'):
            with self.subTest(failure=failure):
                deployment = self.deployment()
                clock = Clock()

                def command(text, **kwargs):
                    if failure in text:
                        raise backend.InstallError('failed ' + failure)
                    return '123'

                deployment.command.side_effect = command
                with patch.object(backend, 'time', clock), self.assertRaisesRegex(backend.InstallError, failure):
                    deployment.verify_server_reboot('old')
                self.assertEqual(clock.now, 15)

    def test_unchanged_boot_or_missing_process_times_out(self):
        for boot, pid in (('old', '123'), ('new', '0')):
            with self.subTest(boot=boot, pid=pid):
                deployment = self.deployment()
                deployment.probe.return_value = {'boot_id': boot}
                deployment.command.return_value = pid
                clock = Clock()
                with patch.object(backend, 'time', clock), self.assertRaisesRegex(backend.InstallError, 'Keep Ethernet connected and inspect the log'):
                    deployment.verify_server_reboot('old')
                self.assertEqual(clock.now, 300)
                self.assertFalse(any('check-server.py' in call.args[0] for call in deployment.command.call_args_list))


if __name__ == '__main__':
    unittest.main()
