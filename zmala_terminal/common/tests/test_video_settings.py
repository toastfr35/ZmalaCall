"""Server presets are authoritative on both platforms; no hidden local knobs."""
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from zmala_terminal.common.video_settings import VideoSettings
from zmala_terminal.common.engine import Engine, VideoSize


class VideoSettingsTests(unittest.TestCase):
    def test_server_resolution_and_bandwidth(self):
        for resolution, dimensions, upload in [('480p', (640, 480), 700),
                                               ('720p', (1280, 720), 1500),
                                               ('1080p', (1920, 1080), 2500)]:
            settings = VideoSettings.for_config({'video_resolution': resolution})
            self.assertEqual(settings.dimensions, dimensions)
            self.assertEqual(settings.upload_kbps, upload)
            self.assertEqual(settings.fps, 15)

    def test_absent_resolution_uses_verified_default(self):
        self.assertEqual(VideoSettings.for_config({}).dimensions, (1280, 720))

    def test_legacy_low_preset_uses_supported_vga(self):
        settings = VideoSettings.for_config({'video_resolution': '360p'})
        self.assertEqual(settings.resolution, '480p')
        self.assertEqual(settings.dimensions, (640, 480))
        self.assertEqual(settings.upload_kbps, 700)

    def test_frame_rate_scales_send_budget_but_not_receive_capacity(self):
        for fps in (10, 15, 20, 25, 30):
            settings = VideoSettings.for_config({'video_resolution': '1080p', 'video_fps': fps})
            self.assertEqual(settings.fps, fps)
            self.assertEqual(settings.dimensions, (1920, 1080))
            self.assertEqual(settings.upload_kbps, (2500 * fps + 14) // 15)
            self.assertEqual(settings.download_kbps, 6000)

    def test_invalid_frame_rate_rejected(self):
        for fps in (None, True, '30', 0, 14, 29.97, 60, []):
            with self.subTest(fps=fps), self.assertRaises(ValueError):
                VideoSettings.for_config({'video_fps': fps})

    def test_native_size_must_match_before_enabling_packet_repair(self):
        engine = Engine.__new__(Engine)
        engine.core = 1
        engine.video_settings = VideoSettings.for_config({'video_resolution': '480p'})
        engine.core_set_preferred_video_size = Mock()
        engine.core_get_preferred_video_size = Mock(return_value=VideoSize(1280, 720))
        engine.core_enable_retransmission_on_nack = Mock()
        with self.assertRaisesRegex(RuntimeError, 'SDK rejected video size'):
            engine.configure_video_target()
        engine.core_enable_retransmission_on_nack.assert_not_called()
        engine.core_get_preferred_video_size.return_value = VideoSize(640, 480)
        engine.configure_video_target()
        engine.core_enable_retransmission_on_nack.assert_called_once_with(1, 1)

    def test_invalid_presets_fail_before_native_capture(self):
        for resolution in ('vga', '4k', None, [], True):
            with self.subTest(resolution=resolution), self.assertRaises(ValueError):
                VideoSettings.for_config({'video_resolution': resolution})
