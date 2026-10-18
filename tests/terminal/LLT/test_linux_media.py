# @test T-LLT-017
# @requirements TLLR048, TLLR051
# @environment portable
# @plan Supply device catalogs with stale paths, replugged C20 nodes and unrelated devices; assert C20 rediscovery, no silent substitution and playback/ringer routing.
# @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

"""C20 routing follows identity and never silently switches to other hardware."""
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from zmala_terminal.common.engine import Engine
from zmala_terminal.linux.media import c20_devices, settings


def catalog(node='0'):
    return {'camera': ['V4L2: /dev/video0', f'ZmalaMJPEG: /dev/video{node}', 'StaticImage: Static picture'],
            'microphone': ['ALSA: unrelated mic', 'ALSA: Nuroum C20 [Unknown]'],
            'speaker': ['ALSA: vc4-hdmi [Unknown]', 'ALSA: default [Unknown]', 'ALSA: Nuroum C20 [Unknown]']}


class C20MediaTests(unittest.TestCase):
    def test_replugged_camera_uses_current_node(self):
        self.assertEqual(settings(catalog('4'))['camera'], 'ZmalaMJPEG: /dev/video4')

    def test_catalog_excludes_raw_camera_and_hdmi(self):
        devices = c20_devices(catalog())
        self.assertEqual(devices['camera'], ['ZmalaMJPEG: /dev/video0'])
        self.assertEqual(devices['speaker'], ['ALSA: Nuroum C20 [Unknown]'])

    def test_missing_c20_does_not_choose_another_device(self):
        for kind in ('camera', 'microphone', 'speaker'):
            devices = catalog()
            devices[kind] = ['ALSA: default', 'V4L2: /dev/video0']
            with self.subTest(kind=kind), self.assertRaisesRegex(RuntimeError, kind):
                settings(devices)

    def test_linux_ignores_stale_server_hardware_and_routes_ringer_to_c20(self):
        engine = Engine.__new__(Engine)
        engine.core = 'core'
        engine.devices = Mock(return_value=catalog('4'))
        for name in ('core_set_video_device', 'core_set_capture_device', 'core_set_playback_device', 'core_set_ringer_device'):
            setattr(engine, name, Mock(return_value=0))
        engine.core_get_playback_device = Mock(return_value=b'ALSA: Nuroum C20 [Unknown]')
        with patch('zmala_terminal.common.engine.WINDOWS', False):
            engine.apply_settings({'camera': 'old webcam', 'speaker': 'ALSA: vc4-hdmi'})
        engine.core_set_video_device.assert_called_once_with('core', b'ZmalaMJPEG: /dev/video4')
        engine.core_set_capture_device.assert_called_once_with('core', b'ALSA: Nuroum C20 [Unknown]')
        engine.core_set_ringer_device.assert_called_once_with('core', b'ALSA: Nuroum C20 [Unknown]')
