# Installer regression tests; outside the Pi runtime requirements baseline.
import unittest
from unittest.mock import Mock, patch
from build_tools.server_installer import app
from tests.support.installer_gui import InstallerUIContract


class ServerInstallerUITests(InstallerUIContract, unittest.TestCase):
    module = app

    def test_optional_migration_selection_and_confirmation(self):
        with patch.object(app.filedialog, 'askdirectory', side_effect=['', str(self.directory)]):
            self.app.choose(); self.assertEqual(self.app.data.get(), '')
            self.app.choose(); self.assertEqual(self.app.data.get(), str(self.directory))
        self.app.target = self.target
        self.dialogs.askokcancel.return_value = True
        with patch.object(app.threading, 'Thread', side_effect=self.run_worker): self.app.confirm()
        self.assertIn(str(self.directory), self.dialogs.askokcancel.call_args.args[1])
        self.assertEqual(self.target.install.call_args.args[1], str(self.directory))

    def test_entrypoint_smoke_checks_payload_then_closes_without_installing(self):
        output=self.directory/'smoke.txt'; window=Mock()
        with patch.object(app,'Installer',return_value=window),patch.object(app,'verify_payload') as verify,patch('sys.argv',['setup','--smoke-test',str(output)]):
            self.assertEqual(app.main(),0)
        verify.assert_called_once(); window.withdraw.assert_called_once(); window.close.assert_called_once(); window.mainloop.assert_not_called()
        self.assertIn('checksum verified',output.read_text())
        window.reset_mock()
        with patch.object(app,'Installer',return_value=window),patch('sys.argv',['setup']): self.assertEqual(app.main(),0)
        window.mainloop.assert_called_once(); window.close.assert_not_called()
