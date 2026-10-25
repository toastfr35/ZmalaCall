# @test T-LLT-027
# @requirements LLR-TERM-REMOTE-013, LLR-TERM-REMOTE-014, LLR-TERM-REMOTE-015, LLR-TERM-REMOTE-016, LLR-TERM-REMOTE-019
# @environment portable
# @plan Feed recorded-format raw and evdev reports, signed motion, repeats and disconnects; assert Presenter-only button mapping, middle-button duplicate suppression, optional raw-motion callback gating and release/status cleanup (the volume page does not bind motion). Inject sysfs identities and descriptor failures to check exclusive remote discovery, reconnect, observer consumption, health exposure and handler/descriptor cleanup.
# @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

"""The measured remote button cannot be triggered by unrelated HID keys."""
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from zmala_terminal.linux.presenter_input import EVENT, PresenterInput, button_report, pointer_report, teams_events


class PresenterTests(unittest.TestCase):
    def test_discovery_accepts_only_presenter_devices_and_closes_failed_registration(self):
        import zmala_terminal.linux.presenter_input as module
        root = Mock()
        health = Mock(battery=63, charger_connected=True, state='unpaired')
        with patch.object(module.os, 'name', 'posix'), patch.object(module, 'RemoteHealth', return_value=health), \
                patch.object(PresenterInput, 'discover') as discover:
            remote = PresenterInput(root, Mock(), Mock())
        discover.assert_called_once()
        self.assertEqual(remote.status, 'unpaired')
        self.assertIsNone(remote.battery)
        with tempfile.TemporaryDirectory() as temporary, patch.object(module.os, 'open', side_effect=[11, 12, 13]) as opened, \
                patch.object(module.os, 'close') as closed, patch.object(module.os, 'O_NONBLOCK', 2048, create=True):
            device = Path(temporary)/'hidraw1'
            (device/'device').mkdir(parents=True)
            identity = device/'device/uevent'
            identity.write_text('HID_NAME=Other\nHID_ID=0005:0000045E:00000851')
            remote.open_device(device, True)
            opened.assert_not_called()
            identity.write_text('HID_NAME=Microsoft Presenter+\nHID_ID=0005:0000045E:00000851')
            remote.open_device(device, True)
            remote.open_device(device, True)
            self.assertEqual(opened.call_count, 1)
            self.assertEqual(remote.status, 'input_unavailable')
            self.assertEqual(remote.battery, 63)
            self.assertTrue(remote.charger_connected)
            event = Path(temporary)/'event2'
            (event/'device').mkdir(parents=True)
            (event/'device/name').write_text('Keyboard')
            remote.open_device(event, False)
            self.assertEqual(opened.call_count, 1)
            (event/'device/name').write_text('Microsoft Presenter+ Consumer Control')
            remote.open_device(event, False)
            self.assertEqual(remote.status, 'connected')
            root.createfilehandler.side_effect = OSError('disconnected')
            remote.open_device(device, False)
            # Missing evdev identity is ignored before trying to open it.
            self.assertEqual(opened.call_count, 2)
            (device/'device/name').write_text('Microsoft Presenter+')
            remote.open_device(device, False)
            closed.assert_called_once_with(13)
            self.assertNotIn('/dev/input/hidraw1', remote.devices)
            remote.timer = 'discovery-timer'
            remote.close()
            health.close.assert_called_once()
            root.after_cancel.assert_called_once_with('discovery-timer')
            self.assertFalse(remote.devices)
            self.assertEqual(closed.call_count, 3)
        with patch.object(module, 'Path') as paths:
            remote.discover()
            paths.assert_not_called()

    def test_discovery_reconnects_and_read_handles_backpressure_and_observer(self):
        import zmala_terminal.linux.presenter_input as module
        with patch.object(module.os, 'name', 'nt'):
            remote = PresenterInput(Mock(), Mock(), Mock(), observe=Mock(return_value=True))
        remote.supported = True
        remote.devices = {'/dev/missing': 7}
        def path(value):
            return SimpleNamespace(exists=lambda: False, glob=lambda pattern: [value+'/'+pattern])
        with patch.object(module, 'Path', side_effect=path), patch.object(remote, 'remove') as remove, \
                patch.object(remote, 'open_device') as opened:
            remote.discover()
        remove.assert_called_once_with(7)
        self.assertEqual(opened.call_count, 2)
        self.assertEqual(remote.root.after.call_args.args[0], 3000)
        remote.raw_fds.add(8)
        for data, fd in [(bytes.fromhex('043d010000000000'), 8),
                         (bytes.fromhex('043f010000000000'), 8),
                         (EVENT.pack(0, 0, 1, 104, 1), 7)]:
            with patch.object(module.os, 'read', return_value=data):
                remote.read(fd, 1)
        self.assertEqual(remote.observe.call_args_list[0].args, ('pointer', True))
        self.assertEqual(remote.observe.call_args_list[-1].args, ('left', True))
        remote.press.assert_not_called()
        with patch.object(module.os, 'read', side_effect=BlockingIOError), patch.object(remote, 'remove') as remove:
            remote.read(8, 1)
            remove.assert_not_called()
        with patch.object(module.os, 'read', side_effect=OSError), patch.object(remote, 'remove') as remove:
            remote.read(8, 1)
            remove.assert_called_once_with(8)
        with patch.object(module.os, 'read', side_effect=RuntimeError), patch.object(module.logging, 'exception') as logged:
            remote.read(8, 1)
            logged.assert_called_once()

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
