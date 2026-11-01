# @test T-LLT-068
# @requirements LLR-TERM-SETUP-027, LLR-TERM-SETUP-028, LLR-TERM-SETUP-030, LLR-TERM-SETUP-033, LLR-TERM-SETUP-034, LLR-TERM-SETUP-035
# @environment portable
# @plan Run reset and QR enrollment orchestration using temporary profile files, queued fake workers and mocked Wi-Fi/native boundaries. Assert reset invalidates old work before resource shutdown and clears only owned state, calls block reset, QR duplicate/busy/pairing gates suppress requests, and server validation is non-persistent until a current-generation success reaches the UI. Verify failure logs omit scanned secrets and pending Wi-Fi cleanup precedes camera acquisition.
# @pass All state, order and privacy assertions pass without altering actual Wi-Fi profiles, files outside the temporary profile, or device enrollment.
from pathlib import Path
import queue
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from zmala_terminal.common import setup_flow
from zmala_terminal.common.model import TerminalModel, State
from tests.terminal.LLT import test_setup_ownership


class EnrollmentLifecycleTests(unittest.TestCase):
    def flow(self):
        f=test_setup_ownership.SetupOwnershipTests().flow(); f.profile='fixture'; f.wifi_mode='connect'; f.last_qr=('',0)
        f.messages=queue.Queue(); f.setup_cancelled=threading.Event(); f.setup_error_until=0
        return f

    def test_reset_cancels_generation_before_teardown_and_starts_empty_model(self):
        f=self.flow()
        with tempfile.TemporaryDirectory() as directory:
            f.enrollment.path=Path(directory)/'enrollment.json'; check=Path(directory)/'tv-check.json'; check.write_text('{}')
            untouched=Path(directory)/'other-profile.json'; untouched.write_text('keep')
            f.model=TerminalModel(); f.maintenance=Mock(); f.configuration=Mock(); f.engine=Mock(); f.tv_check=Mock(); f.remote_test=Mock()
            f.missed_calls_store=Mock(); f.settings_hold=Mock(); f.settings_open=True; f.callbacks.seen={'old'}; f.callbacks.serial=5; f.language='fr'
            f.enrollment.value={'wifi':{'linux_uuid':'owned'}}; cancelled=f.setup_cancelled
            resources=[f.maintenance,f.configuration,f.engine,f.scanner,f.tv_check]; events=[]
            def closed(label):
                self.assertTrue(cancelled.is_set()); self.assertEqual(f.generation,2); events.append(label)
            f.maintenance.stop.side_effect=lambda:closed('maintenance')
            f.configuration.deactivate.side_effect=lambda **kw:closed('configuration')
            f.engine.close.side_effect=lambda:closed('engine'); f.scanner.close.side_effect=lambda:closed('scanner')
            f.tv_check.close.side_effect=lambda:closed('tv-check'); f.start_scanner=Mock()
            f.factory_reset()
            self.assertEqual(events,['maintenance','configuration','engine','scanner','tv-check'])
            resources[1].deactivate.assert_called_once_with(erase=True); f.enrollment.reset.assert_called_once_with({'linux_uuid':'owned'},language='fr')
            self.assertFalse(f.setup_cancelled.is_set()); self.assertEqual(f.model.state,State.HOME); self.assertIsNone(f.model.config)
            self.assertEqual(f.callbacks.serial,6); self.assertFalse(f.callbacks.seen); self.assertEqual(f.current_settings,{})
            self.assertFalse(check.exists()); self.assertEqual(untouched.read_text(),'keep'); self.assertEqual(f.setup_stage,'wifi')
            f.remote_test.reset.assert_called_once(); f.start_scanner.assert_called_once(); f.missed_calls_store.clear.assert_called_once()
            f.model.state=State.IN_CALL; f.factory_reset(); self.assertEqual(f.generation,2)

    def test_qr_gates_duplicate_busy_cleanup_pairing_and_invalid_input(self):
        f=self.flow(); workers=[]
        with patch.object(setup_flow.threading,'Thread',side_effect=lambda **kw:Mock(start=lambda:workers.append(kw['target']))),patch.object(setup_flow.time,'monotonic',return_value=100):
            f.needs_pairing.return_value=True; f.qr_found('WIFI:S:home;;'); self.assertFalse(f.setup_busy)
            f.needs_pairing.return_value=False; f.enrollment.value={'wifi_cleanup':{'linux_uuid':'old'}}; f.qr_found('WIFI:S:home;;'); self.assertFalse(f.setup_busy)
            f.enrollment.value={}
            with self.assertLogs(level='WARNING') as messages: f.qr_found('private invalid QR secret')
            self.assertNotIn('private invalid QR secret',' '.join(messages.output)); self.assertTrue(f.setup_feedback); self.assertEqual(f.setup_error_until,102)
            f.qr_found('WIFI:S:home;T:WPA;P:secret123;;'); self.assertTrue(f.setup_busy); self.assertEqual(len(workers),1)
            f.qr_found('WIFI:S:other;;'); self.assertEqual(len(workers),1)
            f.setup_busy=False; f.qr_found('WIFI:S:home;T:WPA;P:secret123;;'); self.assertEqual(len(workers),1)
        with patch.object(setup_flow,'connect_wifi',return_value={'linux_uuid':'new'}) as connect: workers[0]()
        self.assertEqual(connect.call_args.args[1:],('fixture','connect',f.setup_cancelled))
        self.assertEqual(f.messages.get_nowait(),('setup',(1,'wifi',{'linux_uuid':'new'})))

    def test_server_candidate_validation_and_failure_do_not_persist_in_worker(self):
        f=self.flow(); f.setup_stage='server'; candidate=Mock(); candidate.fetch.return_value={'version':1}; f.make_configuration=Mock(return_value=candidate)
        with patch.object(setup_flow,'parse_server',return_value={'device_token':'private token'}),patch.object(setup_flow.threading,'Thread',side_effect=lambda **kw:Mock(start=kw['target'])):
            f.qr_found('server payload'); candidate.fetch.assert_called_once_with(persist=False); candidate.persist.assert_not_called()
            self.assertEqual(f.messages.get_nowait(),('setup',(1,'server',(candidate,{'version':1}))))
            f.setup_busy=False; f.last_qr=('',0); candidate.fetch.side_effect=OSError('private token included by transport')
            with self.assertLogs(level='WARNING') as messages: f.qr_found('server payload')
        self.assertNotIn('private token',' '.join(messages.output)); self.assertEqual(f.messages.get_nowait(),('setup',(1,'error','server')))
        f.setup_result(1,'error','server'); self.assertEqual(f.setup_feedback,'server_unavailable'); self.assertEqual(f.setup_stage,'server')

    def test_camera_waits_for_owned_cleanup_and_usb_readiness(self):
        f=self.flow(); f.scanner=None; f.enrollment.value={'wifi_cleanup':{'linux_uuid':'old'}}; f.start_wifi_cleanup=Mock()
        f.start_scanner(); f.start_wifi_cleanup.assert_called_once(); f.make_scanner.assert_not_called()
        f.enrollment.value={}; f.usb_media_ready=Mock(return_value=False); f.start_scanner(); f.make_scanner.assert_not_called()
        f.usb_media_ready.return_value=True; f.start_scanner(); self.assertIs(f.scanner,f.make_scanner.return_value)
        f.iterate_scanner(); f.scanner.iterate.assert_called_once()


if __name__=='__main__': unittest.main()
