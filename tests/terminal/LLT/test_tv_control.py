# @test T-LLT-036
# @requirements LLR-TERM-TV-026, LLR-TERM-TV-027, LLR-TERM-TV-028, LLR-TERM-TV-031, LLR-TERM-TV-032
# @environment portable
# @plan Simulate TV power/input observations, network fallback, concurrent calls and delayed workers; assert the first button only reveals the UI, restoration uses the saved state, stale work is fenced and no volume/mute command is emitted. Reproduce unknown power after restart with power qualified, source switching skipped and an unconfigured adapter; require the press to be consumed and playback registration/wake sent, without inventing a restoration baseline. Reject unknown-state wake when power is disabled. Feed fragmented CEC monitor output through fake selectors/processes; assert atomic routing heartbeats, query timeout handling, connected-port changes and monitor cleanup.
# @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

"""Check CEC routing, cancellation and failures without changing a real TV."""
from pathlib import Path
import json
import subprocess
import sys
import threading
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from zmala_terminal.linux.tv_control import TVControl
from zmala_terminal.common.call_control import CallControl
from zmala_terminal.common.model import TerminalModel
from tests.terminal.LLT.test_terminal import config
from zmala_terminal.common.management import ManagementLoop, defer_auto_answer
from zmala_terminal.linux.cec_observer import RoutingState


class TVControlTests(unittest.TestCase):
    def test_observer_assembles_reports_publishes_atomic_heartbeat_and_closes_dead_monitor(self):
        import zmala_terminal.linux.cec_observer as observer
        process = Mock()
        process.poll.side_effect = [None, None, 1]
        selector = Mock()
        selector.select.return_value = [(SimpleNamespace(fd=12), 1)]
        chunks = [b'Received from Playback Device 1 to all (4 to 15): ACTIVE_SOURCE (0x82)\n  phys-addr: 1.',
                  b'0.0.0\nReceived from TV to all (0 to 15): STANDBY (0x36)\n']
        with tempfile.TemporaryDirectory() as temporary, patch.object(observer.subprocess, 'Popen', return_value=process), \
                patch.object(observer.subprocess, 'run', side_effect=subprocess.TimeoutExpired('cec', 3)) as query, \
                patch.object(observer.selectors, 'DefaultSelector') as selectors, \
                patch.object(observer.os, 'read', side_effect=chunks), \
                patch.object(observer.time, 'monotonic', return_value=100), patch.object(observer.time, 'time', return_value=123):
            selectors.return_value.__enter__.return_value = selector
            destination = Path(temporary)/'state.json'
            with self.assertRaisesRegex(RuntimeError, 'monitor stopped'):
                observer.observe('/dev/cec0', destination)
            state = json.loads(destination.read_text())
            self.assertEqual(state, {'device':'/dev/cec0', 'active_source':'1.0.0.0', 'off':True, 'updated_at':123})
            self.assertFalse(destination.with_suffix('.tmp').exists())
            self.assertEqual(query.call_count, 1)
            self.assertIn('--request-active-source', query.call_args.args[0])
        process.terminate.assert_called_once()
        process.wait.assert_called_once_with(timeout=5)

    def test_observer_reopens_changed_hdmi_adapter_without_inventing_routing(self):
        import zmala_terminal.linux.cec_observer as observer
        process = Mock()
        process.poll.return_value = None
        with patch.object(observer.subprocess, 'Popen', return_value=process), \
                patch.object(observer.selectors, 'DefaultSelector'), \
                patch.object(observer, 'select_device', return_value='/dev/cec1'), \
                patch.object(observer.os, 'replace') as replace:
            observer.observe('/dev/cec0', Path('unused'), automatic=True)
        replace.assert_not_called()
        process.terminate.assert_called_once()
        state = RoutingState()
        state.consume('Transmitted by Playback Device 1 to TV (4 to 0): IMAGE_VIEW_ON (0x04)')
        self.assertFalse(state.off)
        self.assertIsNone(state.source)

    def test_answer_waits_for_tv_but_has_a_bounded_wait(self):
        model = TerminalModel()
        model.configure(config() | {'auto_answer': True})
        model.incoming('alice', 'family.test')
        model.deadline = 5
        tv = self.controller()
        tv._started = 0
        tv._ready.clear()
        defer_auto_answer(model, tv, 6)
        self.assertIsNone(model.tick(6))
        self.assertEqual(model.deadline, 11)
        tv._ready.set()
        defer_auto_answer(model, tv, 10)
        self.assertEqual(model.tick(11), 'answer')
        tv._ready.clear()
        self.assertTrue(tv.ready(30), 'Slow CEC must not block calls forever')
        model.deadline = None
        defer_auto_answer(model, tv, 12)
        self.assertIsNone(model.deadline)
    def test_only_permitted_incoming_calls_wake_tv_and_end_cancels(self):
        model = TerminalModel()
        model.configure(config())
        app = SimpleNamespace(model=model, engine=Mock(), tv_control=Mock(),
                              reset_gesture=Mock(), setup_stage=None, root=Mock(),
                              render=Mock(), missed_calls_store=Mock())
        app.finish_call = lambda **kwargs: CallControl.finish_call(app, **kwargs)
        CallControl.call_event(app, 'call', 1, 'unknown', 'family.test')
        app.tv_control.wake.assert_not_called()
        CallControl.call_event(app, 'call', 1, 'alice', 'family.test')
        app.tv_control.wake.assert_called_once()
        app.engine.call = 'call'
        CallControl.call_event(app, 'call', 14, 'alice', 'family.test')
        app.tv_control.cancel.assert_called_once()

    def controller(self):
        tv = TVControl(device='/dev/cec0', state_file='/nonexistent-zmala-test-state.json')
        tv.command = 'cec-ctl'
        tv._run = Mock(return_value='3.0.0.0')
        tv._samsung = Mock()
        tv._samsung.restore_broadcast.return_value = False
        return tv

    def test_visible_terminal_buttons_do_not_start_cec_commands(self):
        tv = self.controller()
        tv._address = '2.0.0.0'
        tv._observed_state = Mock(return_value={'off': False, 'active_source': '2.0.0.0'})
        with patch.object(Path, 'exists', return_value=True), patch('threading.Thread') as thread:
            self.assertFalse(tv.handle_button(Mock()))
        thread.assert_not_called()
        tv._run.assert_not_called()

    def test_unknown_power_can_wake_with_source_check_skipped_after_restart(self):
        tv = self.controller()
        tv.source_enabled = False
        tv._observed_state = Mock(return_value={})
        action = Mock()
        with patch.object(Path, 'exists', return_value=True), patch('threading.Thread') as thread:
            self.assertTrue(tv.handle_button(action))
            thread.assert_called_once()
        configured = False
        woke = False

        def run(*args):
            nonlocal configured, woke
            if '--physical-address' in args:
                return '2.0.0.0'
            if '--logical-address' in args:
                return '4' if configured else '65535'
            if '--playback' in args:
                configured = True
            if '--image-view-on' in args:
                self.assertTrue(configured)
                woke = True
            if '--give-device-power-status' in args:
                return 'pwr-state: on (0x00)' if woke else 'Adapter is unconfigured, please configure it first.'
            return ''

        tv._run.side_effect = run
        tv.wake = Mock()
        tv._button_worker(tv._cancel, action, False)
        action.assert_not_called()
        initial = tv.wake.call_args.kwargs['initial']
        self.assertIsNone(initial['off'])
        tv._cancel.wait = Mock(return_value=False)
        tv._worker(tv._cancel, restore=False, initial=initial)
        self.assertTrue(woke)
        self.assertIsNone(tv._browse_previous, 'Unknown power must not become a standby restoration baseline')
        tv._samsung.select_terminal.assert_not_called()

        tv.power_enabled = False
        for source_enabled in (False, True):
            tv.source_enabled = source_enabled
            with patch.object(Path, 'exists', return_value=True), patch('threading.Thread') as thread:
                self.assertFalse(tv.handle_button(action))
                thread.assert_not_called()

    def test_other_source_or_standby_consumes_press_and_reveals_terminal(self):
        for off, source in ((False, '0.0.0.0'), (True, '2.0.0.0'), (None, None)):
            with self.subTest(off=off, source=source):
                tv = self.controller()
                tv._previous_power = Mock(return_value=off)
                tv._previous_source = Mock(return_value=source)
                tv.wake = Mock()
                action = Mock()
                tv._button_worker(tv._cancel, action, False)
                action.assert_not_called()
                tv.wake.assert_called_once_with(restore=False, initial={
                    'off': off, 'source': source, 'address': '3.0.0.0'})

    def test_standby_at_press_survives_on_reports_during_wake(self):
        tv = self.controller()
        tv._run.side_effect = lambda *args: ('pwr-state: on (0x00)' if '--give-device-power-status' in args else '3.0.0.0')
        tv._observed_state = Mock(return_value={'off': True, 'active_source': '0.0.0.0'})
        original_wake = tv.wake
        tv.wake = Mock()
        tv._button_worker(tv._cancel, Mock(), False)
        initial = tv.wake.call_args.kwargs['initial']
        tv.wake = original_wake
        tv._observed_state.return_value = {'off': False, 'active_source': '3.0.0.0'}
        tv._cancel.wait = Mock(return_value=False)
        tv._worker(tv._cancel, restore=False, initial=initial)
        self.assertTrue(tv._browse_previous['off'])
        self.assertEqual(tv._browse_previous['source'], '0.0.0.0')

    def test_first_visible_press_after_restart_dispatches_its_action(self):
        tv = self.controller()
        tv._run.side_effect = ['2.0.0.0', 'pwr-state: on (0x00)']
        tv._previous_source = Mock(return_value='2.0.0.0')
        tv.wake = Mock()
        action = Mock()
        tv._button_worker(tv._cancel, action, True)
        action.assert_called_once()
        tv.wake.assert_not_called()
        self.assertEqual(tv._address, '2.0.0.0')

    def test_buttons_during_switching_are_not_queued_or_restarted(self):
        tv = self.controller()
        for pending, ready in ((True, True), (False, False)):
            tv._input_pending = pending
            tv._ready.set() if ready else tv._ready.clear()
            with patch.object(Path, 'exists', return_value=True), patch('threading.Thread') as thread:
                self.assertTrue(tv.handle_button(Mock()))
            thread.assert_not_called()

    def test_explicit_reveal_stays_on_terminal_instead_of_restoring_broadcast(self):
        tv = self.remembered(off=True, source='0.0.0.0')
        tv._previous_power = Mock(return_value=False)
        tv._previous_source = Mock(return_value='0.0.0.0')
        tv._cancel.wait = Mock(return_value=False)
        tv._worker(tv._cancel, restore=False)
        self.assertIsNone(tv._previous)
        self.assertFalse(tv._changed)
        tv._run.reset_mock()
        tv._restore(tv._cancel)
        tv._run.assert_not_called()

    def test_browsing_restores_original_source_or_standby_independent_of_calls(self):
        for off, source in ((False, '0.0.0.0'), (False, '1.0.0.0'), (True, '2.0.0.0')):
            tv = self.controller()
            tv._previous_power = Mock(return_value=off)
            tv._previous_source = Mock(return_value=source)
            tv._cancel.wait = Mock(return_value=False)
            tv._restore_wait = Mock(return_value=True)
            tv._worker(tv._cancel, restore=False)
            session = tv._browse_previous
            self.assertEqual(session['source'], source)
            # A call while browsing sees UI already visible; hang-up leaves the browsing lease.
            tv._previous_power.return_value = False
            tv._previous_source.return_value = '3.0.0.0'
            tv._worker(tv._cancel, restore=True)
            tv._run.reset_mock()
            tv._restore(tv._cancel)
            tv._run.assert_not_called()
            self.assertIs(tv._browse_previous, session)
            tv._restore(tv._cancel, browsing=True)
            if off:
                tv._run.assert_any_call('--to', '0', '--standby')
            elif source == '0.0.0.0':
                tv._samsung.restore_broadcast.assert_called_once()
            else:
                tv._run.assert_any_call('--set-stream-path', 'phys-addr=' + source)
            self.assertIsNone(tv._browse_previous)

    def test_manual_tv_change_releases_browsing_lease_without_restoration(self):
        for state in ({'off': True}, {'off': False, 'active_source': '0.0.0.0'}):
            tv = self.controller()
            session = tv._browse_previous = {'off': False, 'source': '0.0.0.0', 'address': '3.0.0.0'}
            tv._observed_state = Mock(return_value=state)
            self.assertIsNone(tv.browsing_session())
            with patch('threading.Thread') as thread:
                tv.restore_browsing(session)
            thread.assert_not_called()

    def test_idle_restore_is_superseded_by_button_or_incoming_call(self):
        for incoming in (False, True):
            tv = self.controller()
            baseline = tv._browse_previous = {'off': True, 'source': '0.0.0.0', 'address': '3.0.0.0'}
            with patch('threading.Thread'), patch.object(Path, 'exists', return_value=True):
                tv.restore_browsing(baseline)
                old = tv._cancel
                self.assertIsNone(tv.browsing_session())
                if incoming:
                    tv.wake()
                    self.assertIs(tv._previous, baseline)
                    self.assertIsNone(tv._browse_previous)
                else:
                    self.assertTrue(tv.handle_button(Mock()))
                    self.assertEqual(tv._browse_previous, baseline)
                    self.assertIsNot(tv._browse_previous, baseline)
                tv._run.reset_mock()
                tv._restore(old, browsing=True)
                tv._run.assert_not_called()
                self.assertIsNot(old, tv._cancel)

    def test_superseded_button_check_cannot_wake_or_dispatch(self):
        tv = self.controller()
        old = tv._cancel
        tv._cancel = threading.Event()
        action = Mock()
        tv._button_worker(old, action, False)
        action.assert_not_called()
        tv._run.assert_not_called()

    def test_failed_or_disconnected_cec_does_not_disable_controls(self):
        for response in ('f.f.f.f', subprocess.TimeoutExpired('cec-ctl', 4)):
            tv = self.controller()
            if isinstance(response, Exception):
                tv._run.side_effect = response
            else:
                tv._run.return_value = response
            action = Mock()
            with patch('logging.warning'):
                tv._button_worker(tv._cancel, action, False)
            action.assert_called_once()

    def test_visibility_result_cannot_answer_a_new_call_or_reset_enrollment(self):
        app = SimpleNamespace(closed=False, generation=3, model=TerminalModel(), press=Mock())
        app.physical_press=app.press
        state = app.model.state
        ManagementLoop.handle_worker_message(app, 'tv-button', (3, state, 'green'))
        app.press.assert_called_once_with('green')
        app.press.reset_mock()
        ManagementLoop.handle_worker_message(app, 'tv-button', (2, state, 'green'))
        app.model.incoming = Mock()
        from zmala_terminal.common.model import State
        app.model.state = State.RINGING
        ManagementLoop.handle_worker_message(app, 'tv-button', (3, state, 'green'))
        app.press.assert_not_called()

    def test_pointer_first_press_only_reveals_hidden_tv(self):
        from zmala_terminal.common.main import Terminal
        app = SimpleNamespace(pointer_serial=0, keys_down=set(), volume_control=Mock(),
                              remote_setup_blocked=lambda: False, setup_stage=None,
                              cancel_settings_hold=Mock(), generation=1, model=TerminalModel(),
                              tv_control=Mock(), messages=Mock(), closed=False)
        app.input_activity = lambda: Terminal.input_activity(app)
        app.tv_control.handle_button.return_value = True
        Terminal.pointer_button(app, True)
        app.volume_control.pointer.assert_not_called()
        app.cancel_settings_hold.assert_called_once()
        # Repeated down events cannot start volume or restart TV switching.
        Terminal.pointer_button(app, True)
        app.tv_control.handle_button.assert_called_once()
        Terminal.pointer_button(app, False)
        app.volume_control.pointer.assert_called_once_with(False)
        # Once visible, the NEXT deliberate click opens the volume page normally.
        app.tv_control.handle_button.return_value = False
        Terminal.pointer_button(app, True)
        app.volume_control.pointer.assert_called_with(True)

    def test_delayed_pointer_visibility_requires_same_click_context(self):
        from zmala_terminal.common.main import Terminal
        app = SimpleNamespace(pointer_serial=1, keys_down={'pointer'}, volume_control=Mock(),
                              generation=1, model=TerminalModel(), closed=False)
        state = app.model.state
        Terminal.pointer_visible(app, 1, state, 1)
        app.volume_control.pointer.assert_called_once_with(True)
        app.volume_control.reset_mock()
        for generation, serial, held in ((0, 1, True), (1, 0, True)):
            app.keys_down = {'pointer'} if held else set()
            Terminal.pointer_visible(app, generation, state, serial)
        app.volume_control.pointer.assert_not_called()
        app.keys_down=set()
        Terminal.pointer_visible(app,1,state,1)
        self.assertEqual([x.args for x in app.volume_control.pointer.call_args_list],[(True,),(False,)])

    def call_app(self):
        model = TerminalModel()
        model.configure(config())
        engine = Mock(call='call')
        engine.hold_call.side_effect = lambda call: setattr(engine, 'call', call)
        app = CallControl()
        app.model, app.engine, app.tv_control = model, engine, Mock()
        app.setup_stage, app.root, app.render = None, Mock(), Mock()
        app.missed_calls_store, app.dial_serial = Mock(), 0
        return app

    def test_rejection_restores_without_waiting_for_sip_end(self):
        app = self.call_app()
        CallControl.call_event(app, 'call', 1, 'alice', 'family.test')
        CallControl.action(app, app.model.button('red'))
        app.tv_control.cancel.assert_called_once()
        app.engine.end.assert_called_once_with(decline=True)

    def test_acceptance_preserves_tv_until_the_call_ends(self):
        for ending in (13, 14, 19):
            with self.subTest(ending=ending):
                app = self.call_app()
                CallControl.call_event(app, 'call', 1, 'alice', 'family.test')
                CallControl.action(app, app.model.button('green'))
                CallControl.call_event(app, 'call', 7, 'alice', 'family.test')
                CallControl.call_event(app, 'call', 8, 'alice', 'family.test')
                app.tv_control.cancel.assert_not_called()
                CallControl.call_event(app, 'call', ending, 'alice', 'family.test')
                app.tv_control.cancel.assert_called_once()

    def test_ending_without_sip_call_still_restores_tv(self):
        app = self.call_app()
        app.engine.call = None
        CallControl.action(app, 'end')
        app.tv_control.cancel.assert_called_once()

    def test_already_watching_terminal_needs_no_cec_changes(self):
        tv = self.controller()
        tv._previous_power = Mock(return_value=False)
        tv._previous_source = Mock(return_value='3.0.0.0')
        tv._worker(tv._cancel)
        self.assertFalse(tv._changed)
        tv._run.assert_has_calls([
            unittest.mock.call('--physical-address'),
            unittest.mock.call('--to', '0', '--give-device-power-status')])
        self.assertEqual(tv._run.call_count, 2)
        tv._restore(tv._cancel)
        self.assertEqual(tv._run.call_count, 2)

    def test_cec_sequences_never_control_volume_or_mute(self):
        tv = self.controller()
        tv._cancel.wait = Mock(return_value=False)
        tv._previous_power = Mock(return_value=False)
        tv._previous_source = Mock(return_value='1.0.0.0')
        tv._restore_wait = Mock(return_value=True)
        tv._worker(tv._cancel)
        tv._restore(tv._cancel)
        arguments = ' '.join(str(call.args) for call in tv._run.call_args_list)
        for prohibited in ('volume', 'mute', 'user-control', 'system-audio'):
            self.assertNotIn(prohibited, arguments)

    def test_wake_uses_connector_address_and_retries(self):
        tv = self.controller()
        cancel = Mock()
        cancel.is_set.return_value = False
        cancel.wait.return_value = False
        tv._worker(cancel)
        tv._run.assert_any_call('--to', '0', '--image-view-on')
        selected = [call for call in tv._run.call_args_list if call.args[0] == '--active-source']
        self.assertEqual(len(selected), 6)
        self.assertTrue(all(call.args == ('--active-source', 'phys-addr=3.0.0.0') for call in selected))

    def test_broadcast_selection_uses_paired_fallback_only_for_awake_tuner(self):
        for off, source, expected in ((False, '0.0.0.0', True), (True, '0.0.0.0', False),
                                      (False, '1.0.0.0', False), (None, None, False)):
            tv = self.controller()
            tv._previous_power = Mock(return_value=off)
            tv._previous_source = Mock(return_value=source)
            tv._cancel.wait = Mock(return_value=False)
            tv._worker(tv._cancel, restore=False)
            self.assertEqual(tv._samsung.select_terminal.called, expected)
            if expected:
                address, current = tv._samsung.select_terminal.call_args.args
                self.assertEqual(address, '3.0.0.0')
                self.assertTrue(current())
                tv._cancel.set()
                self.assertFalse(current())

    def test_call_ending_cancels_retries(self):
        tv = self.controller()
        cancel = threading.Event()
        def run(*args):
            if '--image-view-on' in args:
                cancel.set()
            return '2.0.0.0'
        tv._run.side_effect = run
        tv._worker(cancel)
        self.assertFalse(any(call.args[0] == '--active-source' for call in tv._run.call_args_list))

    def test_awake_tv_gets_one_settled_retry_before_audio_starts(self):
        tv = self.controller()
        # Ignore the host's live observer when this test runs on a real Pi.
        tv._previous_source = Mock(return_value='1.0.0.0')
        tv._run.side_effect = lambda *args: ('pwr-state: on (0x00)' if '--give-device-power-status' in args else '2.0.0.0')
        cancel = Mock()
        cancel.is_set.return_value = False
        cancel.wait.return_value = False
        tv._worker(cancel)
        selected = [call for call in tv._run.call_args_list if call.args[0] == '--active-source']
        self.assertEqual(len(selected), 2)
        self.assertEqual(cancel.wait.call_args_list[-1].args, (2,))

    def test_disconnected_display_does_not_send_wake(self):
        tv = self.controller()
        tv._run.return_value = 'f.f.f.f'
        tv._worker(threading.Event())
        self.assertEqual(tv._run.call_count, 1)

    def test_timeout_does_not_escape_worker(self):
        tv = self.controller()
        tv._run.side_effect = subprocess.TimeoutExpired('cec-ctl', 4)
        with self.assertLogs(level='WARNING'):
            tv._worker(threading.Event())

    def test_transmit_nack_is_failure_even_with_success_exit(self):
        tv = self.controller()
        with patch('subprocess.run', return_value=subprocess.CompletedProcess([], 0, 'Tx, NACK', '')):
            with self.assertRaises(RuntimeError):
                TVControl._run(tv, '--image-view-on')

    def test_closed_controller_never_starts_worker(self):
        tv = self.controller()
        tv.close()
        with patch('threading.Thread') as thread:
            tv.wake()
        thread.assert_not_called()

    def remembered(self, off=False, source='1.0.0.0'):
        tv = self.controller()
        tv._previous = {'off': off, 'source': source, 'address': '2.0.0.0'}
        tv._changed = True
        tv._restore_wait = Mock(return_value=True)
        return tv

    def test_previous_standby_is_restored_once(self):
        tv = self.remembered(off=True, source='2.0.0.0')
        tv._restore(tv._cancel)
        tv._restore(tv._cancel)
        self.assertEqual(sum(call.args == ('--to', '0', '--standby') for call in tv._run.call_args_list), 4)

    def test_standby_restores_the_remembered_input_first(self):
        tv = self.remembered(off=True)
        tv._restore(tv._cancel)
        calls = [call.args for call in tv._run.call_args_list]
        self.assertLess(calls.index(('--active-source', 'phys-addr=1.0.0.0')),
                        calls.index(('--to', '0', '--standby')))

    def test_previous_input_is_restored_without_switching_tv_off(self):
        tv = self.remembered()
        tv._restore(tv._cancel)
        tv._run.assert_any_call('--set-stream-path', 'phys-addr=1.0.0.0')
        tv._run.assert_any_call('--active-source', 'phys-addr=1.0.0.0')
        self.assertFalse(any('--standby' in call.args for call in tv._run.call_args_list))

    def test_already_on_terminal_input_does_not_change_tv_at_end(self):
        tv = self.remembered(source='2.0.0.0')
        tv._restore(tv._cancel)
        tv._run.assert_not_called()

    def test_native_tv_source_returns_to_broadcast_without_changing_channel(self):
        tv = self.remembered(source='0.0.0.0')
        tv._restore(tv._cancel)
        tv._run.assert_called_once_with('--to', '0', '--inactive-source', 'phys-addr=2.0.0.0')
        tv._restore_wait.assert_called_once_with(2, tv._cancel)

    def test_hdmi_restoration_does_not_select_broadcast(self):
        tv = self.remembered()
        tv._restore(tv._cancel)
        self.assertFalse(any('--user-control-pressed' in call.args for call in tv._run.call_args_list))
        tv._samsung.restore_broadcast.assert_not_called()

    def test_paired_samsung_restores_tuner_after_cec_release(self):
        tv = self.remembered(source='0.0.0.0')
        tv._samsung.restore_broadcast.return_value = True
        tv._restore(tv._cancel)
        tv._samsung.restore_broadcast.assert_called_once()
        self.assertTrue(tv._samsung.restore_broadcast.call_args.args[0]())
        tv._restore_wait.assert_any_call(3, tv._cancel)

    def test_network_failure_still_allows_standby_restoration(self):
        tv = self.remembered(off=True, source='0.0.0.0')
        tv._samsung.restore_broadcast.return_value = False
        tv._restore(tv._cancel)
        tv._run.assert_any_call('--to', '0', '--standby')

    def test_new_call_during_network_restore_prevents_standby(self):
        tv = self.remembered(off=True, source='0.0.0.0')
        def incoming(is_current):
            tv._cancel = threading.Event()
            self.assertFalse(is_current())
            return False
        tv._samsung.restore_broadcast.side_effect = incoming
        tv._restore(tv._cancel)
        self.assertFalse(any('--standby' in call.args for call in tv._run.call_args_list))
        self.assertIsNotNone(tv._previous)

    def test_network_standby_fallback_requires_settled_on(self):
        for power, expected in (('on', True), ('standby', False),
                                ('to-on', False), ('to-standby', False), ('unknown', False)):
            with self.subTest(power=power):
                tv = self.remembered(off=True, source='2.0.0.0')
                tv._run.return_value = 'pwr-state: ' + power + ' (0x00)'
                tv._restore(tv._cancel)
                self.assertEqual(tv._samsung.standby_if_on.called, expected)
                self.assertEqual(tv._tv_is_on(), expected)

    def test_new_incoming_call_supersedes_old_restore_and_keeps_baseline(self):
        tv = self.remembered(off=True)
        old = tv._cancel
        tv._cancel = threading.Event()
        tv._restore(old)
        tv._run.assert_not_called()
        self.assertTrue(tv._previous['off'])

    def test_cancelled_wake_before_any_change_sends_no_restore(self):
        tv = self.remembered(off=True)
        tv._changed = False
        tv._restore(tv._cancel)
        tv._run.assert_not_called()

    def test_unknown_power_and_input_never_guesses_or_sends_standby(self):
        tv = self.remembered(off=None, source=None)
        with self.assertLogs(level='WARNING'):
            tv._restore(tv._cancel)
        tv._run.assert_called_once_with('--to', '0', '--inactive-source', 'phys-addr=2.0.0.0')

    def test_restoration_failure_is_contained(self):
        tv = self.remembered(off=True)
        tv._run.side_effect = subprocess.TimeoutExpired('cec-ctl', 4)
        with self.assertLogs(level='WARNING'):
            tv._restore(tv._cancel)
        self.assertIsNone(tv._previous)

    def test_live_routing_cache_only(self):
        with tempfile.TemporaryDirectory() as directory:
            tv = self.controller()
            tv.state_file = Path(directory) / 'state.json'
            for age, expected in ((0, '1.0.0.0'), (10, None)):
                tv.state_file.write_text(json.dumps({'device': '/dev/cec0', 'active_source': '1.0.0.0',
                                                     'updated_at': time.time() - age}), encoding='utf-8')
                self.assertEqual(tv._previous_source(), expected)

    def test_routing_parser_tracks_announcements_not_stream_path_requests(self):
        state = RoutingState()
        for line in ('Transmitted by Playback Device 1 to all (4 to 15): ACTIVE_SOURCE (0x82):',
                     '\tphys-addr: 1.0.0.0'):
            state.consume(line)
        self.assertEqual(state.source, '1.0.0.0')
        for line in ('Received from TV to all (0 to 15): ROUTING_CHANGE (0x80):',
                     '\torig-phys-addr: 1.0.0.0', '\tnew-phys-addr: 3.0.0.0'):
            state.consume(line)
        self.assertEqual(state.source, '3.0.0.0')

        for line in ('Transmitted by Playback Device 1 to all (4 to 15): SET_STREAM_PATH (0x86):',
                     '\tphys-addr: 2.0.0.0'):
            state.consume(line)
        self.assertEqual(state.source, '3.0.0.0')

    def test_transition_reply_does_not_erase_observed_standby(self):
        state = RoutingState()
        state.consume('Transmitted by Playback Device 1 to TV (4 to 0): STANDBY (0x36)')
        state.consume('Received from TV to Playback Device 1 (0 to 4): REPORT_POWER_STATUS (0x90)')
        state.consume('pwr-state: to-on (0x02)')
        self.assertTrue(state.off)
        tv = self.controller()
        tv._observed_state = Mock(return_value={'off': True})
        self.assertTrue(tv._previous_power('pwr-state: to-on (0x02)'))

    def test_inactive_source_clears_only_the_released_route(self):
        state = RoutingState()
        state.source = '2.0.0.0'
        for address, expected in [('1.0.0.0', '2.0.0.0'), ('2.0.0.0', None)]:
            state.consume('Transmitted by Playback Device 1 to TV (4 to 0): INACTIVE_SOURCE (0x9d):')
            state.consume('phys-addr: ' + address)
            self.assertEqual(state.source, expected)

    def test_cancel_during_adapter_configuration_still_restores(self):
        tv = self.controller()
        def run(*args):
            if '--playback' in args:
                tv._cancel.set()
            if '--give-device-power-status' in args:
                return 'pwr-state: standby (0x01)'
            return '2.0.0.0'
        tv._run.side_effect = run
        tv._restore_wait = Mock(return_value=True)
        tv._worker(tv._cancel)
        self.assertTrue(tv._changed)
        tv._restore(tv._cancel)
        tv._run.assert_any_call('--to', '0', '--standby')

    def test_restore_settling_wait_stops_when_another_call_arrives(self):
        tv = self.controller()
        old_cancel = tv._cancel
        tv._cancel = threading.Event()
        self.assertFalse(tv._restore_wait(5, old_cancel))
        self.assertTrue(tv._restore_wait(0, tv._cancel))
