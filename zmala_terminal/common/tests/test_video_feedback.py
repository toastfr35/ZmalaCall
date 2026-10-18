"""Decoded video, negotiated direction and stalled-stream detection."""
from pathlib import Path
import sys
import unittest
import ctypes as C
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from zmala_terminal.common.engine import Engine, OglContext


class VideoFeedbackTests(unittest.TestCase):
    def test_preview_uses_distinct_persistent_native_context(self):
        e = Engine.__new__(Engine)
        e.core = 1
        e.core_set_video_display_filter = Mock()
        e.core_set_native_video_window_id = Mock()
        e.core_set_native_preview_window_id = Mock()
        e.core_use_preview_window = Mock()
        e.configure_video_windows(100, 200)
        main = e.core_set_native_video_window_id.call_args.args[1]
        preview = e.core_set_native_preview_window_id.call_args.args[1]
        self.assertNotEqual(main, preview)
        self.assertEqual(C.cast(main, C.POINTER(OglContext)).contents.window, 100)
        self.assertEqual(C.cast(preview, C.POINTER(OglContext)).contents.window, 200)
        self.assertEqual(preview, C.addressof(e.preview_ogl))
        e.core_use_preview_window.assert_called_once_with(1, 1)
        e.configure_video_windows(0, 0)
        e.core_use_preview_window.assert_called_with(1, 0)
        e.core_set_native_preview_window_id.assert_called_with(1, None)

    def engine(self):
        engine = Engine.__new__(Engine)
        engine.call = 10
        engine._last_video_frame = None
        engine.call_get_current_params = lambda call: 20
        engine.call_params_video_enabled = lambda params: True
        engine.call_params_get_video_direction = lambda params: 3
        engine.call_params_get_received_framerate = lambda params: 0
        return engine

    @patch('zmala_terminal.common.engine.WINDOWS', False)
    @patch('zmala_terminal.common.engine.time.monotonic')
    def test_linux_frame_rate_without_repeated_decoder_callbacks(self, clock):
        e = self.engine()
        clock.return_value = 100
        self.assertFalse(e.incoming_video_active())
        e.call_params_get_received_framerate = lambda params: 15
        self.assertTrue(e.incoming_video_active())
        clock.return_value = 110
        self.assertTrue(e.incoming_video_active())
        e.call_params_get_received_framerate = lambda params: 0
        clock.return_value = 114
        self.assertFalse(e.incoming_video_active())

    @patch('zmala_terminal.common.engine.time.monotonic')
    def test_first_frame_short_gaps_stall_and_recovery(self, clock):
        e = self.engine()
        clock.return_value = 100
        self.assertFalse(e.incoming_video_active())
        e._video_frame_decoded(e.call)
        self.assertTrue(e.incoming_video_active())
        clock.return_value = 103.9
        self.assertTrue(e.incoming_video_active())
        clock.return_value = 104
        self.assertFalse(e.incoming_video_active())
        e._video_frame_decoded(e.call)
        self.assertTrue(e.incoming_video_active())

    @patch('zmala_terminal.common.engine.time.monotonic', return_value=100)
    def test_disabled_reception_discards_history_before_resuming(self, clock):
        e = self.engine()
        e._video_frame_decoded(e.call)
        for direction in (0, 1):
            e.call_params_get_video_direction = lambda params: direction
            self.assertFalse(e.incoming_video_active())
        e.call_params_get_video_direction = lambda params: 3
        self.assertFalse(e.incoming_video_active())
        e._video_frame_decoded(e.call)
        self.assertTrue(e.incoming_video_active())
        e.call_params_video_enabled = lambda params: False
        self.assertFalse(e.incoming_video_active())

    def test_ended_and_unrelated_calls_cannot_supply_video(self):
        e = self.engine()
        e._video_frame_decoded(11)
        self.assertFalse(e.incoming_video_active())
        e.call = None
        self.assertFalse(e.incoming_video_active())


if __name__ == '__main__':
    unittest.main()
