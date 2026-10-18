# @test S-LLT-012
# @requirements LLR-SRV-INSTALL-003, LLR-SRV-INSTALL-004, LLR-SRV-INSTALL-005, LLR-SRV-INSTALL-006, LLR-SRV-INSTALL-007, LLR-SRV-INSTALL-010
# @environment portable
# @plan Use fake SSH targets and temporary migration/release archives; assert supported wired Pi preflight, consent, pinned reconnect, failed-recheck abort and exact private-state/payload boundaries.
# @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

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

    def test_migration_keeps_current_state_not_logs_and_backups(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'server.json').write_text(json.dumps({'users': {'alice': {'password': 'private'}}, 'profiles': {}}))
            (root/'admin-password.json').write_text('{"password_hash":"private"}')
            (root/'server.log').write_text('private log')
            (root/'server-before-reset.json').write_text('old private data')
            (root/'photos').mkdir()
            (root/'photos/a.png').write_bytes(b'picture')
            output = root/'migration.tar.gz'
            migration_archive(root, output)
            with tarfile.open(output) as archive:
                self.assertEqual(set(archive.getnames()), {'server.json', 'admin-password.json', 'photos/a.png'})


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
                for name in ('docs/general.md', 'docs/server.md', 'docs/terminal.md',
                             'build_tools/assets/installation-connections.png',
                             'zmala_terminal/common/assets/presenter-pairing.png'):
                    self.assertIn(name, names)
                self.assertFalse(any('/data/' in p or '/node_modules/' in p or 'password.txt' in p for p in names))
                self.assertNotIn(b'\r\n', archive.extractfile('install.sh').read())


if __name__ == '__main__':
    unittest.main()
