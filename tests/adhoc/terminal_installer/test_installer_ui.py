# Installer regression tests; outside the Pi runtime requirements baseline.
import importlib
import contextlib
import io
import sys
import unittest
from unittest.mock import Mock, patch
from build_tools.windows_installer import backend
from tests.support.installer_gui import InstallerUIContract

with patch.dict(sys.modules, {'backend': backend}):
    app = importlib.import_module('build_tools.windows_installer.app')


class TerminalInstallerUITests(InstallerUIContract, unittest.TestCase):
    module = app

    def test_update_preserves_enrollment_and_installs_argon_automatically(self):
        self.app.target = self.target; self.target.info['installed'] = True
        self.dialogs.askokcancel.return_value = True
        with patch.object(app.threading, 'Thread', side_effect=self.run_worker): self.app.confirm()
        self.assertIn('Update ZmalaCall', self.dialogs.askokcancel.call_args.args[1])
        self.assertIn('enrollment is preserved', self.dialogs.askokcancel.call_args.args[1])
        self.target.install.assert_called_once_with(self.app.archive, True)
        with patch.object(self.app.details, 'deiconify') as show, patch.object(self.app.details, 'lift') as lift:
            self.app.show_details(); show.assert_called_once(); lift.assert_called_once()

    def test_entrypoint_smoke_and_read_only_ssh_cleanup(self):
        output=self.directory/'smoke.txt'; window=Mock(); target=Mock()
        with patch.object(app,'Installer',return_value=window),patch.object(app,'verify_payload') as verify,patch.object(app,'Deployment',return_value=target),patch('sys.argv',['setup','--smoke-test',str(output),'--smoke-host','example.test']):
            app.main()
        verify.assert_called_once_with(window.archive); target.check.assert_called_once(); target.close.assert_called_once(); target.install.assert_not_called()
        self.assertIn('preflight checks passed',output.read_text()); window.after.assert_called_once_with(200,window.close); window.mainloop.assert_called_once()
        window.reset_mock()
        with patch.object(app,'Installer',return_value=window),patch('sys.argv',['setup']): app.main()
        window.mainloop.assert_called_once(); window.after.assert_not_called()

    def test_smoke_failure_records_diagnostics_closes_and_propagates(self):
        output=self.directory/'failure.txt'; window=Mock(); target=Mock(); target.check.side_effect=RuntimeError('wrong OS')
        with patch.object(app,'Installer',return_value=window),patch.object(app,'verify_payload'),patch.object(app,'Deployment',return_value=target),patch('sys.argv',['setup','--smoke-test',str(output),'--smoke-host','example.test']):
            with self.assertRaisesRegex(RuntimeError,'wrong OS'): app.main()
        target.close.assert_called_once(); window.close.assert_called_once(); window.mainloop.assert_not_called(); self.assertIn('wrong OS',output.read_text())
        with patch.object(app,'Installer') as create,patch('sys.argv',['setup','--smoke-host','example.test']),contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as failure: app.main()
            self.assertEqual(failure.exception.code,2); create.assert_not_called()
