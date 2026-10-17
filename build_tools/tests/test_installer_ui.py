"""Confirmation and target invalidation in the Windows installer GUI."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'windows_installer'))
READY = sys.platform == 'win32' and all(importlib.util.find_spec(name) for name in ('tkinter', 'paramiko'))
if READY:
    import app


@unittest.skipUnless(READY, 'Windows with installer dependencies required')
class InstallerUiTests(unittest.TestCase):
    def setUp(self):
        self.ui = app.Installer()
        self.ui.withdraw()
        self.ui.update()

    def tearDown(self):
        self.ui.close()

    def checked_target(self):
        target = Mock()
        target.info = {'installed': False, 'model': 'Raspberry Pi 4 Model B',
                       'os': {'PRETTY_NAME': 'Raspberry Pi OS'}, 'ssh_address': '192.168.1.93'}
        target.key = 'SHA256:test'
        self.ui.target = target
        return target

    def test_install_disabled_before_checks(self):
        self.assertIn('disabled', self.ui.install_button.state())

    def test_cancel_confirmation_does_not_install(self):
        target = self.checked_target()
        with patch.object(app.messagebox, 'askokcancel', return_value=False), patch.object(self.ui, 'start') as start:
            self.ui.confirm()
        start.assert_not_called()
        target.install.assert_not_called()

    def test_confirmation_always_enables_argon_fan_setup(self):
        target = self.checked_target()
        with patch.object(app.messagebox, 'askokcancel', return_value=True), patch.object(self.ui, 'start') as start:
            self.ui.confirm()
        work, completion = start.call_args.args
        self.assertEqual(completion, 'installed')
        work()
        target.install.assert_called_once_with(self.ui.archive, True)

    def test_address_edit_invalidates_preflight(self):
        target = self.checked_target()
        self.ui.install_button.configure(state='normal')
        self.ui.host.set('192.168.1.99')
        self.assertIsNone(self.ui.target)
        target.close.assert_called_once()
        self.assertIn('disabled', self.ui.install_button.state())


if __name__ == '__main__':
    unittest.main()
