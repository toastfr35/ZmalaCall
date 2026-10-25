# Installer regression tests; outside the Pi runtime requirements baseline.
"""Server target validation, migration boundaries and clean release contents."""
import importlib.util
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
HAS_PARAMIKO = importlib.util.find_spec('paramiko') is not None
if HAS_PARAMIKO:
    from build_tools.server_installer.backend import Deployment, InstallError, migration_archive, validate_target


def target():
    return {'hostname': 'zmalaserver', 'model': 'Raspberry Pi 4 Model B Rev 1.5',
            'pi_image': 'Raspberry Pi reference 2026', 'os': {'ID': 'debian', 'VERSION_CODENAME': 'trixie'},
            'architecture': 'arm64', 'machine': 'aarch64', 'boot_mounted': True,
            'ethernet_up': True, 'ssh_address': '192.168.1.42', 'ethernet_addresses': ['192.168.1.42'],
            'free_var': 4*1024**3}


@unittest.skipUnless(HAS_PARAMIKO, 'Install SSH build dependencies')
class ServerInstallerTests(unittest.TestCase):
    def test_wired_pi3_and_pi4(self):
        validate_target(target())
        validate_target(dict(target(), model='Raspberry Pi 3 Model B Rev 1.2'))

    def test_wifi_wrong_os_architecture_hostname_and_storage_rejected(self):
        for change in ({'ethernet_up': False}, {'ssh_address': '192.168.1.43'}, {'hostname': 'zmala'},
                       {'architecture': 'armhf'}, {'os': {'ID': 'debian', 'VERSION_CODENAME': 'bookworm'}},
                       {'free_var': 1}, {'pi_image': ''}):
            with self.subTest(change=change), self.assertRaises(InstallError):
                validate_target(dict(target(), **change))

    def test_failed_recheck_never_uploads(self):
        deployment = Deployment('zmalaserver.local')
        deployment.info = target()
        with patch.object(deployment, 'connect'), patch.object(deployment, 'probe', return_value=dict(target(), ethernet_up=False)), patch.object(deployment, 'command') as command:
            with self.assertRaises(InstallError):
                deployment.install('unused')
            command.assert_not_called()

    def test_check_moves_from_wifi_to_observed_wired_ip_with_pinned_key(self):
        deployment = Deployment('zmalaserver.local')
        deployment.key = 'SHA256:already-observed'
        wifi = dict(target(), ssh_address='192.168.1.43')
        with patch.object(deployment, 'connect') as connect, patch.object(deployment, 'probe', side_effect=[wifi, target()]), patch.object(deployment, 'command'):
            deployment.check()
        self.assertEqual(connect.call_count, 2)
        self.assertEqual(deployment.wired_address, '192.168.1.42')
        self.assertEqual(deployment.key, 'SHA256:already-observed')

    def test_headless_requires_confirmation_without_contacting_pi(self):
        from build_tools.server_installer import cli
        with tempfile.TemporaryDirectory() as temporary, patch.object(cli, 'Deployment') as deployment:
            code = cli.main(['--headless', '--log', str(Path(temporary)/'test.log')])
            self.assertEqual(code, 2)
            deployment.assert_not_called()

    def test_headless_check_install_smoke_failure_and_dispatch(self):
        from build_tools.server_installer import cli, entrypoint, app
        with tempfile.TemporaryDirectory() as temporary, patch.object(cli, 'Deployment') as deployment, \
                patch.object(cli, 'verify_payload') as verify, patch.object(cli, 'resources', return_value=Path(temporary)), \
                patch.object(sys, 'stdout', None):
            base = ['--headless', '--log', str(Path(temporary)/'test.log')]
            self.assertEqual(cli.main(base+['--check-only']), 0)
            deployment.return_value.check.assert_called_once()
            deployment.return_value.install.assert_not_called()
            deployment.return_value.close.assert_called_once()
            deployment.reset_mock()
            self.assertEqual(cli.main(base+['--yes', '--host', 'unit.local', '--data-dir', temporary]), 0)
            self.assertEqual(deployment.call_args.args[0], 'unit.local')
            deployment.return_value.install.assert_called_once_with(Path(temporary)/'ZmalaCall-Server-rpi.tar.gz', Path(temporary))
            deployment.reset_mock()
            smoke = Path(temporary)/'smoke.txt'
            self.assertEqual(cli.main(base+['--smoke-test', str(smoke)]), 0)
            self.assertIn('checksum verified', smoke.read_text())
            deployment.assert_not_called()
            self.assertEqual(cli.main(base+['--smoke-test', str(smoke), '--yes']), 2)
            verify.side_effect = ValueError('bad package')
            self.assertEqual(cli.main(base+['--yes']), 1)
            self.assertIn('bad package', (Path(temporary)/'test.log').read_text())
            deployment.assert_not_called()
            verify.side_effect = None
            deployment.return_value.check.side_effect = RuntimeError('offline')
            self.assertEqual(cli.main(base+['--yes']), 1)
            deployment.return_value.close.assert_called_once()
        with patch.object(sys, 'argv', ['installer', '--headless']), patch.object(cli, 'main', return_value=7) as headless, \
                patch.object(app, 'main', return_value=8) as gui:
            self.assertEqual(entrypoint.main(), 7)
            sys.argv = ['installer']
            self.assertEqual(entrypoint.main(), 8)
            headless.assert_called_once_with()
            gui.assert_called_once_with()

    def test_bundle_build_includes_checksums_probe_and_icon_and_stops_on_failure(self):
        from build_tools.server_installer import build
        with tempfile.TemporaryDirectory() as temporary, patch.object(build, 'ROOT', Path(temporary)), \
                patch.object(build.sys, 'platform', 'win32'), patch.object(build.subprocess, 'run') as run:
            build.main()
            self.assertEqual(run.call_count, 2)
            first, second = [call.args[0] for call in run.call_args_list]
            self.assertTrue(first[-1].endswith('package-server.py'))
            self.assertIn('--onefile', second)
            self.assertIn('--windowed', second)
            self.assertEqual(second[second.index('--name')+1], 'ZmalaServer-Pi4-setup')
            self.assertEqual(sum(argument == '--add-data' for argument in second), 4)
            self.assertTrue(any('tar.gz.sha256' in argument for argument in second))
            self.assertTrue(any('remote_probe.py' in argument for argument in second))
            self.assertTrue(all(call.kwargs['check'] for call in run.call_args_list))
            run.reset_mock()
            run.side_effect = RuntimeError('package failed')
            with self.assertRaisesRegex(RuntimeError, 'package failed'):
                build.main()
            self.assertEqual(run.call_count, 1)
        with patch.object(build.sys, 'platform', 'linux'), patch.object(build.subprocess, 'run') as run:
            with self.assertRaises(SystemExit):
                build.main()
            run.assert_not_called()

    def test_migration_keeps_current_state_not_logs_and_backups(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            identity = 'a' * 64
            (root/'server.json').write_text(json.dumps({'users': {'alice': {'password': 'private'}}, 'profiles': {}, 'ringtones': {identity: {'name': 'Private sound', 'bytes': 4}}}))
            (root/'admin-password.json').write_text('{"password_hash":"private"}')
            (root/'server.log').write_text('private log')
            (root/'server-before-reset.json').write_text('old private data')
            (root/'photos').mkdir()
            (root/'photos/a.png').write_bytes(b'picture')
            (root/'ringtones').mkdir()
            (root/'ringtones'/(identity+'.wav')).write_bytes(b'tone')
            (root/'ringtones'/('b'*64+'.wav')).write_bytes(b'obsolete')
            output = root/'migration.tar.gz'
            migration_archive(root, output)
            with tarfile.open(output) as archive:
                self.assertEqual(set(archive.getnames()), {'server.json', 'admin-password.json', 'photos/a.png', 'ringtones/'+identity+'.wav'})


class ServerPackageTests(unittest.TestCase):
    def test_release_excludes_private_state_and_includes_runtime(self):
        spec = importlib.util.spec_from_file_location('package_server', ROOT/'build_tools/linux/package-server.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temporary:
            output = module.package(Path(temporary)/'server.tar.gz')
            with tarfile.open(output) as archive:
                names = archive.getnames()
                self.assertIn('zmala_server/vendor/sip/sip.js', names)
                self.assertIn('build_tools/linux/server-ssh.py', names)
                self.assertIn('zmala_terminal/common/shared/terminal-languages.json', names)
                self.assertEqual([p for p in names if p.endswith('.wav')], ['zmala_terminal/common/assets/gentle-chime.wav'])
                for name in ('docs/general.md', 'docs/server.md', 'docs/terminal.md',
                             'build_tools/assets/installation-connections.png',
                             'zmala_terminal/common/assets/presenter-pairing.png'):
                    self.assertIn(name, names)
                self.assertFalse(any('/data/' in p or '/node_modules/' in p or 'password.txt' in p for p in names))
                self.assertNotIn(b'\r\n', archive.extractfile('install.sh').read())


if __name__ == '__main__':
    unittest.main()
