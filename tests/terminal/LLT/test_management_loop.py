# @test T-LLT-064
# @requirements LLR-TERM-NET-005, LLR-TERM-COM-007, LLR-TERM-COM-008, LLR-TERM-CALL-012, LLR-TERM-POWER-013, LLR-TERM-MAINT-018
# @environment portable
# @plan Exercise the real UI queue and timer pump with a configured model, virtual clock and recording UI/device boundaries. Verify captured-generation polling, diagnostics publication, worker-failure recovery, rejected stale button/results, USB readiness activity, deferred auto-answer, timer-driven redraw and rescheduling after a tick exception. Verify completed carousel motion and closed terminals do not keep animating.
# @pass Assertions pass without real threads, Tk windows, network or devices; these tests verify scheduling and boundary contracts, not hardware timing.
import copy
import queue
import unittest
from unittest.mock import Mock, patch
from zmala_terminal.common import management
from zmala_terminal.common.model import TerminalModel, State
from tests.terminal.LLT.test_terminal import config


class ManagementPumpTests(unittest.TestCase):
    def loop(self):
        loop=management.ManagementLoop(); loop.model=TerminalModel(); loop.model.configure(config())
        loop.messages=queue.Queue(); loop.generation=3; loop.callback_revision=4; loop.closed=False
        loop.setup_stage=None; loop.scanner=None; loop.settings_open=False; loop.keys_down=set()
        loop.worker_busy=False; loop.network_worker_busy=False; loop.configuration=Mock(cancelled=False)
        loop.engine=Mock(registered=True,call=None); loop.usb_power=Mock(enabled=True,ready=True)
        loop.presenter_input=Mock(battery=75); loop.tv_control=Mock(); loop.tv_control.ready.return_value=True
        loop.pending_config=None; loop.notice=''; loop.callback_alert=None; loop.callback_requests=[]
        loop.server_seen=99; loop.presence_stale=False; loop.last_poll=99; loop.diagnostics={'camera':'ready'}
        loop.outgoing_deadline=None; loop.carousel_motion=None; loop.root=Mock(); loop.case_fan=Mock()
        for name in ('render','draw_connectivity','apply_config','press','action','tick_settings_access',
                     'show_callback_available','update_video_message','iterate_scanner','tick_tv_setup',
                     'update_setup_display','draw_avatar','animate_ringing','tick_tv_idle','local_settings_result',
                     'pointer_visible','dial_ready','setup_result'):
            setattr(loop,name,Mock())
        return loop

    def test_poll_captures_generation_revision_and_status_then_releases_busy_flag(self):
        loop=self.loop(); tasks=[]
        def thread(**kwargs): return Mock(start=lambda:tasks.append(kwargs['target']))
        loop.configuration.fetch.return_value=config()
        with patch.object(management.threading,'Thread',side_effect=thread), patch.object(management,'wifi_link_available',return_value=True):
            loop.poll(); loop.poll(); self.assertEqual(len(tasks),2)
            # Mutation after launch must not leak into the captured report.
            loop.generation=8; loop.diagnostics['camera']='changed'; loop.callback_revision=9
            for task in tasks: task()
        loop.configuration.report.assert_called_once_with({'camera':'ready','state':'home','configuration_version':1})
        loop.drain_messages(); self.assertTrue(loop.worker_busy); self.assertFalse(loop.network_worker_busy)
        loop.apply_config.assert_not_called(); loop.draw_connectivity.assert_not_called()
        loop.handle_worker_message('poll-done',8); self.assertFalse(loop.worker_busy)

    def test_poll_failure_and_cancelled_configuration_never_strand_workers(self):
        for failure,cancelled in ((True,False),(False,True)):
            loop=self.loop(); loop.configuration.cancelled=cancelled
            loop.configuration.fetch.return_value=config()
            if failure: loop.configuration.fetch.side_effect=OSError('offline')
            with patch.object(management.threading,'Thread',side_effect=lambda **kw:Mock(start=kw['target'])), \
                    patch.object(management,'wifi_link_available',side_effect=OSError('wifi unavailable')):
                loop.poll()
            loop.configuration.report.assert_not_called(); loop.drain_messages()
            self.assertFalse(loop.worker_busy); self.assertFalse(loop.network_worker_busy); self.assertIsNone(loop.network_connected)

    def test_dispatch_contract_and_delayed_button_cannot_act_in_a_new_call(self):
        loop=self.loop()
        for kind,name in [('local-settings','local_settings_result'),('tv-pointer','pointer_visible'),
                          ('dial-ready','dial_ready'),('setup','setup_result')]:
            loop.handle_worker_message(kind,('one','two')); getattr(loop,name).assert_called_once_with('one','two')
        loop.handle_worker_message('tv-button',(2,State.HOME,'green'))
        loop.handle_worker_message('tv-button',(3,State.RINGING,'green')); loop.press.assert_not_called()
        loop.handle_worker_message('tv-button',(3,State.HOME,'green')); loop.press.assert_called_once_with('green')
        loop.closed=True; loop.handle_worker_message('tv-button',(3,State.HOME,'red')); self.assertEqual(loop.press.call_count,1)
        loop.apply_poll_config=Mock(); loop.callback_requests=[{'id':'new'}]
        loop.handle_worker_message('poll-config',(3,config() | {'callbacks':[]},1))
        self.assertEqual(loop.apply_poll_config.call_args.args[0]['callbacks'],[{'id':'new'}])
        loop.setup_stage='wifi'; loop.apply_poll_config.reset_mock()
        loop.handle_worker_message('poll-config',(3,config(),4)); loop.apply_poll_config.assert_not_called()

    def test_poll_versions_and_same_version_presence_refresh_preserve_other_contact_fields(self):
        loop=self.loop(); loop.model.config['configuration_version']=3
        loop.apply_poll_config(config()); self.assertEqual(loop.server_seen,99)
        fresh=config(); fresh['configuration_version']=4
        loop.apply_poll_config(fresh); loop.apply_config.assert_called_once_with(fresh)
        fresh=copy.deepcopy(loop.model.config); fresh['contacts'][0]['online']=False; fresh['contacts'][0]['name']='remote change'
        with patch.object(management.time,'monotonic',return_value=101): loop.apply_poll_config(fresh)
        self.assertFalse(loop.model.config['contacts'][0]['online']); self.assertEqual(loop.model.config['contacts'][0]['name'],'Alice')
        self.assertEqual(loop.server_seen,101); loop.render.assert_called_once()

    def test_usb_activity_and_readiness_requires_power_before_native_refresh(self):
        loop=self.loop(); order=[]
        loop.usb_power.require.side_effect=lambda:order.append('require')
        loop.usb_power.refresh.side_effect=lambda engine:order.append(engine)
        self.assertTrue(loop.usb_media_ready()); self.assertEqual(order,['require',loop.engine])
        loop.usb_power.ready=False; self.assertFalse(loop.usb_media_ready())
        loop.tick_usb(); loop.usb_power.update.assert_called_with(False,75,False)
        for attribute,value in [('setup_stage','server'),('scanner',object()),('settings_open',True),('keys_down',{'green'})]:
            before=getattr(loop,attribute); setattr(loop,attribute,value); loop.tick_usb()
            loop.usb_power.update.assert_called_with(True,75,False); setattr(loop,attribute,before)
        loop.model.state=State.RINGING; loop.tick_usb(); loop.usb_power.update.assert_called_with(True,75,True)
        loop.usb_power.enabled=False; self.assertTrue(loop.usb_media_ready()); loop.usb_power=None; self.assertTrue(loop.usb_media_ready())

    def test_timers_apply_pending_config_expire_notices_and_publish_diagnostics(self):
        loop=self.loop(); loop.pending_config={'pending':True}; loop.engine_retry_at=105
        loop.notice='callback_requested'; loop.callback_notice_until=102; loop.callback_alert=('alice',103)
        loop.poll=Mock(); loop.last_poll=90; loop.server_seen=90
        loop.update_timers(100); self.assertEqual(loop.pending_config,{'pending':True}); self.assertTrue(loop.presence_stale)
        loop.poll.assert_called_once(); self.assertIs(loop.diagnostics,loop.engine.diagnostics.return_value)
        loop.update_timers(106); self.assertIsNone(loop.pending_config); loop.apply_config.assert_called_once_with({'pending':True})
        self.assertEqual(loop.notice,''); self.assertIsNone(loop.callback_alert)
        loop.outgoing_deadline=107; loop.model.state=State.CONNECTING; loop.update_timers(108); loop.press.assert_called_once_with('red')

    def test_auto_answer_waits_for_usb_and_tv_then_counts_down_without_duplicate_redraw(self):
        loop=self.loop(); loop.poll=Mock(); loop.model.incoming('alice','family.test'); loop.model.deadline=100
        loop.usb_power.ready=False; loop.tv_control.ready.return_value=False
        loop.update_timers(100); self.assertEqual(loop.model.deadline,105); loop.action.assert_called_with(None)
        loop.usb_power.ready=True; loop.tv_control.ready.return_value=True; loop.render.reset_mock()
        loop.update_timers(100.1); loop.render.assert_not_called()
        loop.update_timers(105.1); loop.action.assert_called_with('answer'); self.assertIsNone(loop.model.deadline)
        self.assertEqual(loop.last_countdown,(State.CONNECTING,None))

    def test_tick_orders_ui_work_schedules_animation_and_stops_when_closed(self):
        loop=self.loop(); loop.update_timers=Mock(); loop.configuration.photos.changed.return_value=True
        motion=Mock(); motion.progress.return_value=.5; motion.next_frame_delay.return_value=17; loop.carousel_motion=motion
        with patch.object(management.time,'monotonic',return_value=100): loop.tick()
        loop.engine.iterate.assert_called_once(); loop.render.assert_called_once(); loop.draw_avatar.assert_called_once_with(loop.model.selected)
        loop.root.after.assert_called_with(17,loop.tick); loop.case_fan.update.assert_called_with(False)
        motion.progress.return_value=1
        with patch.object(management.time,'monotonic',return_value=101): loop.tick()
        self.assertIsNone(loop.carousel_motion); loop.root.after.assert_called_with(20,loop.tick)
        loop.model.state=State.RINGING; loop.tick(); loop.animate_ringing.assert_called_once()
        loop.model.state=State.IN_CALL; loop.tick(); loop.case_fan.update.assert_called_with(True)
        loop.closed=True; loop.root.reset_mock(); loop.tick(); loop.root.after.assert_not_called()

    def test_failed_tick_reports_help_and_still_schedules_recovery(self):
        loop=self.loop(); loop.engine.iterate.side_effect=RuntimeError('native failure')
        with self.assertLogs(level='ERROR') as captured: loop.tick()
        self.assertIn('Terminal tick failed',captured.output[0]); self.assertEqual(loop.notice,'help')
        loop.root.after.assert_called_once_with(20,loop.tick)


if __name__=='__main__': unittest.main()
