# @test T-LLT-066
# @requirements LLR-TERM-NAV-007, LLR-TERM-CALL-012, LLR-TERM-CALL-014, LLR-TERM-HISTORY-015, LLR-TERM-HISTORY-017, LLR-TERM-HISTORY-021, LLR-TERM-HISTORY-022, LLR-TERM-HISTORY-024, LLR-TERM-POWER-014, LLR-TERM-TV-034
# @environment portable
# @plan Drive real call orchestration and the configured model with fake native SIP, HTTP preflight, scheduling and USB boundaries. Verify incoming permissions, call-handle ownership, persisted notifications, timeout validation, stale/cancelled USB retries, end/error cleanup and callback target/response validation. For unanswered outgoing attempts, inject remote rejection/end, delayed/immediate caller cancellation, synchronous end callbacks, prior connection, incoming decline, permission removal and existing pending requests; verify one callback offer, both choices and late-event fencing. Check callback-availability prompts do not interrupt active settings or calls.
# @pass Native operations and persisted results match assertions; no actual call, media, TV or network side effects occur.
# The TV retry predicate remains true only for the same still-ringing native call; answer, replacement, end and engine teardown invalidate it.
from zmala_terminal.common.callbacks import CallbackController
import json
import queue
import unittest
from unittest.mock import Mock, patch
from zmala_terminal.common import call_control
from zmala_terminal.common.model import TerminalModel, State
from tests.terminal.LLT.test_terminal import config


class CallOrchestrationTests(unittest.TestCase):
    def test_tv_retries_belong_only_to_the_same_ringing_call(self):
        c = self.controller()
        c.call_event(42, 1, 'alice', 'family.test')
        ringing = c.tv_control.wake.call_args.kwargs['ringing']
        self.assertTrue(ringing())
        for state in (State.CONNECTING, State.IN_CALL, State.STOPPING, State.HOME):
            c.model.state = state
            self.assertFalse(ringing(), state)
        c.model.state = State.RINGING
        c.engine.call = 43
        self.assertFalse(ringing())
        c.engine = None
        self.assertFalse(ringing())

    def controller(self):
        c=call_control.CallControl(); c.callbacks = CallbackController(); c.model=TerminalModel(); c.model.configure(config())
        c.root=Mock(); c.render=Mock(); c.missed_calls_store=Mock(); c.engine=Mock(call=41,registered=True)
        c.engine.hold_call.side_effect=lambda handle:setattr(c.engine,'call',handle)
        c.usb_power=Mock(); c.tv_control=Mock(); c.settings_hold=Mock(started=None); c.settings_open=False
        c.configuration=Mock(); c.messages=queue.Queue(); c.setup_stage=None; c.closed=False; c.notice=''; c.carousel_motion=None
        c.generation=1; c.dial_serial=2; c.callbacks.serial=3; c.outgoing_deadline=None; c.server_seen=100
        c.callbacks.requests=[]; c.callbacks.seen=set(); c.callback_alert=None; c.last_button=0
        return c

    def test_notifications_require_matching_domain_and_contact_permission(self):
        c=self.controller(); c.registration_event(True); self.assertTrue(c.last_registration)
        c.root.after_idle.assert_called_with(c.render)
        for user,domain in [('alice','other.test'),('stranger','family.test')]: c.message_event(user,domain)
        c.missed_calls_store.save.assert_not_called()
        c.message_event('alice','FAMILY.TEST'); self.assertIn('alice',c.model.notifications)
        c.missed_calls_store.save.assert_called_once_with(c.model.config,c.model.notifications)
        c.setup_stage='wifi'; c.message_event('alice','family.test'); self.assertEqual(c.missed_calls_store.save.call_count,1)

    def test_incoming_call_declines_setup_unknown_or_busy_and_wakes_only_accepted_calls(self):
        c=self.controller(); c.setup_stage='wifi'; c.call_event(42,1,'alice','family.test'); c.engine.call_decline.assert_called_with(42,6)
        c.setup_stage=None; c.call_event(42,1,'unknown','family.test'); c.engine.call_decline.assert_called_with(42,2)
        c.usb_power.require.assert_not_called(); c.call_event(42,1,'alice','family.test')
        c.usb_power.require.assert_called_once_with(urgent=True); c.settings_hold.clear.assert_called_once()
        self.assertEqual(c.engine.call,42); self.assertEqual(c.model.state,State.RINGING); c.tv_control.wake.assert_called_once()
        c.root.after_idle.call_args_list[-2].args[0](); c.root.lift.assert_called_once()
        c.call_event(43,1,'alice','family.test'); c.engine.call_decline.assert_called_with(43,6)

    def test_native_events_ignore_unowned_calls_and_persist_terminal_states(self):
        c=self.controller()
        for state in (3,4,5,6): c.call_event(41,state,'alice','family.test')
        c.root.after_idle.assert_not_called(); c.model.incoming('alice','family.test')
        c.call_event(99,7,'alice','family.test'); self.assertEqual(c.model.state,State.RINGING)
        c.model.mark_notification('alice')
        c.call_event(41,7,'alice','family.test'); self.assertEqual(c.model.state,State.IN_CALL)
        c.missed_calls_store.save.assert_called(); self.assertIsNone(c.outgoing_deadline)
        c.model.state=State.STOPPING; c.call_event(41,8,'alice','family.test'); c.engine.end.assert_called_once()
        for state,notice in [(13,'unavailable'),(14,''),(19,'')]:
            c.engine.call=41; c.model.state=State.IN_CALL; c.call_event(41,state,'alice','family.test')
            self.assertEqual(c.notice,notice); self.assertIsNone(c.engine.call); self.assertEqual(c.model.state,State.HOME)
        self.assertEqual(c.tv_control.cancel.call_count,3)

    def test_preflight_validates_contact_permissions_and_integer_timeout(self):
        for reply,available,timeout in [({'id':'alice','online':True,'can_call':True,'ring_timeout':660},True,660),
                                       ({'id':'alice','online':True,'can_call':True,'ring_timeout':True},True,60),
                                       ({'id':'alice','online':True,'can_call':True,'ring_timeout':661},True,60),
                                       ({'id':'other','online':True,'can_call':True},False,60),(None,False,60)]:
            c=self.controller(); c.model.button('green'); c.model.button('green')
            c.configuration.request.return_value=json.dumps(reply)
            with patch.object(call_control.threading,'Thread',side_effect=lambda **kw:Mock(start=kw['target'])),patch.object(call_control.time,'monotonic',return_value=100): c.begin_dial()
            kind,result=c.messages.get_nowait(); self.assertEqual(kind,'dial-ready'); self.assertEqual(result[:2],(1,3)); self.assertEqual(result[3:],(available,timeout))
            self.assertEqual(c.outgoing_deadline,160); c.configuration.request.assert_called_once_with('/api/contacts/alice/availability')

    def test_usb_delayed_answer_cannot_answer_replaced_cancelled_or_reset_call(self):
        for change in ['closed','generation','call','state',None]:
            c=self.controller(); c.model.state=State.CONNECTING; c.usb_media_ready=Mock(return_value=False)
            c.answer_when_ready(); delay,retry=c.root.after.call_args.args; self.assertEqual(delay,100); c.engine.answer.assert_not_called()
            if change=='closed': c.closed=True
            elif change=='generation': c.generation+=1
            elif change=='call': c.engine.call=99
            elif change=='state': c.model.state=State.STOPPING
            c.usb_media_ready.return_value=True; retry()
            self.assertEqual(c.engine.answer.call_count,0 if change else 1)
            self.assertEqual(c.usb_power.stop_ringing.call_count,0 if change else 1)

    def test_dial_waits_for_usb_and_revalidates_tokens_before_native_start(self):
        c=self.controller(); c.model.button('green'); c.model.button('green'); contact=c.model.contact
        c.usb_media_ready=Mock(return_value=False); c.dial_ready(1,2,contact,True,120)
        c.engine.dial.assert_not_called(); retry=c.root.after.call_args.args[1]
        c.usb_media_ready.return_value=True
        with patch.object(call_control.time,'monotonic',return_value=100): retry()
        c.engine.dial.assert_called_once_with(contact['sip_uri']); self.assertEqual(c.outgoing_deadline,220)
        c.engine.dial.side_effect=RuntimeError('device removed')
        with self.assertLogs(level='ERROR'): c.dial_ready(1,2,contact,True)
        self.assertEqual(c.notice,'unavailable'); self.assertIsNone(c.outgoing_deadline); self.assertEqual(c.model.state,State.CONFIRM_CALLBACK)
        c.model.state=State.CALLING; c.engine.registered=False; c.dial_ready(1,2,contact,True)
        self.assertEqual(c.notice,'offline'); self.assertFalse(c.model.contacts[0]['online'])

    def test_action_routes_call_controls_and_cleanup_when_native_answer_fails(self):
        c=self.controller(); c.begin_callback=Mock(); c.begin_dial=Mock(); c.answer_when_ready=Mock()
        for action in ['request_callback','cancel_callback','dial','answer']: c.action(action)
        self.assertEqual([call.kwargs for call in c.begin_callback.call_args_list],[{'cancel':False},{'cancel':True}]); c.begin_dial.assert_called_once(); c.answer_when_ready.assert_called_once()
        for action in ['end','decline']:
            c.engine.call=None; c.action(action); c.engine.end.assert_called_with(decline=action=='decline'); self.assertEqual(c.model.state,State.HOME)
        c.engine.call=41; c.answer_when_ready.side_effect=RuntimeError('SDK failure')
        with self.assertLogs(level='ERROR'): c.action('answer')
        c.engine.end.assert_called_with(); self.assertEqual(c.notice,'unavailable'); c.tv_control.cancel.assert_called()
        c.engine=None; c.begin_dial.reset_mock(); c.action('dial'); c.action(None); c.begin_dial.assert_not_called()

    def outgoing(self):
        c = self.controller(); c.model.button('green'); c.model.button('green')
        return c

    def test_unanswered_remote_end_offers_callback_once_for_original_contact(self):
        for state in (13, 14, 19):
            c = self.outgoing(); c.call_event(41, state, 'alice', 'family.test')
            self.assertEqual(c.model.state, State.CONFIRM_CALLBACK)
            self.assertTrue(c.model.callback_after_call); self.assertEqual(c.model.contact['id'], 'alice')
            self.assertIsNone(c.engine.call); self.assertFalse(c.model.outgoing_attempt)
            c.call_event(41, 19, 'alice', 'family.test')
            self.assertEqual(c.model.state, State.CONFIRM_CALLBACK)
            self.assertTrue(c.finish_call())
            c.begin_callback = Mock()
            c.action(c.model.button('green')); c.begin_callback.assert_called_once_with(cancel=False)

    def test_caller_cancel_waits_for_native_end_and_no_closes_without_request(self):
        for immediate in (False, True):
            c = self.outgoing()
            if immediate: c.engine.end.side_effect = lambda **kw: setattr(c.engine, 'call', None)
            c.action(c.model.button('red'))
            if not immediate:
                self.assertEqual(c.model.state, State.STOPPING)
                c.call_event(41, 14, 'alice', 'family.test')
            self.assertEqual(c.model.state, State.CONFIRM_CALLBACK)
            self.assertIsNone(c.model.button('red')); self.assertEqual(c.model.state, State.HOME)
            c.configuration.request.assert_not_called()
            c.dial_ready(1, 2, dict(c.model.selected), True); c.engine.dial.assert_not_called()

    def test_synchronous_end_does_not_dismiss_its_own_callback_offer(self):
        c = self.outgoing()
        c.engine.end.side_effect = lambda **kw: c.call_event(41, 14, 'alice', 'family.test')
        c.action(c.model.button('red'))
        self.assertEqual(c.model.state, State.CONFIRM_CALLBACK); self.assertTrue(c.model.callback_after_call)

    def test_connected_calls_incoming_declines_and_existing_requests_do_not_offer(self):
        c = self.outgoing(); c.call_event(41, 7, 'alice', 'family.test')
        c.model.button('red'); c.call_event(41, 14, 'alice', 'family.test')
        self.assertEqual(c.model.state, State.HOME)
        c = self.controller(); c.model.incoming('alice', 'family.test')
        c.model.button('red'); c.call_event(41, 14, 'alice', 'family.test')
        self.assertEqual(c.model.state, State.HOME)
        c = self.outgoing(); c.model.config['callbacks'] = [
            {'from': c.model.config['sip']['username'], 'to': 'alice', 'status': 'pending'}]
        c.call_event(41, 14, 'alice', 'family.test'); self.assertEqual(c.model.state, State.HOME)
        c = self.outgoing(); c.model.config['contacts'] = []
        c.call_event(41, 14, 'alice', 'family.test'); self.assertEqual(c.model.state, State.HOME)

    def test_callback_worker_validates_reply_and_reports_cancelled_request_identity(self):
        request={'id':'11111111-1111-4111-8111-111111111111','from':'terminal','to':'alice','status':'pending','ready':False}
        for cancel,payload in [(False,request),(False,request|{'to':'unknown'}),(False,[]),(True,{'ok':True}),(True,{'ok':False})]:
            c=self.controller(); c.model.config['callbacks']=[request] if cancel else []
            c.model.config['contacts'][0]['online']=False; c.model.button('green')
            c.configuration.request.return_value=json.dumps(payload)
            with patch.object(call_control.threading,'Thread',side_effect=lambda **kw:Mock(start=kw['target'])): c.begin_callback(cancel)
            _,result=c.messages.get_nowait(); self.assertEqual(result[:3],(1,4,'alice'))
            self.assertEqual(result[3],payload==({'ok':True} if cancel else request)); self.assertEqual(result[-1],request['id'] if cancel else None)

    def test_ready_callback_prompt_waits_for_idle_and_only_targets_online_contact_once(self):
        c=self.controller(); c.callbacks.requests=[{'id':'1','from':'terminal','to':'alice','ready':True}]
        with patch.object(call_control.time,'monotonic',return_value=101):
            c.settings_open=True; c.show_callback_available(101); self.assertIsNone(c.callback_alert)
            c.settings_open=False; c.show_callback_available(101); self.assertEqual(c.callback_alert,('Alice',111))
            c.callback_alert=None; c.show_callback_available(102); self.assertIsNone(c.callback_alert)
        self.assertEqual(c.callbacks.seen,{'1'}); c.render.assert_called_once()


if __name__=='__main__': unittest.main()
