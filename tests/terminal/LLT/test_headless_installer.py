# @test T-LLT-012
# @requirements LLR-TERM-INSTALL-003, LLR-TERM-INSTALL-004, LLR-TERM-INSTALL-008
# @environment portable
# @plan Use a fake deployment backend and payload; assert explicit consent, preflight-before-install ordering, Argon defaults, failed completion reporting and GUI-free dispatch.
# @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

"""Headless installation must retain preflight, consent and failure reporting."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str((Path(__file__).resolve().parents[3] / 'build_tools') / 'windows_installer'))
READY = importlib.util.find_spec('paramiko') is not None
if READY:
    import cli
    import entrypoint


@unittest.skipUnless(READY, 'Installer dependencies required')
class HeadlessInstallerTests(unittest.TestCase):
    def invoke(self, options, *, check_error=None, install_error=None, payload_error=None):
        with tempfile.TemporaryDirectory() as folder:
            log = Path(folder) / 'run.log'
            with patch.object(cli, 'Deployment') as deployment, patch.object(cli, 'verify_payload') as verify:
                target = deployment.return_value
                target.check.return_value = {'model': 'Pi 4', 'ssh_address': '192.0.2.4'}
                target.check.side_effect = check_error
                target.install.side_effect = install_error
                verify.side_effect = payload_error
                with patch.object(cli.sys, 'stdout', None), patch.object(cli.sys, 'stderr', None):
                    result = cli.main(['--headless', '--log', str(log), *options])
                return result, log.read_text(), deployment, verify

    def test_confirmation_is_required_before_connecting(self):
        result, log, deployment, _ = self.invoke([])
        self.assertEqual(result, 2)
        self.assertIn('requires --yes', log)
        deployment.assert_not_called()

    def test_read_only_check_does_not_install(self):
        result, log, deployment, _ = self.invoke(['--check-only'])
        self.assertEqual(result, 0)
        self.assertIn('CHECK PASSED', log)
        deployment.return_value.install.assert_not_called()
        deployment.return_value.close.assert_called_once()

    def test_install_checks_first_and_always_enables_argon(self):
        with patch.object(cli, 'resources', return_value=Path('/package')):
            result, log, deployment, verify = self.invoke(['--host', '192.0.2.4', '--yes'])
        self.assertEqual(result, 0)
        self.assertIn('SUCCESS', log)
        verify.assert_called_once_with(Path('/package/ZmalaCall-Terminal-rpi.tar.gz'))
        self.assertEqual(deployment.call_args.args[0], '192.0.2.4')
        self.assertEqual([c[0] for c in deployment.return_value.mock_calls], ['check', 'install', 'close'])
        deployment.return_value.install.assert_called_once_with(Path('/package/ZmalaCall-Terminal-rpi.tar.gz'), True)

    def test_bad_payload_does_not_connect(self):
        result, log, deployment, _ = self.invoke(['--yes'], payload_error=RuntimeError('damaged package'))
        self.assertEqual(result, 1)
        self.assertIn('damaged package', log)
        deployment.assert_not_called()

    def test_failed_preflight_does_not_install(self):
        result, log, deployment, _ = self.invoke(['--yes'], check_error=RuntimeError('wrong OS'))
        self.assertEqual(result, 1)
        self.assertIn('wrong OS', log)
        deployment.return_value.install.assert_not_called()
        deployment.return_value.close.assert_called_once()

    def test_failed_post_reboot_check_is_not_success(self):
        result, log, deployment, _ = self.invoke(['--yes'], install_error=RuntimeError('reboot check failed'))
        self.assertEqual(result, 1)
        self.assertIn('reboot check failed', log)
        self.assertNotIn('SUCCESS', log)
        deployment.return_value.close.assert_called_once()

    def test_smoke_test_never_connects(self):
        with tempfile.TemporaryDirectory() as folder:
            report = Path(folder) / 'report.txt'
            result, _, deployment, _ = self.invoke(['--smoke-test', str(report)])
            self.assertEqual(result, 0)
            self.assertIn('Headless mode', report.read_text())
            deployment.assert_not_called()

    def test_dispatch_does_not_import_gui(self):
        with patch.dict(sys.modules, {'app': None}), patch.object(sys, 'argv', ['setup.exe', '--headless']), \
                patch.object(cli, 'main', return_value=2) as run:
            self.assertEqual(entrypoint.main(), 2)
            run.assert_called_once()
