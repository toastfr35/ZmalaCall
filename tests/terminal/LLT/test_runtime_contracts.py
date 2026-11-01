# @test T-LLT-049
# @requirements LLR-TERM-START-006, LLR-TERM-START-007, LLR-TERM-CONFIG-024, LLR-TERM-UI-025, LLR-TERM-HISTORY-024, LLR-TERM-MAINT-018
# @environment portable
# @plan Use native-call, UI and transport doubles to check retained call handles and shutdown order, live language/framing changes, idle-only callback notices and status snapshots. Inject failed JSON replacement to verify old private state survives and successful UTF-8 state is complete.
# @pass Every transition must preserve unrelated call ownership; notifications must never dial automatically and failed persistence must preserve the prior snapshot.

from zmala_terminal.common.callbacks import CallbackController
import json
from pathlib import Path
import queue
import tempfile
import unittest
from unittest.mock import Mock, call, patch

from zmala_terminal.common.engine import Engine
from zmala_terminal.common.configuration_control import ConfigurationControl
from zmala_terminal.common.call_control import CallControl
from zmala_terminal.common.management import ManagementLoop
from zmala_terminal.common.model import TerminalModel, State
from zmala_terminal.common.json_storage import write_json
from tests.terminal.LLT.test_terminal import config


class RuntimeContractTests(unittest.TestCase):
    def test_borrowed_calls_are_retained_once_and_released_before_core(self):
        e = Engine.__new__(Engine)
        e.call = None; e.core = 7; e.factory = 8; e._video_callbacks = None
        e.video_frame_callback = Mock()
        events = []
        e.call_ref = Mock(side_effect=lambda value: events.append(('ref', value)) or value)
        e.factory_create_call_cbs = Mock(return_value=42)
        for name in ('call_remove_callbacks', 'call_cbs_unref', 'call_unref', 'core_stop', 'core_unref'):
            setattr(e, name, Mock(side_effect=lambda *values, name=name: events.append((name, *values))))
        e.call_cbs_set_next_video_frame_decoded = Mock(); e.call_add_callbacks = Mock(); e.end = Mock()
        e.auto_framing = Mock(); e.auto_framing.close.side_effect = lambda: events.append(('detector-stop',))
        e.hold_call(10); e.hold_call(10)
        e.call_ref.assert_called_once_with(10)
        e.hold_call(11)
        self.assertLess(events.index(('call_unref', 10)), events.index(('ref', 11)))
        events.clear(); e.close(); e.close()
        self.assertLess(events.index(('detector-stop',)), events.index(('call_unref', 11)))
        self.assertLess(events.index(('call_unref', 11)), events.index(('core_stop', 7)))
        e.core_unref.assert_called_once_with(7)
        self.assertIsNone(e.call); self.assertIsNone(e.core)

    def test_language_and_framing_apply_in_call_without_native_restart(self):
        v = ConfigurationControl(); v.callbacks = CallbackController()
        v.model = TerminalModel(); v.model.configure(config()); v.model.state = State.IN_CALL
        v.setup_stage = None; v.root = Mock(); v.available_fonts = set()
        v.text = lambda key: key; v.render = Mock(); v.engine = Mock(); v.configure_engine = Mock()
        desired = config() | {'language':'fr', 'auto_framing':True, 'c20_speaker_volume':25}
        v.apply_config(desired)
        self.assertEqual(v.language, 'fr'); self.assertEqual(v.pending_config, desired)
        v.engine.auto_framing.configure.assert_called_once_with(True)
        v.configure_engine.assert_not_called(); v.engine.close.assert_not_called(); v.engine.end.assert_not_called()
        self.assertEqual(v.model.state, State.IN_CALL)

    def test_callback_notice_waits_for_idle_input_then_selects_once_without_dial(self):
        v = CallControl(); v.callbacks = CallbackController(); v.model = TerminalModel(); v.model.configure(config())
        v.setup_stage = None; v.last_button = 100; v.callback_alert = None; v.notice = ''; v.carousel_motion = None
        v.callbacks.seen = set(); v.render = Mock(); v.engine = Mock(); v.contact_online = lambda person: True
        v.callbacks.requests = [{'id':'request', 'ready':True, 'from':'terminal', 'to':'alice'}]
        for state in (State.IN_CALL, State.RINGING, State.CONFIRMING):
            v.model.state = state; v.show_callback_available(110)
            self.assertIsNone(v.callback_alert)
        v.model.state = State.HOME
        v.show_callback_available(104.99); self.assertIsNone(v.callback_alert)
        v.show_callback_available(105)
        self.assertEqual(v.callback_alert, (v.model.selected['name'], 115))
        self.assertIn('request', v.callbacks.seen)
        v.engine.dial.assert_not_called()
        v.callback_alert = None; v.show_callback_available(120)
        self.assertIsNone(v.callback_alert); v.render.assert_called_once()

    def test_status_snapshot_uses_applied_revision_and_captured_diagnostics(self):
        v = ManagementLoop(); v.callbacks = CallbackController(); v.model = TerminalModel(); v.model.configure(config())
        v.poll_wifi = Mock(); v.worker_busy = False; v.generation = 3; v.setup_stage = None
        v.configuration = Mock(cancelled=False); v.messages = queue.Queue()
        v.diagnostics = {'registered':True, 'devices':{'camera':['C20']}, 'camera':'C20'}
        with patch('zmala_terminal.common.management.threading.Thread') as thread:
            v.poll()
            v.diagnostics = {'registered':False}
            thread.call_args.kwargs['target']()
        v.configuration.report.assert_called_once_with({'registered':True, 'devices':{'camera':['C20']},
            'camera':'C20', 'state':State.HOME.value, 'configuration_version':1,
            'remote_status':'unknown','remote_battery':None,'remote_charger_connected':None,
            'camera_powered':None,'camera_connected':None,'camera_status':'unknown'})

    def test_native_statistics_release_both_handles_and_preserve_units(self):
        e = Engine.__new__(Engine); e.call = 9
        e.call_get_audio_stats = Mock(return_value=10); e.call_get_video_stats = Mock(return_value=11)
        getters = {'download_bandwidth':123, 'upload_bandwidth':456, 'jitter_buffer_size_ms':20,
                   'round_trip_delay':.02, 'receiver_loss_rate':1, 'sender_loss_rate':2}
        for key, value in getters.items():
            setattr(e, 'call_stats_get_'+key, Mock(return_value=value))
        e.call_stats_unref = Mock(); e.call_get_current_params = Mock(return_value=None)
        result = e.media_stats()
        self.assertEqual(result['audio']['download_kbps'], 123)
        self.assertEqual(result['video']['jitter_buffer_ms'], 20)
        e.call_stats_unref.assert_has_calls([call(10), call(11)])

    def test_json_state_is_complete_utf8_and_failed_replace_retains_previous(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'private/state.json'
            write_json(path, {'name':'Élodie', 'revision':1})
            before = path.read_bytes()
            with patch('zmala_terminal.common.json_storage.os.replace', side_effect=OSError('disk failed')):
                with self.assertRaises(OSError):
                    write_json(path, {'revision':2})
            self.assertEqual(path.read_bytes(), before)
            write_json(path, {'name':'日本語', 'revision':3})
            self.assertEqual(json.loads(path.read_text(encoding='utf8')), {'name':'日本語', 'revision':3})
            self.assertFalse(path.with_name('state.json.tmp').exists())
