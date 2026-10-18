"""Button verification cannot be passed by repeat, disconnect or stale state."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from zmala_terminal.common.remote_test import RemoteTest, BUTTONS
from zmala_terminal.linux.presenter_input import PresenterInput, EVENT


class RemoteTestTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name)/'test.json'
        self.test = RemoteTest(self.path)
        self.test.sync('bond', True)

    def click(self, button):
        self.test.event(button, True)
        self.test.event(button, False)

    def test_order_release_repeat_and_chords(self):
        self.click('red')
        self.test.event('left', False)
        self.assertEqual(self.test.index, 0)
        self.test.event('left', True)
        self.test.event('left', True)
        self.assertEqual(self.test.index, 0)
        self.test.event('right', True)
        self.test.event('left', False)
        self.test.event('right', False)
        self.assertEqual(self.test.index, 0)
        for button in BUTTONS:
            self.click(button)
        self.assertTrue(self.test.complete)

    def test_disconnect_resets_progress_and_release_cannot_complete(self):
        self.click('left')
        self.test.event('right', True)
        self.test.sync('bond', False)
        self.test.sync('bond', True)
        self.test.event('right', False)
        self.assertEqual(self.test.index, 0)
        self.assertFalse(self.path.exists())

    def test_reboot_keeps_only_completed_test_new_bond_and_reset_require_retest(self):
        self.click('left')
        restored = RemoteTest(self.path)
        restored.sync('bond', True)
        self.assertFalse(restored.complete)
        for button in BUTTONS[1:]:
            self.click(button)
        restored = RemoteTest(self.path)
        restored.sync('bond', True)
        self.assertTrue(restored.complete)
        restored.sync('new-bond', True)
        self.assertFalse(restored.complete)
        restored.reset()
        restored.sync('bond', True)
        self.assertFalse(restored.complete)

    def test_write_failure_keeps_final_step_and_allows_retry(self):
        for button in BUTTONS[:-1]:
            self.click(button)
        with patch('zmala_terminal.common.remote_test.write_json', side_effect=OSError):
            self.click('pointer')
        self.assertFalse(self.test.complete)
        self.assertTrue(self.test.error)
        self.click('pointer')
        self.assertTrue(self.test.complete)

    def test_reader_reports_real_navigation_and_consumes_vendor_actions(self):
        observe = Mock(return_value=True)
        with patch('zmala_terminal.linux.presenter_input.os.name', 'nt'):
            remote = PresenterInput(Mock(), Mock(), Mock(), Mock(), Mock(), observe)
        remote.raw_fds.add(11)
        for code in (104, 109):
            data = b''.join(EVENT.pack(0, 0, 1, code, v) for v in (1, 2, 0))
            with patch('zmala_terminal.linux.presenter_input.os.read', return_value=data):
                remote.read(10, 1)
        for code in ('3f', '3e', '3d'):
            for value in ('01', '00'):
                with patch('zmala_terminal.linux.presenter_input.os.read', return_value=bytes.fromhex('04'+code+value+'0000000000')):
                    remote.read(11, 1)
        self.assertEqual([c.args for c in observe.call_args_list],
                         [(b, down) for b in BUTTONS for down in (True, False)])
        remote.press.assert_not_called()
        remote.release.assert_not_called()
        remote.pointer.assert_not_called()

