"""Server settings override local experiments; unsupported clients stay usable."""
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audio_processing import configure, requested_profile
from test_terminal import config
from configuration import validate


class AudioProfileTests(unittest.TestCase):
    def test_server_profile_is_validated(self):
        for profile in ('normal', 'speech'):
            value = config() | {'audio_profile': profile}
            self.assertEqual(validate(value, 'test')['audio_profile'], profile)
        for profile in (None, 16000, 'unknown', []):
            with self.assertRaises(ValueError):
                validate(config() | {'audio_profile': profile}, 'test')
    def test_server_overrides_local_profile(self):
        with patch.dict(os.environ, {'ZMALA_AUDIO_PROFILE': 'speech'}):
            self.assertEqual(requested_profile({'audio_profile': 'normal'}), 'normal')
            self.assertEqual(requested_profile({}), 'normal')

    def test_windows_does_not_load_linux_plugin(self):
        engine = SimpleNamespace(config={'audio_profile': 'speech'})
        with patch('platforms.native_runtime.WINDOWS', True), patch('ctypes.CDLL') as load:
            configure(engine)
        load.assert_not_called()
        self.assertEqual(engine.audio_profile, 'speech')
        self.assertEqual(engine.applied_audio_profile, 'normal')

    def test_missing_plugin_falls_back_without_blocking_calls(self):
        engine = SimpleNamespace(config={'audio_profile': 'speech'})
        with patch('platforms.native_runtime.WINDOWS', False), patch.object(Path, 'is_file', return_value=False):
            configure(engine)
        self.assertEqual(engine.applied_audio_profile, 'normal')

    def test_normal_does_not_load_plugin(self):
        engine = SimpleNamespace(config={'audio_profile': 'normal'})
        with patch('ctypes.CDLL') as load:
            configure(engine)
        load.assert_not_called()
        self.assertEqual(engine.applied_audio_profile, 'normal')
