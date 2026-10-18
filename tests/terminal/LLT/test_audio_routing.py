# @test T-LLT-006
# @requirements LLR-TERM-MEDIA-008
# @environment portable
# @plan Configure a fake native core with explicit playback devices; assert ringback and ringtone use the effective playback device. Windows camera preservation is a compatibility subcase.
# @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

"""Incoming ringtone output follows the effective call speaker."""
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from zmala_terminal.common.engine import Engine


class AudioRoutingTests(unittest.TestCase):
    def test_windows_keeps_the_server_camera_selection(self):
        engine = Engine.__new__(Engine)
        engine.core = 'core'
        for name in ('core_set_video_device', 'core_set_capture_device', 'core_set_playback_device', 'core_set_ringer_device'):
            setattr(engine, name, Mock(return_value=0))
        engine.core_get_playback_device = Mock(return_value=b'speaker')
        with patch('zmala_terminal.common.engine.WINDOWS', True):
            engine.apply_settings({'camera': 'ordinary camera'})
        engine.core_set_video_device.assert_called_once_with('core', b'ordinary camera')

    def test_ringtone_follows_effective_playback_device(self):
        for requested, effective in [('ALSA: vc4-hdmi', b'ALSA: vc4-hdmi'), ('', b'ALSA: system-default')]:
            engine = Engine.__new__(Engine)
            engine.core = 'core'
            for name in ('core_set_video_device', 'core_set_capture_device', 'core_set_playback_device', 'core_set_ringer_device'):
                setattr(engine, name, Mock(return_value=0))
            engine.core_get_playback_device = Mock(return_value=effective)
            with patch('zmala_terminal.common.engine.WINDOWS', True):
                engine.apply_settings({'camera': 'camera', 'speaker': requested})
            engine.core_set_ringer_device.assert_called_once_with('core', effective)
