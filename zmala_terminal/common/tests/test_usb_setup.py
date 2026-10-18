"""C20-specific presence and the installation-only camera gate."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from zmala_terminal.linux.c20_status import c20_connected, C20Status
from zmala_terminal.common.ui.usb_setup import UsbSetupView
from zmala_terminal.common.ui.display import TerminalDisplay
from zmala_terminal.common.setup_flow import ProvisioningFlow
from zmala_terminal.common.model import State


class UsbSetupTests(unittest.TestCase):
    def test_only_c20_counts_and_hotplug_is_observed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            device = root / '1-1'
            device.mkdir()
            for key, value in {'idVendor': '0525', 'idProduct': 'a4ad', 'product': 'Nuroum C10'}.items():
                (device / key).write_text(value)
            self.assertFalse(c20_connected(root))
            (device / 'product').write_text('Nuroum C20')
            self.assertTrue(c20_connected(root))
            (device / 'idProduct').unlink()
            self.assertFalse(c20_connected(root))

    def test_probe_is_opt_in_and_cached(self):
        with patch.dict('os.environ', {}, clear=True):
            self.assertIsNone(C20Status().read())
        with patch('zmala_terminal.linux.c20_status.sys.platform', 'linux'), patch.dict('os.environ', ZMALA_C20_SETUP='1'):
            status = C20Status()
        with patch('zmala_terminal.linux.c20_status.c20_connected', side_effect=[False, True]) as probe:
            self.assertFalse(status.read())
            self.assertFalse(status.read())
            self.assertEqual(probe.call_count, 1)
            status.next_read = 0
            self.assertTrue(status.read())

    def test_gate_only_applies_to_enrollment_and_preserves_calls(self):
        view = UsbSetupView()
        view.model = Mock(state=State.HOME)
        view.c20_status = Mock()
        view.c20_status.read.return_value = False
        for stage, expected in [('wifi', True), ('server', True), ('wifi_ready', True), (None, False), ('reset', False)]:
            view.setup_stage = stage
            self.assertEqual(view.needs_c20(), expected)
        view.setup_stage = 'wifi'
        view.model.state = State.IN_CALL
        self.assertFalse(view.needs_c20())
        view.model.state = State.HOME
        view.c20_status.read.return_value = True
        self.assertFalse(view.needs_c20())

    def test_missing_camera_blocks_scanner_before_pairing(self):
        flow = ProvisioningFlow()
        flow.closed, flow.setup_stage, flow.scanner = False, 'wifi', None
        flow.needs_c20 = Mock(return_value=True)
        flow.needs_pairing = Mock(return_value=False)
        flow.make_scanner = Mock()
        flow.start_scanner()
        flow.update_setup_display(100)
        flow.make_scanner.assert_not_called()
        flow.needs_pairing.assert_not_called()

    def test_setup_english_does_not_replace_normal_selected_language(self):
        view = TerminalDisplay()
        view.language = 'fr'
        view.setup_stage = 'wifi'
        self.assertEqual(view.text('remote_picture_back'), 'Back')
        view.setup_stage = None
        self.assertEqual(view.text('remote_picture_back'), 'Dos')


if __name__ == '__main__':
    unittest.main()
