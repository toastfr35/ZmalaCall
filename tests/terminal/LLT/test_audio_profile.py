# @test T-LLT-005
# @requirements LLR-TERM-AUDIO-003
# @environment portable
# @plan Validate profile values and configure a fake native core; assert only the Pi loads the selected processing plugin and a missing plugin leaves calling available. Stub plugin registration to verify failed speech setup does not claim an applied profile and successful setup selects the requested echo parameters.
# @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

"""Server settings override local experiments; unsupported clients stay usable."""
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from zmala_terminal.common.audio_processing import configure, requested_profile
from tests.terminal.LLT.test_terminal import config
from zmala_terminal.common.configuration import validate


class AudioProfileTests(unittest.TestCase):
    def test_speech_plugin_uses_capped_rate_and_commits_profile_only_after_registration(self):
        from zmala_terminal.linux import audio_processing
        engine = Mock(audio_profile='speech', applied_audio_profile='normal', core=12)
        engine.dll.linphone_core_get_ms_factory.return_value = 42
        engine.core_get_config.return_value = 99
        with patch.object(Path, 'is_file', return_value=True), patch.object(audio_processing.C, 'CDLL') as load:
            plugin = load.return_value
            plugin.zmala_speech_audio_register.return_value = 1
            with self.assertRaisesRegex(RuntimeError, 'echo cancellation'):
                audio_processing.configure(engine)
            self.assertEqual(engine.applied_audio_profile, 'normal')
            engine.config_set_int.assert_not_called()
            plugin.zmala_speech_audio_register.return_value = 0
            audio_processing.configure(engine)
            self.assertEqual(engine.applied_audio_profile, 'speech')
            plugin.zmala_speech_audio_register.assert_called_with(42, 16000)
            engine.config_set_int.assert_called_once_with(99, b'sound', b'ec_tail_len', 500)

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

    def test_missing_plugin_falls_back_without_blocking_calls(self):
        engine = SimpleNamespace(config={'audio_profile': 'speech'})
        with patch('zmala_terminal.common.native_runtime.WINDOWS', False), patch.object(Path, 'is_file', return_value=False):
            configure(engine)
        self.assertEqual(engine.applied_audio_profile, 'normal')

    def test_normal_does_not_load_plugin(self):
        engine = SimpleNamespace(config={'audio_profile': 'normal'})
        with patch('ctypes.CDLL') as load:
            configure(engine)
        load.assert_not_called()
        self.assertEqual(engine.applied_audio_profile, 'normal')
