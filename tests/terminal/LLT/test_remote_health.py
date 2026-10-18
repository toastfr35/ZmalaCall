# @test T-LLT-029
# @requirements TLLR017, TLLR018, TLLR019
# @environment portable
# @plan Inject remote connection, status-file freshness, battery and charging changes; assert stale or malformed status cannot report a healthy remote and assistance does not interrupt a call.
# @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

"""Hardware failures must not be mislabeled as a remote being switched off."""
from pathlib import Path
import subprocess
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from zmala_terminal.linux.remote_health import RemoteHealth, battery_percentage, bluetooth_snapshot, bluetooth_state, charger_connected, remote_charger_connected
from zmala_terminal.common.ui.remote_help import RemoteHelpView
from zmala_terminal.common.model import State
from zmala_terminal.common.localization import LANGUAGES, REMOTE_MESSAGES, REMOTE_ORIENTATION, REMOTE_ORIENTATION_KEYS, translate


class RemoteHealthTests(unittest.TestCase):
    def test_battery_formats_absence_and_invalid_values(self):
        self.assertEqual(battery_percentage('\tBattery Percentage: 0x5f (95)\n'), 95)
        self.assertEqual(battery_percentage('Battery Percentage: 20'), 20)
        self.assertEqual(battery_percentage('Battery Percentage: 0x00 (0)'), 0)
        for value in ('', 'Battery Percentage: unknown', 'Battery Percentage: 101', 'Battery Percentage: -1'):
            self.assertIsNone(battery_percentage(value))

    def test_disconnected_or_expired_battery_is_not_displayed_as_current(self):
        for connected, expected in [('yes', 95), ('no', None)]:
            replies = ['Powered: yes', 'Device E8:DA:FC:18:34:86 Microsoft Presenter+',
                       f'Paired: yes\nConnected: {connected}\nBattery Percentage: 0x5f (95)']
            self.assertEqual(bluetooth_snapshot(Mock(side_effect=replies))[1], expected)
        health = RemoteHealth.__new__(RemoteHealth)
        health.snapshot = ('input_unavailable', 95, True, 100.)
        with patch('zmala_terminal.linux.remote_health.time.monotonic', return_value=105):
            self.assertEqual(health.battery, 95)
            self.assertTrue(health.charger_connected)
        with patch('zmala_terminal.linux.remote_health.time.monotonic', return_value=121):
            self.assertIsNone(health.battery)
            self.assertIsNone(health.charger_connected)

    def test_measured_charger_reports_and_unknown_shapes(self):
        self.assertTrue(charger_connected(bytes.fromhex('3903200000000000')))
        self.assertFalse(charger_connected(bytes.fromhex('3903000000000000')))
        for value in ('', '390320', '3901200000000000', '3903400000000000',
                      '3903200100000000', '043e010000000000'):
            self.assertIsNone(charger_connected(bytes.fromhex(value)))

    def test_read_only_current_charger_query_and_failure(self):
        from unittest.mock import MagicMock
        device = MagicMock()
        device.name = 'hidraw2'
        (device / 'device/uevent').read_text.return_value = ('HID_NAME=Microsoft Presenter+\n'
                                                           'HID_ID=0005:0000045E:00000851')
        def read(fd, request, data, mutate):
            self.assertEqual(request, 0xc008480a)
            data[:7] = bytes.fromhex('39032000000000')
            return 7  # This HID-over-Bluetooth driver copies seven bytes.
        fake = SimpleNamespace(ioctl=Mock(side_effect=read))
        with patch.dict(sys.modules, {'fcntl': fake}), patch('zmala_terminal.linux.remote_health.Path.glob', return_value=[device]), \
                patch('zmala_terminal.linux.remote_health.os.open', return_value=12), patch('zmala_terminal.linux.remote_health.os.close') as close, \
                patch('zmala_terminal.linux.remote_health.os.O_NONBLOCK', 2048, create=True):
            self.assertTrue(remote_charger_connected())
            close.assert_called_with(12)
            fake.ioctl.side_effect = OSError('unsupported or disconnected')
            self.assertIsNone(remote_charger_connected())
            self.assertEqual(close.call_count, 2)

    def test_recovery_translations_and_explicit_fallback(self):
        self.assertEqual(set(REMOTE_MESSAGES['en']), set(REMOTE_MESSAGES['fr']))
        for key in REMOTE_MESSAGES['en']:
            self.assertTrue(translate('fr', key))
            if key not in REMOTE_ORIENTATION_KEYS:
                self.assertEqual(translate('de', key), translate('en', key))
        self.assertEqual(set(REMOTE_ORIENTATION), set(LANGUAGES))
        for language, values in REMOTE_ORIENTATION.items():
            self.assertEqual(len(values), len(REMOTE_ORIENTATION_KEYS))
            for key, expected in zip(REMOTE_ORIENTATION_KEYS, values):
                self.assertTrue(expected.strip())
                self.assertEqual(translate(language, key), expected)

    def probe(self, info='', adapter='Powered: yes', listing=None):
        if listing is None:
            listing = 'Device E8:DA:FC:18:34:86 Microsoft Presenter+'
        outputs = {'show': adapter, 'devices': listing, 'info': info}
        return bluetooth_state(lambda verb, *args: outputs[verb])

    def test_pairing_connection_and_blocked_are_distinct(self):
        self.assertEqual(self.probe('Paired: yes\nConnected: no'), 'disconnected')
        self.assertEqual(self.probe('Paired: no\nConnected: no'), 'unpaired')
        self.assertEqual(self.probe('Paired: yes\nConnected: yes'), 'input_unavailable')
        self.assertEqual(self.probe('Paired: yes\nConnected: no\nBlocked: yes'), 'blocked')
        self.assertEqual(self.probe(listing=''), 'unpaired')

    def test_adapter_failure_and_unreadable_results_do_not_claim_unpaired(self):
        self.assertEqual(self.probe(adapter='Powered: no'), 'bluetooth_unavailable')
        self.assertEqual(self.probe(adapter='No default controller available'), 'bluetooth_unavailable')
        self.assertEqual(self.probe(adapter='Waiting to connect to bluetoothd...'), 'unknown')
        self.assertEqual(self.probe(info='Device not available'), 'unknown')
        self.assertEqual(self.probe(listing='Failed to connect'), 'unknown')
        for error in (FileNotFoundError(), subprocess.TimeoutExpired('bluetoothctl', 3)):
            self.assertEqual(bluetooth_state(Mock(side_effect=error)), 'unknown')

    def test_multiple_cached_remotes_prefer_working_pairing(self):
        replies = ['Powered: yes', 'Device 11:22:33:44:55:66 Microsoft Presenter+\n'
                   'Device E8:DA:FC:18:34:86 Microsoft Presenter+',
                   'Paired: no\nConnected: no', 'Paired: yes\nConnected: no']
        self.assertEqual(bluetooth_state(Mock(side_effect=replies)), 'disconnected')

    def test_page_grace_reconnect_calls_and_unsupported_platform(self):
        view = RemoteHelpView()
        view.update_usb_setup = Mock(return_value=False)
        view.pairing_status = Mock()
        view.pairing_status.read.return_value = None
        view.pairing_page_visible = False
        view.root = Mock()
        view.root.winfo_width.return_value = 1280
        view.root.winfo_height.return_value = 720
        view.remote_help = Mock()
        view.remote_help_title, view.remote_help_detail, view.remote_help_icon = Mock(), Mock(), Mock()
        view.label_remote_picture = Mock()
        view.remote_missing_since = view.remote_help_signature = None
        view.presenter_input = Mock(status='disconnected')
        view.model = Mock(state=State.HOME)
        view.setup_stage = None
        view.language, view.font_family = 'fr', 'DejaVu Sans'
        view.text, view.text_renderer, view.icon_renderer = Mock(), Mock(), Mock()
        with patch('zmala_terminal.common.ui.remote_help.time.monotonic', return_value=100):
            view.update_remote_help()
        view.remote_help.place.assert_not_called()
        with patch('zmala_terminal.common.ui.remote_help.time.monotonic', return_value=106), patch.object(view, 'remote_back_picture'):
            view.update_remote_help()
            view.remote_help.place.assert_called_once()
            for state in (State.RINGING, State.IN_CALL, State.CONNECTING, State.CONFIRMING):
                view.model.state = state
                view.remote_help.reset_mock()
                view.update_remote_help()
                view.remote_help.place.assert_not_called()
                view.remote_help.place_forget.assert_called_once()
            view.model.state = State.HOME
            view.setup_stage = 'wifi'
            view.remote_help.reset_mock()
            view.update_remote_help()
            view.remote_help.place.assert_not_called()
            view.setup_stage = None
            for status in ('connected', None):
                view.presenter_input.status = status
                view.update_remote_help()
                self.assertIsNone(view.remote_missing_since)


if __name__ == '__main__':
    unittest.main()
