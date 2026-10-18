# @test T-LLT-046
# @requirements LLR-TERM-SETUP-009, LLR-TERM-SETUP-012, LLR-TERM-SETUP-013
# @environment portable
# @plan Inject QR workers, monotonic time and NetworkManager D-Bus into setup; assert camera failure feedback and five-second retry, scanner release before engine activation, ten-second successful Wi-Fi confirmation and private owned-profile cleanup on cancellation.
# @pass All ownership, timing and credential-boundary assertions must pass without accessing a camera or changing network profiles.

import io
import sys
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from zmala_terminal.common.setup_flow import ProvisioningFlow
from zmala_terminal.common.qr_scanner import QRScanner
from zmala_terminal.linux import wifi


class SetupOwnershipTests(unittest.TestCase):
    def flow(self):
        f = ProvisioningFlow()
        f.scanner = Mock()
        f.render = Mock()
        f.generation = 1
        f.closed = False
        f.enrollment = Mock(value={})
        f.setup_stage = 'wifi'
        f.setup_busy = False
        f.needs_c20 = f.needs_pairing = Mock(return_value=False)
        f.video = Mock()
        f.video_border = (0, None)
        f.root = Mock()
        f.draw_wifi_confirmation = Mock()
        f.make_scanner = Mock()
        return f

    def test_worker_failure_and_start_failure_delay_five_seconds(self):
        for startup in (False, True):
            with self.subTest(startup=startup):
                f = self.flow()
                old = f.scanner
                with patch('zmala_terminal.common.setup_flow.time.monotonic', return_value=100):
                    if startup:
                        f.scanner = None
                        f.make_scanner.side_effect = RuntimeError('camera unavailable')
                        f.start_scanner()
                    else:
                        old.iterate.side_effect = RuntimeError('worker died')
                        f.iterate_scanner()
                        old.close.assert_called_once()
                self.assertIsNone(f.scanner)
                self.assertTrue(f.setup_feedback)
                self.assertEqual(f.setup_error_until, 105)
                f.make_scanner.reset_mock(side_effect=True)
                f.update_setup_display(104.9)
                f.make_scanner.assert_not_called()
                f.update_setup_display(105.1)
                f.make_scanner.assert_called_once()

    def test_wifi_success_holds_confirmation_and_failed_join_does_not_advance(self):
        f = self.flow()
        with patch('zmala_terminal.common.setup_flow.time.monotonic', return_value=100):
            f.setup_result(1, 'error', None)
            self.assertEqual(f.setup_stage, 'wifi')
            f.enrollment.set_wifi.assert_not_called()
            old = f.scanner
            f.setup_result(1, 'wifi', {'linux_uuid': 'owned'})
        old.close.assert_called_once()
        self.assertEqual(f.setup_stage, 'wifi_ready')
        self.assertEqual(f.setup_continue_at, 110)
        f.update_setup_display(109.99)
        self.assertEqual(f.setup_stage, 'wifi_ready')
        f.update_setup_display(110)
        self.assertEqual(f.setup_stage, 'server')

    def test_server_acceptance_releases_camera_before_native_engine(self):
        f = self.flow()
        events = []
        f.scanner.close.side_effect = lambda: events.append('camera closed')
        f.begin_tv_setup = Mock(return_value=False)
        f.apply_config = lambda config: events.append('engine start')
        f.make_maintenance = Mock()
        f.setup_result(1, 'server', (Mock(), {}))
        self.assertEqual(events, ['camera closed', 'engine start'])

    def test_qr_worker_cleanup_is_idempotent_even_when_graceful_stop_times_out(self):
        import subprocess
        s = QRScanner.__new__(QRScanner)
        s.closed = False
        s.process = Mock()
        s.process.poll.return_value = None
        s.process.wait.side_effect = [subprocess.TimeoutExpired('qr', 2), 0]
        s.job, s.reader, s.error_log = Mock(), Mock(), io.BytesIO()
        s.close(); s.close()
        s.process.stdin.write.assert_called_once_with(b'stop\n')
        s.job.close.assert_called_once()
        s.reader.join.assert_called_once_with(timeout=2)
        self.assertTrue(s.error_log.closed)

    def test_owned_join_credentials_use_dbus_and_cancel_removes_only_owned_uuid(self):
        proxy = Mock()
        gio = SimpleNamespace(DBusProxy=Mock(), BusType=SimpleNamespace(SYSTEM=1),
                              DBusProxyFlags=SimpleNamespace(NONE=0), DBusCallFlags=SimpleNamespace(NONE=0))
        gio.DBusProxy.new_for_bus_sync.return_value = proxy
        glib = SimpleNamespace(Variant=lambda signature, value: value, Error=RuntimeError)
        modules = {'gi.repository': SimpleNamespace(Gio=gio, GLib=glib)}
        values = {'ssid': 'Café', 'password': 'private fixture', 'security': 'WPA', 'hidden': True}
        with patch.dict(sys.modules, modules):
            wifi._add_connection(values, 'owned-uuid', 'ZmalaCall-terminal-owned')
        settings = proxy.call_sync.call_args.args[1][0]
        self.assertEqual(settings['connection']['uuid'], 'owned-uuid')
        self.assertTrue(settings['connection']['autoconnect'])
        self.assertEqual(settings['802-11-wireless']['powersave'], 2)
        self.assertEqual(bytes(settings['802-11-wireless']['ssid']).decode(), 'Café')
        self.assertEqual(settings['802-11-wireless-security']['psk'], values['password'])
        cancelled = threading.Event()
        with patch.object(wifi, '_add_connection') as add, patch.object(wifi, '_nmcli') as command:
            command.side_effect = lambda args: cancelled.set() if args[1] == 'up' else None
            with self.assertRaisesRegex(OSError, 'cancelled'):
                wifi.connect_wifi(values, 'terminal', 'native', cancelled)
            identifier = add.call_args.args[1]
            self.assertTrue(add.call_args.args[2].startswith('ZmalaCall-terminal-'))
            self.assertEqual(command.call_args.args[0], ['connection', 'delete', 'uuid', identifier])
            self.assertNotIn(values['password'], str(command.call_args_list))
        with patch.object(wifi, '_nmcli', return_value='owned-uuid') as command:
            wifi.forget_wifi({'linux_profile': 'Home', 'linux_uuid': 'owned-uuid'}, 'terminal')
            command.assert_not_called()
            wifi.forget_wifi({'linux_profile': 'ZmalaCall-terminal-owned', 'linux_uuid': 'owned-uuid'}, 'terminal')
            self.assertEqual(command.call_args.args[0], ['connection', 'delete', 'uuid', 'owned-uuid'])

    def test_ethernet_does_not_bypass_normal_join(self):
        with patch.object(wifi, 'network_link_available', return_value=True), \
                patch.object(wifi, '_add_connection', side_effect=OSError('no wifi')) as add:
            with self.assertRaises(OSError):
                wifi.connect_wifi({}, 'terminal', 'native')
            add.assert_called_once()
            self.assertEqual(wifi.connect_wifi({}, 'terminal', 'existing-link')['connection_mode'], 'existing-link')
