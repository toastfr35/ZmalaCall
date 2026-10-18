# @test T-LLT-062
# @requirements LLR-TERM-START-003, LLR-TERM-START-005, LLR-TERM-SETUP-031, LLR-TERM-SETUP-032
# @environment portable
# @plan Execute terminal composition with temporary profile storage and mocked OS/native/UI boundaries. Verify constructor dependency order, saved-language/bootstrap recovery, reset scope, cached/offline startup scheduling, factory argument ownership and idempotent cancellation-before-window-destruction. Exercise CLI validation and normal/failed run cleanup through the real entry function without launching hardware or services.
# @pass Resources close in ownership order and only the selected profile is reset; startup errors propagate with diagnostics and no worker invokes a real device.
import io
from pathlib import Path
import runpy
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch, call
from zmala_terminal.common import main


class ApplicationLifetimeTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory(); self.addCleanup(folder.cleanup)
        self.root=Path(folder.name); (self.root/'data').mkdir()
        self.patches=[patch.object(main,'ROOT',self.root),patch.object(main.tkfont,'families',return_value=['Sans'])]
        self.patches += [patch.object(main,name) for name in ('ArgonFan','UsbPower','TVControl','TextRenderer','IconRenderer')]
        for item in self.patches: item.start(); self.addCleanup(item.stop)

    def terminal(self,profile='terminal'):
        t=main.Terminal.__new__(main.Terminal); t.root=Mock(); t.initialize_state(profile,'connect')
        return t

    def test_constructor_orders_dependencies_and_window_lifetime(self):
        order=[]
        from contextlib import ExitStack
        with ExitStack() as patches:
            for name in ('create_window','initialize_state','restore_enrollment','build_ui','bind_inputs','start_services'):
                patches.enter_context(patch.object(main.Terminal,name,side_effect=lambda *args,name=name:order.append((name,args))))
            main.Terminal(True,'bootstrap','profile',True,'connect')
        self.assertEqual([name for name,_ in order],['create_window','initialize_state','restore_enrollment','build_ui','bind_inputs','start_services'])
        self.assertEqual(order[2][1],('bootstrap',True))
        t=main.Terminal.__new__(main.Terminal)
        with patch.object(main.tk,'Tk') as tk,patch.object(main.tk,'PhotoImage'):
            t.create_window(True)
        tk.return_value.attributes.assert_called_once_with('-fullscreen',True)
        tk.return_value.protocol.assert_called_once_with('WM_DELETE_WINDOW',t.close)
        t.run(); tk.return_value.mainloop.assert_called_once()

    def test_state_profiles_and_unconfigured_reset_only_owned_profile(self):
        t=self.terminal('experiment')
        self.assertEqual(t.cache_path,self.root/'data/config-cache-experiment.json')
        self.assertEqual(t.enrollment.path.parent,self.root/'data/experiment')
        self.assertFalse(t.closed); self.assertIsNone(t.engine); self.assertIsNone(t.network_connected)
        t.enrollment.value={'wifi':{'linux_uuid':'owned'},'language':'fr'}
        t.enrollment.reset=Mock(); t.missed_calls_store.clear=Mock()
        t.cache_path.write_text('cache',encoding='utf-8')
        other=self.root/'data/config-cache.json'; other.write_text('other',encoding='utf-8')
        with patch.object(main,'forget_wifi') as forget:
            t.restore_enrollment('missing-bootstrap',True)
        forget.assert_called_once_with({'linux_uuid':'owned'},'experiment')
        t.enrollment.reset.assert_called_once(); t.missed_calls_store.clear.assert_called_once()
        self.assertFalse(t.cache_path.exists()); self.assertEqual(other.read_text(),'other')
        self.assertEqual(t.setup_stage,'wifi')

    def test_saved_bootstrap_language_and_missing_enrollment_recover_safely(self):
        for saved in (True,False):
            t=self.terminal(); t.setup_stage=None; t.make_configuration=Mock()
            t.enrollment.value={'language':'fr','bootstrap':{'server_url':'http://test'}} if saved else {'language':'not-supported'}
            t.restore_enrollment(self.root/'missing',False)
            if saved:
                self.assertEqual(t.language,'fr'); t.make_configuration.assert_called_once_with({'server_url':'http://test'})
            else:
                self.assertEqual(t.language,'en'); self.assertEqual(t.setup_stage,'wifi')
                t.make_configuration.assert_not_called()
        t=self.terminal(); t.setup_stage=None; t.make_configuration=Mock()
        bootstrap=self.root/'bootstrap.json'; bootstrap.write_text('{}',encoding='utf-8')
        t.restore_enrollment(bootstrap,False); t.make_configuration.assert_called_once_with(bootstrap)

    def test_cached_configuration_setup_and_offline_scheduler(self):
        for setup,cache,checking in (('wifi',None,False),(None,{'version':1},False),(None,{'version':1},True)):
            t=self.terminal(); t.setup_stage=setup
            t.configuration=Mock() if cache else None
            if t.configuration: t.configuration.cached.return_value=cache
            t.begin_tv_setup=Mock(return_value=checking); t.apply_config=Mock(); t.render=Mock(); t.make_maintenance=Mock()
            t.start_services()
            t.root.after.assert_any_call(20,t.tick); t.render.assert_called_once()
            if setup: t.root.after.assert_any_call(100,t.start_scanner)
            elif not checking: t.apply_config.assert_called_once_with(cache)
            else: t.apply_config.assert_not_called()

    def test_factories_pass_owned_profile_and_surfaces(self):
        t=self.terminal('test'); t.video_window=101; t.preview_window=102
        with patch.object(main,'Configuration') as configuration,patch.object(main,'Engine') as engine, \
                patch.object(main,'QRScanner') as scanner,patch.object(main,'MaintenanceAgent') as maintenance:
            t.make_configuration('bootstrap'); configuration.assert_called_once_with(bootstrap='bootstrap',cache=t.cache_path)
            t.make_engine({'setting':1}); engine.assert_called_once_with({'setting':1},t.call_event,t.registration_event,101,
                profile='test',on_message=t.message_event,preview_window=102)
            t.make_scanner(); scanner.assert_called_once_with(t.qr_found,101,'test')
            t.make_maintenance('config'); maintenance.assert_called_once_with('config')

    def test_shutdown_is_idempotent_and_cancels_consumers_before_surface_destruction(self):
        t=self.terminal(); recorder=Mock()
        for name in ('case_fan','usb_power','presenter_input','volume_control','tv_check','tv_control','maintenance','configuration','engine','text_renderer','root'):
            obj=Mock(); setattr(t,name,obj); recorder.attach_mock(obj,name)
        t.stop_scanner=Mock(); recorder.attach_mock(t.stop_scanner,'stop_scanner')
        t.close(); t.close()
        self.assertTrue(t.setup_cancelled.is_set()); self.assertTrue(t.closed)
        self.assertEqual(recorder.mock_calls,[call.case_fan.close(),call.usb_power.close(),call.presenter_input.close(),call.volume_control.close(),
            call.tv_check.close(),call.tv_control.close(),call.maintenance.stop(),call.configuration.deactivate(),call.stop_scanner(),
            call.engine.close(),call.text_renderer.close(),call.root.destroy()])

    def test_cli_validation_and_finally_close_on_run_failure(self):
        with patch.object(main,'Terminal') as terminal,patch('zmala_terminal.common.runtime_logging.configure'):
            main.main(['--profile','demo','--fullscreen','--unconfigured','--wifi-mode','connect'])
            self.assertEqual(terminal.call_args.args[2:],('demo',True,'connect'))
            terminal.return_value.run.assert_called_once(); terminal.return_value.close.assert_called_once()
            terminal.return_value.run.side_effect=RuntimeError('native crash')
            with self.assertLogs(level='ERROR'), self.assertRaisesRegex(RuntimeError,'native crash'): main.main([])
            self.assertEqual(terminal.return_value.close.call_count,2)
            terminal.side_effect=RuntimeError('startup failed')
            with self.assertLogs(level='ERROR'), self.assertRaisesRegex(RuntimeError,'startup failed'): main.main([])
        with patch.object(sys,'argv',['terminal','--profile','../escape']),patch.object(sys,'stderr',io.StringIO()),self.assertRaises(SystemExit) as error:
            runpy.run_module('zmala_terminal.common.main',run_name='__main__')
        self.assertEqual(error.exception.code,2)
