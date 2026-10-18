"""A video-only webcam must not create an outgoing audio capture stream."""
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from zmala_terminal.common.engine import Engine


class MissingMicrophoneTests(unittest.TestCase):
    def test_capture_returns_on_the_next_call_after_reconnection(self):
        engine = Engine.__new__(Engine)
        engine.devices = Mock(side_effect=[{'microphone': []}, {'microphone': ['USB microphone']}])
        engine.call_params_enable_mic = Mock()
        engine.call_params_set_audio_direction = Mock()
        with self.assertLogs(level='WARNING'):
            engine.configure_call_audio('first-call')
        engine.call_params_enable_mic.assert_called_once_with('first-call', 0)
        engine.call_params_set_audio_direction.assert_called_once_with('first-call', 2)
        engine.configure_call_audio('second-call')
        # The second call retains the SDK's negotiated direction and microphone defaults.
        self.assertEqual(engine.call_params_set_audio_direction.call_count, 1)
        self.assertEqual(engine.call_params_enable_mic.call_count, 1)
