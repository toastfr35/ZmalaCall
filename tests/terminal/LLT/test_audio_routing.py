# @test T-LLT-006
# @requirements LLR-TERM-AUDIO-004, LLR-TERM-POWER-010
# @environment portable
# @plan Use native lists containing HDMI and C10/C20 devices, with an incoming call initially routed to HDMI. Apply real Pi settings and assert core defaults, pending-call input/output and ringtone all use C20. Inject absent capabilities, rejected setters and wrong readback; require retryable failure and release every owned native reference.
# @pass All routing and ownership assertions pass; this does not establish acoustic quality.

import ctypes as C
import unittest
from unittest.mock import Mock, call, patch
from zmala_terminal.common.engine import Engine
from zmala_terminal.common.linphone_api import ListNode
from zmala_terminal.common.media_errors import MediaNotReady
from zmala_terminal.linux.media import bind_call_audio
from tests.terminal.LLT.test_linux_media import catalog


class AudioRoutingTests(unittest.TestCase):
    def engine(self, model="C20"):
        engine = Engine.__new__(Engine)
        engine.core, engine.call = 10, 20
        engine.devices = Mock(return_value=catalog('4'))
        for name in ('core_set_video_device', 'core_set_capture_device', 'core_set_playback_device', 'core_set_ringer_device'):
            setattr(engine, name, Mock(return_value=0))
        engine.core_get_playback_device = Mock(return_value=b'ALSA: Nuroum C20 [Unknown]')
        engine.nodes = (ListNode * 3)()
        for i, node in enumerate(engine.nodes):
            node.data = i + 1
            if i < 2:
                node.next = C.pointer(engine.nodes[i+1])
        engine.core_get_extended_audio_devices = Mock(return_value=C.pointer(engine.nodes[0]))
        names = {1: b'ALSA: HDMI', 2: ('ALSA: Nuroum '+model+' [Unknown]').encode(), 3: b'ALSA: unrelated mic'}
        engine.audio_device_get_id = Mock(side_effect=names.get)
        engine.audio_device_get_capabilities = Mock(side_effect={1: 2, 2: 3, 3: 1}.get)
        engine.audio_device_unref, engine.bctbx = Mock(), Mock()
        engine.routes = {}
        for prefix, target in (('core_default_', 10), ('call_', 20)):
            for direction in ('input', 'output'):
                key = prefix + direction
                engine.routes[key] = 1
                setter = 'core_set_default_' if prefix == 'core_default_' else 'call_set_'
                getter = 'core_get_default_' if prefix == 'core_default_' else 'call_get_'
                setattr(engine, setter+direction+'_audio_device', Mock(side_effect=lambda target, device, key=key: engine.routes.update({key: device})))
                setattr(engine, getter+direction+'_audio_device', Mock(side_effect=lambda target, key=key: engine.routes[key]))
        return engine

    def test_c10_pending_call_rebinds_both_directions(self):
        engine = self.engine('C10')
        bind_call_audio(engine)
        self.assertEqual(set(engine.routes.values()), {2})
        engine.call_set_input_audio_device.assert_called_once_with(20, 2)
        engine.call_set_output_audio_device.assert_called_once_with(20, 2)

    def test_waking_c20_replaces_hdmi_on_pending_call_and_future_calls(self):
        engine = self.engine()
        with patch('zmala_terminal.common.engine.WINDOWS', False):
            engine.apply_settings({'speaker': 'HDMI'})
        self.assertEqual(set(engine.routes.values()), {2})
        engine.call_set_input_audio_device.assert_called_once_with(20, 2)
        engine.call_set_output_audio_device.assert_called_once_with(20, 2)
        engine.core_set_ringer_device.assert_called_once_with(10, b'ALSA: Nuroum C20 [Unknown]')
        engine.audio_device_unref.assert_has_calls([call(1), call(2), call(3)])
        engine.bctbx.bctbx_list_free.assert_called_once()

    def test_missing_capture_or_playback_never_uses_hdmi(self):
        for capability in (0, 1, 2):
            engine = self.engine()
            engine.audio_device_get_capabilities.side_effect = {1: 2, 2: capability, 3: 1}.get
            with self.assertRaises(MediaNotReady):
                bind_call_audio(engine)
            self.assertEqual(engine.audio_device_unref.call_count, 3)
            engine.bctbx.bctbx_list_free.assert_called_once()
            engine.call_set_output_audio_device.assert_not_called()

    def test_failed_readback_is_retryable_and_releases_list(self):
        for name in ('core_get_default_input_audio_device', 'core_get_default_output_audio_device', 'call_get_input_audio_device', 'call_get_output_audio_device'):
            engine = self.engine()
            setattr(engine, name, Mock(return_value=1))
            with self.assertRaises(MediaNotReady):
                bind_call_audio(engine)
            self.assertEqual(engine.audio_device_unref.call_count, 3)
            engine.bctbx.bctbx_list_free.assert_called_once()

    def test_rejected_native_setters_do_not_report_media_ready(self):
        for name in ('core_set_video_device', 'core_set_capture_device', 'core_set_playback_device', 'core_set_ringer_device'):
            engine = self.engine()
            getattr(engine, name).return_value = -1
            with patch('zmala_terminal.common.engine.WINDOWS', False), self.assertRaises(MediaNotReady):
                engine.apply_settings({})
            engine.call_set_output_audio_device.assert_not_called()

    def test_legacy_playback_readback_cannot_silently_be_hdmi(self):
        engine = self.engine()
        engine.core_get_playback_device.return_value = b'ALSA: HDMI'
        with patch('zmala_terminal.common.engine.WINDOWS', False), self.assertRaises(MediaNotReady):
            engine.apply_settings({})
        engine.core_set_ringer_device.assert_not_called()
