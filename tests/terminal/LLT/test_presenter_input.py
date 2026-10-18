# @test T-LLT-027
# @requirements LLR-TERM-REMOTE-002, LLR-TERM-REMOTE-003, LLR-TERM-REMOTE-004, LLR-TERM-REMOTE-005, LLR-TERM-REMOTE-009
# @environment portable
# @plan Feed recorded-format raw and evdev reports, signed motion, repeats and disconnects; assert Presenter-only button mapping, held-middle motion gating and release/status cleanup.
# @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

"""The measured remote button cannot be triggered by unrelated HID keys."""
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from zmala_terminal.linux.presenter_input import EVENT, PresenterInput, button_report, pointer_report, teams_events


class PresenterTests(unittest.TestCase):
    def test_measured_pointer_and_signed_vertical_motion(self):
        self.assertEqual(pointer_report(bytes.fromhex('043d010000000000')), ('held', True))
        self.assertEqual(pointer_report(bytes.fromhex('043d000000000000')), ('held', False))
        self.assertEqual(pointer_report(bytes.fromhex('0300fcfff2ff00000000')), ('motion', -14))
        self.assertEqual(pointer_report(bytes.fromhex('0300fcff160000000000')), ('motion', 22))
        for data in ['043d020000000000', '043d01', '0300fcfff2ff', '043e010000000000']:
            self.assertIsNone(pointer_report(bytes.fromhex(data)))

    def test_motion_requires_pointer_held_on_same_raw_device_and_disconnect_releases(self):
        pointer, motion = Mock(), Mock()
        with patch('zmala_terminal.linux.presenter_input.os.name', 'nt'):
            remote = PresenterInput(Mock(), Mock(), Mock(), pointer, motion)
        remote.raw_fds.update([11, 12])
        remote.devices = {'/dev/hidraw1': 11, '/dev/hidraw2': 12}
        packets = [('03000000f6ff00000000', 11), ('043d010000000000', 11),
                   ('043d010000000000', 11), ('043d000000000000', 12),
                   ('03000000f6ff00000000', 12), ('03000000f6ff00000000', 11),
                   ('043d000000000000', 11), ('03000000f6ff00000000', 11),
                   ('043d010000000000', 11)]
        for data, fd in packets:
            with patch('zmala_terminal.linux.presenter_input.os.read', return_value=bytes.fromhex(data)):
                remote.read(fd, 1)
        with patch('zmala_terminal.linux.presenter_input.os.close'):
            remote.remove(11)
        motion.assert_called_once_with(-10)
        self.assertEqual([c.args for c in pointer.call_args_list], [(True,), (False,), (True,), (False,)])
        self.assertIsNone(remote.pointer_fd)

    def test_status_tracks_device_availability_without_reporting_windows_disconnected(self):
        with patch('zmala_terminal.linux.presenter_input.os.name', 'nt'):
            remote = PresenterInput(Mock(), Mock(), Mock())
        self.assertIsNone(remote.connected)
        remote.supported = True
        self.assertFalse(remote.connected)
        remote.devices['/dev/hidraw1'] = 12
        self.assertTrue(remote.connected)
        with patch('zmala_terminal.linux.presenter_input.os.close'):
            remote.remove(12)
        self.assertFalse(remote.connected)

    def test_teams_press_release_filters_repeat_and_other_devices_keys(self):
        data = b''.join(EVENT.pack(0, 0, kind, code, value) for kind, code, value in
                        [(1, 104, 1), (1, 256, 1), (1, 256, 2), (0, 0, 0), (1, 256, 0)])
        self.assertEqual(list(teams_events(data)), [True, False])

    def test_disconnect_removes_handler_and_releases_held_button(self):
        root, press, release = Mock(), Mock(), Mock()
        with patch('zmala_terminal.linux.presenter_input.os.name', 'nt'):
            remote = PresenterInput(root, press, release)
        remote.devices = {'/dev/input/event10': 10}
        with patch('zmala_terminal.linux.presenter_input.os.read', return_value=b''), patch('zmala_terminal.linux.presenter_input.os.close') as close:
            remote.read(10, 1)
            root.deletefilehandler.assert_called_once_with(10)
            close.assert_called_once_with(10)
        self.assertEqual([call.args for call in release.call_args_list], [('green',), ('red',)])
        self.assertFalse(remote.devices)

    def test_vendor_buttons_ignore_pointer_motion_and_invalid_packets(self):
        for code, button in [('3e', 'red'), ('3f', 'green')]:
            self.assertEqual(button_report(bytes.fromhex('04'+code+'010000000000')), (button, True))
            self.assertEqual(button_report(bytes.fromhex('04'+code+'000000000000')), (button, False))
        for data in ['043d010000000000', '03000000010000000000',
                     '053d030000000000000000000000000000000000', '043f020000000000',
                     '043e020000000000', '043f01', '', '043e01000000000000']:
            self.assertIsNone(button_report(bytes.fromhex(data)))

    def test_teams_is_red_and_vendor_mute_is_green(self):
        root, press, release = Mock(), Mock(), Mock()
        with patch('zmala_terminal.linux.presenter_input.os.name', 'nt'):
            remote = PresenterInput(root, press, release)
        remote.raw_fds.add(11)
        with patch('zmala_terminal.linux.presenter_input.os.read', side_effect=[
                bytes.fromhex('043e010000000000'), bytes.fromhex('043e000000000000'),
                EVENT.pack(0, 0, 1, 256, 1)+EVENT.pack(0, 0, 1, 256, 0), bytes.fromhex('043f010000000000'),
                bytes.fromhex('043d010000000000'), bytes.fromhex('043f000000000000')]):
            remote.read(11, 1)
            remote.read(11, 1)
            remote.read(10, 1)
            remote.read(11, 1)
            remote.read(11, 1)
            remote.read(11, 1)
        self.assertEqual([call.args for call in press.call_args_list], [('red',), ('green',)])
        self.assertEqual([call.args for call in release.call_args_list], [('red',), ('green',)])

    def test_teams_evdev_fallback_without_raw_access(self):
        root, press, release = Mock(), Mock(), Mock()
        with patch('zmala_terminal.linux.presenter_input.os.name', 'nt'):
            remote = PresenterInput(root, press, release)
        with patch('zmala_terminal.linux.presenter_input.os.read', return_value=
                   EVENT.pack(0, 0, 1, 256, 1)+EVENT.pack(0, 0, 1, 256, 0)):
            remote.read(10, 1)
        press.assert_called_once_with('red')
        release.assert_called_once_with('red')
