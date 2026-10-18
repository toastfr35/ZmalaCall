# @test T-LLT-043
# @requirements TLLR113, TLLR115, TLLR119
# @environment portable
# @plan Use a fake SSH deployment backend and corrupt payloads; assert supported wired Pi preflight, pinned Ethernet reconnect, mandatory checks and failure reporting without premature reboot.
# @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

"""Deployment validation must fail before any upload or installation."""
import copy
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'build_tools/windows_installer'))
HAS_PARAMIKO = importlib.util.find_spec('paramiko') is not None
if HAS_PARAMIKO:
    import backend


def target():
    return {'hostname': 'zmala', 'model': 'Raspberry Pi 4 Model B Rev 1.5',
            'pi_image': 'Raspberry Pi reference 2026-10-06',
            'os': {'ID': 'debian', 'VERSION_CODENAME': 'trixie', 'PRETTY_NAME': 'Debian 13'},
            'architecture': 'arm64', 'machine': 'aarch64', 'boot_mounted': True,
            'ethernet_up': True, 'ssh_address': '192.168.1.93',
            'ethernet_addresses': ['192.168.1.93'], 'free_var': 10 * 1024**3,
            'free_boot': 256 * 1024**2, 'installed': False, 'boot_id': 'initial-boot'}


@unittest.skipUnless(HAS_PARAMIKO, 'Install Windows installer requirements to run SSH deployment tests')
class WindowsInstallerTests(unittest.TestCase):
    def test_supported_target(self):
        backend.validate_target(target())

    def test_reconnect_uses_verified_ethernet_address_not_mdns(self):
        deployment = backend.Deployment('zmala.local')
        deployment.key = 'SHA256:test'
        with patch.object(deployment, 'connect'), patch.object(deployment, 'probe', return_value=target()), \
                patch.object(deployment, 'command'):
            deployment.check()
        key = Mock()
        key.asbytes.return_value = b'key'
        with patch.object(backend.paramiko, 'SSHClient') as client:
            client.return_value.get_transport.return_value.get_remote_server_key.return_value = key
            deployment.connect()
        self.assertEqual(client.return_value.connect.call_args.args[0], '192.168.1.93')

    def test_rejects_wrong_os_arch_board_hostname_and_network(self):
        changes = [
            {'os': {'ID': 'debian', 'VERSION_CODENAME': 'bookworm'}},
            {'architecture': 'armhf'}, {'machine': 'x86_64'}, {'pi_image': ''},
            {'model': 'Raspberry Pi 5 Model B'}, {'hostname': 'pi3'},
            {'ssh_address': '192.168.1.94'}, {'ethernet_up': False},
            {'boot_mounted': False}, {'free_var': 1024}, {'free_boot': 1024},
        ]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(backend.InstallError):
                backend.validate_target({**target(), **change})

    def test_supports_wired_ipv6(self):
        backend.validate_target({**target(), 'ssh_address': 'fd28::42', 'ethernet_addresses': ['fd28::42']})

    def test_recheck_stops_before_upload_if_target_changed(self):
        deployment = backend.Deployment('zmala.local')
        deployment.info = target()
        with patch.object(deployment, 'connect'), patch.object(deployment, 'probe',
                return_value={**target(), 'model': 'Other computer'}), patch.object(deployment, 'command') as command:
            with self.assertRaises(backend.InstallError):
                deployment.install(Path('unused.tar.gz'))
            command.assert_not_called()

    def test_install_requires_preflight(self):
        deployment = backend.Deployment('zmala.local')
        with patch.object(deployment, 'connect') as connect, self.assertRaises(backend.InstallError):
            deployment.install(Path('unused.tar.gz'))
        connect.assert_not_called()

    def test_payload_corruption_prevents_install(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / 'terminal.tar.gz'
            archive.write_bytes(b'damaged')
            archive.with_name(archive.name + '.sha256').write_text('0' * 64 + '  terminal.tar.gz\n')
            with self.assertRaises(backend.InstallError):
                backend.verify_payload(archive)

    def test_changed_host_key_rejected_on_reconnection(self):
        key = Mock()
        key.asbytes.return_value = b'first key'
        policy = backend.TargetKeyPolicy(backend.fingerprint(key))
        policy.missing_host_key(None, 'zmala', key)
        changed = copy.copy(key)
        changed.asbytes = Mock(return_value=b'other key')
        with self.assertRaises(backend.InstallError):
            policy.missing_host_key(None, 'zmala', changed)

    def test_monitor_reports_failure_without_rebooting(self):
        deployment = backend.Deployment('zmala.local')
        deployment.client = Mock()
        # Use a real in-memory stream for the remote output context manager.
        import io
        from unittest.mock import MagicMock
        session = MagicMock()
        session.open.side_effect = lambda *args: io.BytesIO(b'FAILED during: dependencies\n')
        deployment.client.open_sftp = MagicMock()
        deployment.client.open_sftp.return_value.__enter__.return_value = session
        with patch.object(deployment, 'command', return_value='ActiveState=failed\nResult=exit-code\nExecMainStatus=23'):
            with self.assertRaises(backend.InstallError):
                deployment.monitor('unit', '/progress.log')


if __name__ == '__main__':
    unittest.main()
