# @test T-LLT-006
# @requirements LLR-TERM-AUDIO-004
# @environment portable
# @plan Run the Pi settings path with a synthetic C20 catalog and recording native setters. Return an effective speaker ID different from the request; assert ringtone uses that readback. Fail device and ringer setters and assert explicit diagnostics without silent rerouting. This checks routing, not acoustic quality or tone cadence.
# @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

"""Incoming ringtone output follows the effective call speaker."""
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from zmala_terminal.common.engine import Engine
from tests.terminal.LLT.test_linux_media import catalog


class AudioRoutingTests(unittest.TestCase):
    def engine(self, effective):
        engine = Engine.__new__(Engine)
        engine.core = 'core'
        engine.devices = Mock(return_value=catalog('4'))
        for name in ('core_set_video_device', 'core_set_capture_device', 'core_set_playback_device', 'core_set_ringer_device'):
            setattr(engine, name, Mock(return_value=0))
        engine.core_get_playback_device = Mock(return_value=effective)
        return engine

    def test_ringtone_follows_effective_playback_device(self):
        for effective in (b'ALSA: Nuroum C20 [Unknown]', b'C20-effective-native-id'):
            engine = self.engine(effective)
            with patch('zmala_terminal.common.engine.WINDOWS', False):
                engine.apply_settings({'camera': 'obsolete node', 'speaker': 'obsolete speaker'})
            engine.core_set_playback_device.assert_called_once_with('core', b'ALSA: Nuroum C20 [Unknown]')
            engine.core_set_ringer_device.assert_called_once_with('core', effective)

    def test_rejected_native_routing_reports_each_failed_device(self):
        engine = self.engine(b'C20-effective-native-id')
        for name in ('core_set_video_device', 'core_set_capture_device', 'core_set_playback_device', 'core_set_ringer_device'):
            getattr(engine, name).return_value = -1
        with patch('zmala_terminal.common.engine.WINDOWS', False), self.assertLogs(level='WARNING') as logs:
            engine.apply_settings({})
        self.assertEqual(len(logs.output), 4)
        for kind in ('camera', 'microphone', 'speaker', 'ringtone'):
            self.assertTrue(any(kind+' device is unavailable' in message for message in logs.output))
        engine.core_set_ringer_device.assert_called_once_with('core', b'C20-effective-native-id')
