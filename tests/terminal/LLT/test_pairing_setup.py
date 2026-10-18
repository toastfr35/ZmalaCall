# @test T-LLT-024
# @requirements TLLR020, TLLR022, TLLR024
# @environment portable
# @plan Inject installation status, saved bonds, keyboard events and verified remote status into the setup controller; assert pairing alone cannot advance setup, camera ownership stays gated and calls keep priority.
# @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

"""First-run pairing precedes camera enrollment and never interrupts a call."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from zmala_terminal.linux.pairing_status import PairingStatus
from zmala_terminal.common.ui.remote_help import RemoteHelpView
from zmala_terminal.common.setup_flow import ProvisioningFlow
from zmala_terminal.common.model import State
from zmala_terminal.common.remote_test import RemoteTest, BUTTONS


class PairingSetupTests(unittest.TestCase):
    def test_installed_status_is_required_but_desktop_is_not_gated(self):
        with patch.dict('os.environ', {}, clear=True):
            self.assertIsNone(PairingStatus().read())
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'status.json'
            with patch.dict('os.environ', ZMALA_PAIRING_STATUS=str(path)):
                status = PairingStatus()
            self.assertEqual(status.read(), 'bluetooth_unavailable')
            for state in ('unpaired', 'pairing', 'paired'):
                path.write_text(json.dumps({'state': state}))
                status.next_read = 0
                self.assertEqual(status.read(), state)
            path.write_text('broken')
            status.next_read = 0
            self.assertEqual(status.read(), 'bluetooth_unavailable')

    def test_unpaired_first_run_does_not_open_camera(self):
        flow = ProvisioningFlow()
        flow.closed, flow.setup_stage, flow.scanner = False, 'wifi', None
        flow.needs_pairing = Mock(return_value=True)
        flow.needs_c20 = Mock(return_value=False)
        flow.make_scanner = Mock()
        flow.start_scanner()
        flow.update_setup_display(100)
        flow.make_scanner.assert_not_called()

    def test_call_retains_priority_and_pairing_completion_redraws(self):
        view = RemoteHelpView()
        view.pairing_status = Mock()
        view.pairing_status.read.return_value = 'unpaired'
        view.model = Mock(state=State.IN_CALL)
        view.pairing_page_visible = False
        self.assertFalse(view.update_pairing_page())
        view.model.state = State.HOME
        view.pairing_status.read.return_value = 'paired'
        view.pairing_status.bond = 'tested-bond'
        view.setup_stage = None
        view.presenter_input = Mock(status='connected')
        with tempfile.TemporaryDirectory() as folder:
            view.remote_test = RemoteTest(Path(folder)/'test.json')
        view.remote_test.verified = 'tested-bond'
        view.pairing_page_visible = True
        view.root, view.remote_help, view.render = Mock(), Mock(), Mock()
        self.assertFalse(view.update_pairing_page())
        view.root.after_idle.assert_called_once_with(view.render)

    def test_saved_pairing_and_keyboard_cannot_advance_setup(self):
        from zmala_terminal.common.main import Terminal
        with tempfile.TemporaryDirectory() as folder:
            view = RemoteHelpView()
            view.model = Mock(state=State.HOME)
            view.setup_stage = 'wifi'
            view.pairing_status = Mock(bond='bond')
            view.pairing_status.read.return_value = 'paired'
            view.presenter_input = Mock(status='connected')
            view.remote_test = RemoteTest(Path(folder)/'test.json')
            self.assertTrue(view.needs_pairing())
            view.input_activity = lambda: Terminal.input_activity(view)
            for button in BUTTONS:
                Terminal.keypress(view, button)
            self.assertEqual(view.remote_test.index, 0)
            view.needs_c20 = Mock(return_value=False)
            view.render = Mock()
            for button in BUTTONS:
                self.assertTrue(view.remote_test_event(button, True))
                self.assertTrue(view.remote_test_event(button, False))
            self.assertFalse(view.needs_pairing())
            view.presenter_input.status = 'disconnected'
            self.assertTrue(view.needs_pairing())
            view.presenter_input.status = 'connected'
            view.pairing_status.bond = 'new-pairing'
            self.assertTrue(view.needs_pairing())


if __name__ == '__main__':
    unittest.main()
