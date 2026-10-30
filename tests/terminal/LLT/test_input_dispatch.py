# @test T-LLT-074
# @requirements LLR-TERM-REMOTE-015, LLR-TERM-REMOTE-016, LLR-TERM-NAV-004, LLR-TERM-NAV-005, LLR-TERM-NAV-007, LLR-TERM-TV-026, LLR-TERM-POWER-014
# @environment portable
# @plan Invoke real physical-input dispatch with a configured model and mocked Tk/HID/TV boundaries. Verify wake-only presses, confirmation debounce/repeat cancellation, pairing-test isolation, pointer-generation guards and fullscreen/cancel dispatch. Send three released arrows less than 80 ms apart in both directions during animation; verify one move per press, held-repeat suppression, wrap and confirmation of the final target. Distinguish equal-time X11 autorepeat pairs from later-time clicks while release callbacks are waiting for idle. Verify volume consumes physical input through both immediate and delayed dispatch, while internal cancellation remains separate. Change contact presence between confirmation presses and assert the stale selection cannot start a call.
# @pass All action, activity, queue, callback and model assertions pass without real remote events, TV commands or native calls.
import queue
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from zmala_terminal.common import input_control
from zmala_terminal.common.model import State, TerminalModel
from tests.terminal.LLT.test_terminal import config


class InputDispatchTests(unittest.TestCase):
    def controller(self):
        c=input_control.InputControl(); c.root=Mock(); c.model=TerminalModel(); c.model.configure(config())
        c.setup_stage=None; c.closed=False; c.settings_open=False; c.settings_hold=Mock(capturing=False)
        c.keys_down=set(); c.key_release_jobs={}; c.last_key={}; c.generation=3; c.pointer_serial=4; c.messages=queue.Queue()
        c.usb_power=Mock(); c.tv_control=Mock(); c.tv_control.handle_button.return_value=False; c.volume_control=Mock()
        c.engine=Mock(registered=True); c.carousel_motion=None; c.notice='old'; c.callback_alert=None; c.missed_calls_store=Mock()
        for name in ('press','cancel_settings_hold','action','render','resize','queue_keyrelease','keyrelease','input_focus_lost','remote_test_event'):
            setattr(c,name,Mock())
        c.remote_setup_blocked=Mock(return_value=False); c.tv_setup_button=Mock(return_value=False); c.contact_online=Mock(return_value=True)
        return c

    def test_bindings_route_press_release_focus_and_volume_enable_gate(self):
        c=self.controller()
        with patch.object(input_control,'VolumeControl') as volume,patch.object(input_control,'PresenterInput') as presenter:
            c.bind_inputs()
        enabled=volume.call_args.args[1]; self.assertTrue(enabled()); c.setup_stage='wifi'; self.assertFalse(enabled()); c.setup_stage=None; c.settings_open=True; self.assertFalse(enabled())
        self.assertEqual(presenter.call_args.args[1:4],(c.keypress,c.keyrelease,c.pointer_button))
        c.keypress=Mock()
        for call in c.root.bind_all.call_args_list:
            key,callback=call.args
            if key=='<Left>': callback(SimpleNamespace(time=123)); c.keypress.assert_called_once_with('left',123)
            elif key=='<KeyRelease-Return>': callback(SimpleNamespace(time=124)); c.queue_keyrelease.assert_called_once_with('green',124)
        next(call.args[1] for call in c.root.bind.call_args_list if call.args[0]=='<FocusOut>')(None); c.input_focus_lost.assert_called_once()

    def test_keypress_activity_precedes_gates_and_repeat_is_consumed(self):
        c=self.controller(); c.remote_setup_blocked.return_value=True
        self.assertEqual(c.keypress('green'),'break'); c.usb_power.require.assert_called_once_with(urgent=True, reason='remote/keyboard input'); c.press.assert_not_called()
        c.remote_setup_blocked.return_value=False; c.key_release_jobs['green']=('pending',100)
        with patch.object(input_control.time,'monotonic',return_value=100): c.keypress('green'); c.keypress('green')
        c.root.after_cancel.assert_called_once_with('pending'); c.press.assert_called_once_with('green')
        c.keys_down.clear()
        with patch.object(input_control.time,'monotonic',return_value=100.01): c.keypress('green')
        self.assertEqual(c.press.call_count,1); self.assertEqual(c.last_button,100.01)
        c.keys_down.clear(); c.tv_setup_button.return_value=True; c.keypress('red'); self.assertEqual(c.press.call_count,1)
        c.keys_down.clear(); c.tv_setup_button.return_value=False; c.tv_control.handle_button.return_value=True; c.model.state=State.IN_CALL
        c.keypress('red'); self.assertTrue(c.tv_control.handle_button.call_args.kwargs['preserve_restore'])
        c.tv_control.handle_button.call_args.args[0](); self.assertEqual(c.messages.get_nowait(),('tv-button',(3,State.IN_CALL,'red')))

    def test_pointer_delayed_visibility_keeps_click_but_rejects_newer_context(self):
        c=self.controller(); c.tv_control.handle_button.return_value=True; c.pointer_button(True)
        callback=c.tv_control.handle_button.call_args.args[0]; c.pointer_button(True); self.assertEqual(c.tv_control.handle_button.call_count,1)
        callback(); _,tokens=c.messages.get_nowait(); c.pointer_visible(*tokens); c.volume_control.pointer.assert_called_once_with(True)
        c.pointer_button(False); c.volume_control.pointer.reset_mock()
        c.pointer_visible(*tokens)
        self.assertEqual([x.args for x in c.volume_control.pointer.call_args_list],[(True,),(False,)])
        c.volume_control.pointer.reset_mock()
        c.tv_control.handle_button.return_value=False; c.pointer_button(True); c.volume_control.pointer.assert_called_once_with(True)
        c.volume_control.pointer.reset_mock();c.pointer_visible(*tokens);c.volume_control.pointer.assert_not_called()
        c.setup_stage='tv'; c.pointer_button(False); c.volume_control.pointer.assert_not_called()

    def test_queued_release_distinguishes_fast_arrows_from_x11_autorepeat(self):
        for button in ('left','right'):
            c=self.controller(); c.keypress(button,100)
            c.key_release_jobs[button]=('repeat-release',200)
            c.keypress(button,200)  # X11 repeat release/down share a timestamp.
            self.assertEqual(c.press.call_count,1)
            for n in (1,2):
                c.key_release_jobs[button]=('real-release',200+n*40)
                c.keypress(button,210+n*40)
            self.assertEqual(c.press.call_count,3)
            self.assertEqual(c.key_release_jobs,{})

    def test_other_keys_cancel_confirmation_without_changing_fullscreen(self):
        c=self.controller(); c.model.state=State.CONFIRMING
        self.assertEqual(c.other_key(None),'break'); c.press.assert_called_with('cancel')
        self.assertEqual(c.toggle_fullscreen(None),'break'); c.root.attributes.assert_not_called()
        c.model.state=State.HOME; c.root.attributes.return_value=False; c.toggle_fullscreen(None); c.root.attributes.assert_called_with('-fullscreen',True)
        c.settings_open=True; c.press.reset_mock(); c.other_key(None); c.press.assert_not_called(); c.volume_activity(); c.usb_power.require.assert_called_with(urgent=True, reason='remote/keyboard input')

    def test_volume_consumes_physical_actions_but_not_the_logical_entry_point(self):
        c=self.controller();c.volume_control.active=True
        for button in ('left','right','green','red'):c.physical_press(button)
        c.press.assert_not_called()
        self.assertEqual([call.args for call in c.volume_control.button.call_args_list],
                         [('left',),('right',),('green',),('red',)])
        c.press('red');c.press.assert_called_once_with('red')
        c.volume_control.active=False;c.physical_press('green')
        c.press.assert_called_with('green')

    def test_carousel_retargets_and_confirming_unavailable_contact_never_dials(self):
        c=self.controller(); settings=config(); settings['contacts'].append(settings['contacts'][0]|{'id':'bob','name':'Bob','sip_uri':'sip:bob@family.test'}); c.model.configure(settings)
        c._press_action('right'); self.assertEqual(c.model.selected['id'],'bob'); self.assertIsNotNone(c.carousel_motion); self.assertEqual(c.notice,'')
        c._press_action('left'); self.assertEqual(c.model.selected['id'],settings['contacts'][0]['id'])
        c._press_action('green'); self.assertIsNone(c.carousel_motion); self.assertEqual(c.model.state,State.CONFIRMING)
        c.engine.registered=False; c.action.reset_mock(); c._press_action('green'); self.assertEqual(c.model.state,State.CONFIRM_CALLBACK); c.action.assert_not_called()
        c.model.ended(); c.contact_online.return_value=False; c._press_action('green'); self.assertEqual(c.model.state,State.CONFIRM_CALLBACK)
        c.model.ended(); c.contact_online.return_value=True; c.engine.registered=True; c._press_action('green')
        c.model.config['contacts']=[]; c.contact_online.return_value=False; c._press_action('green'); self.assertEqual(c.model.state,State.HOME); self.assertEqual(c.notice,'unavailable')

    def test_three_fast_released_arrows_count_and_green_confirms_latest_selection(self):
        for button, direction in (('left', -1), ('right', 1)):
            with self.subTest(button=button):
                c=self.controller(); settings=config()
                settings['contacts']=[settings['contacts'][0]|{'id':str(i)} for i in range(5)]
                c.model.configure(settings); c.volume_control.active=False
                c.press=c._press_action
                for n in range(3):
                    # Each release starts a distinct click. Duplicate downs
                    # during that same click must still be ignored.
                    with patch.object(input_control.time,'monotonic',return_value=100+n*.04):
                        c.keypress(button); c.keypress(button)
                    c.keys_down.discard(button)
                    self.assertEqual(c.model.index, ((n+1)*direction)%5)
                expected=c.model.selected
                c._press_action('green')
                self.assertEqual(c.model.state,State.CONFIRMING)
                self.assertEqual(c.model.contact['id'],expected['id'])
                self.assertIsNone(c.carousel_motion)


if __name__=='__main__': unittest.main()
