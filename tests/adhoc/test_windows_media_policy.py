"""Desktop compatibility checks; excluded from Pi requirements and RBT coverage."""
from types import SimpleNamespace
from zmala_terminal.common.media_adapter import MediaAdapter
from zmala_terminal.windows import media as windows_media
import unittest
from unittest.mock import Mock, patch
from zmala_terminal.common.audio_processing import configure
from zmala_terminal.common.engine import Engine


class WindowsMediaPolicyTests(unittest.TestCase):
    def test_windows_keeps_server_camera_and_effective_speaker(self):
        engine = Engine.__new__(Engine); engine.media = MediaAdapter(windows_media)
        engine.core = 'core'
        for name in ('core_set_video_device', 'core_set_capture_device', 'core_set_playback_device', 'core_set_ringer_device'):
            setattr(engine, name, Mock(return_value=0))
        engine.core_get_playback_device = Mock(return_value=b'effective speaker')
        with patch('zmala_terminal.common.engine.WINDOWS', True):
            engine.apply_settings({'camera': 'ordinary camera'})
        engine.core_set_video_device.assert_called_once_with('core', b'ordinary camera')
        engine.core_set_ringer_device.assert_called_once_with('core', b'effective speaker')

    def test_windows_does_not_load_linux_audio_plugin(self):
        engine = SimpleNamespace(config={'audio_profile': 'speech'})
        with patch('zmala_terminal.common.native_runtime.WINDOWS', True), patch('ctypes.CDLL') as load:
            configure(engine)
        load.assert_not_called()
        self.assertEqual(engine.audio_profile, 'speech')
        self.assertEqual(engine.applied_audio_profile, 'normal')


if __name__ == '__main__':
    unittest.main()
