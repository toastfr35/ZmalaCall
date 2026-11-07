# @test T-LLT-106
# @requirements LLR-TERM-SETUP-028, LLR-TERM-SETUP-029, LLR-TERM-NET-004
# @environment portable
# @plan Inject NetworkManager C-locale activation messages, timeouts and D-Bus permission errors. Assert safe classifications for missing SSID, authentication, permissions, unavailable adapter and IP address failure; unknown/private diagnostics stay generic. Run setup workers through current/stale generations, invalid QR, progress and failed joins; assert actionable visible text, no credentials in feedback/logs and owned UUID cleanup retaining the original failure.
# @pass All classification, UI state, ownership and privacy assertions pass with mocked network/Tk boundaries; no physical network or hardware pass is claimed.
import subprocess
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from zmala_terminal.common import setup_flow
from zmala_terminal.common.setup_feedback import MESSAGES, WifiSetupError
from zmala_terminal.linux import wifi
from tests.terminal.LLT import test_enrollment_lifecycle
from tests.terminal.LLT.test_display_states import fixture


class WifiFeedbackTests(unittest.TestCase):
    def test_nmcli_reasons_and_unknown_output_are_redacted(self):
        cases = {
            'The Wi-Fi network could not be found': 'network_not_found',
            'Secrets were required, but not provided': 'authentication_failed',
            '802.1X supplicant took too long to authenticate': 'authentication_failed',
            'Invalid secrets': 'authentication_failed',
            'Not authorized to control networking': 'permission_denied',
            'No suitable device found for this connection (device private-name unavailable)': 'wifi_unavailable',
            'IP configuration could not be reserved (no available address, timeout, etc.)': 'address_failed',
            'DHCP client failed': 'address_failed',
            'private-network private-password': 'connection_failed',
        }
        for diagnostic, expected in cases.items():
            with self.subTest(expected=expected):
                reply = SimpleNamespace(returncode=4,stderr='Warning: secret\nError: Connection activation failed: '+diagnostic+'\nHint: private-token')
                with patch.object(wifi.subprocess,'run',return_value=reply) as run:
                    with self.assertRaises(WifiSetupError) as caught:
                        wifi._nmcli(['connection','up','uuid','owned'])
                self.assertEqual(caught.exception.reason,expected)
                self.assertNotIn('private',str(caught.exception))
                self.assertEqual(run.call_args.kwargs['env']['LC_ALL'],'C')
                self.assertEqual(run.call_args.args[0][-1],'owned')
        self.assertEqual(wifi._activation_failure('unrecognized private output'),'connection_failed')
        self.assertEqual(WifiSetupError('private-password').reason,'connection_failed')

    def test_timeouts_are_safe_and_owned_cleanup_keeps_original_reason(self):
        for failure in (subprocess.TimeoutExpired(['nmcli'],40,stderr='private-password'),
                        SimpleNamespace(returncode=3,stderr='private-password')):
            with patch.object(wifi.subprocess,'run') as run:
                if isinstance(failure,Exception): run.side_effect=failure
                else: run.return_value=failure
                with self.assertRaises(WifiSetupError) as caught: wifi._nmcli(['connection','up'])
                self.assertEqual(caught.exception.reason,'timed_out')
        with patch.object(wifi,'_add_connection'), patch.object(wifi,'_nmcli',side_effect=[WifiSetupError('authentication_failed'),WifiSetupError('timed_out')]) as run:
            with self.assertRaises(WifiSetupError) as caught: wifi.connect_wifi({'ssid':'private'},'test','connect')
            self.assertEqual(caught.exception.reason,'authentication_failed')
            self.assertEqual(run.call_args_list[0].args[0][-1],run.call_args_list[1].args[0][-1])
            self.assertEqual(run.call_args.args[0][:3],['connection','delete','uuid'])

    def test_add_connection_permission_is_classified_without_error_message(self):
        gio = SimpleNamespace(DBusProxy=Mock(),DBusError=Mock(),BusType=SimpleNamespace(SYSTEM=1),
                              DBusProxyFlags=SimpleNamespace(NONE=0),DBusCallFlags=SimpleNamespace(NONE=0))
        glib = SimpleNamespace(Variant=lambda signature,value:value,Error=RuntimeError)
        gio.DBusProxy.new_for_bus_sync.side_effect=RuntimeError('private-password')
        for remote,reason in (('org.freedesktop.NetworkManager.Settings.PermissionDenied','permission_denied'),
                              ('org.freedesktop.DBus.Error.AccessDenied','permission_denied'),
                              ('unknown.private','connection_failed')):
            gio.DBusError.get_remote_error.return_value=remote
            with patch.dict(sys.modules,{'gi.repository':SimpleNamespace(Gio=gio,GLib=glib)}):
                with self.assertRaises(WifiSetupError) as caught:
                    wifi._add_connection({'ssid':'private','password':'private-password','security':'WPA','hidden':False},'id','name')
            self.assertEqual(caught.exception.reason,reason)
            self.assertNotIn('private',str(caught.exception))

    def test_invalid_progress_failure_stale_and_new_scan_feedback(self):
        flow = test_enrollment_lifecycle.EnrollmentLifecycleTests().flow()
        with self.assertLogs(level='WARNING'): flow.qr_found('private-invalid-code')
        self.assertEqual(flow.setup_feedback,'invalid_wifi_qr')
        workers=[]
        with patch.object(setup_flow.threading,'Thread',side_effect=lambda **kw:Mock(start=lambda:workers.append(kw['target']))):
            flow.qr_found('WIFI:S:private-name;T:WPA;P:private-password;;')
        self.assertEqual(flow.setup_feedback,'connecting')
        flow.render.assert_called()
        with patch.object(setup_flow,'connect_wifi',side_effect=WifiSetupError('network_not_found')):
            with self.assertLogs(level='WARNING') as logs: workers[0]()
        self.assertNotIn('private',' '.join(logs.output))
        _,event = flow.messages.get_nowait()
        flow.setup_result(0,'error','authentication_failed')
        self.assertEqual(flow.setup_feedback,'connecting')
        flow.setup_result(*event)
        self.assertEqual(flow.setup_feedback,'network_not_found')
        self.assertEqual(flow.setup_stage,'wifi')
        flow.enrollment.set_wifi.assert_not_called()
        flow.setup_result(flow.generation,'error','private-password')
        self.assertEqual(flow.setup_feedback,'connection_failed')

    def test_visible_feedback_is_bounded_and_progress_is_distinct(self):
        view=fixture();view.setup_stage='wifi'
        for reason,text in MESSAGES.items():
            view.setup_feedback=reason
            view.render_setup_feedback()
            self.assertEqual(view.setup_feedback_label.configure.call_args.kwargs['text'],text)
            self.assertNotIn('private',text)
        view.setup_feedback='connecting';view.render_setup_feedback()
        progress=view.setup_feedback_label.configure.call_args.kwargs['fg']
        view.setup_feedback='authentication_failed';view.render_setup_feedback()
        self.assertNotEqual(view.setup_feedback_label.configure.call_args.kwargs['fg'],progress)


if __name__=='__main__': unittest.main()
