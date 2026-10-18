# @test T-LLT-008
# @requirements LLR-TERM-AUDIO-007
# @environment portable
# @plan Mock mixer execution at zero, full and invalid levels and on device failures; assert playback-only writes, validation before execution and nonfatal failure.
# @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

"""Hardware volume uses a stable C20 identity and fails safely if USB is absent."""
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from zmala_terminal.common.configuration import validate
from zmala_terminal.linux.c20_volume import apply
from tests.terminal.LLT.test_terminal import config


class C20VolumeTests(unittest.TestCase):
    def test_reject_invalid_volume_before_running_a_command(self):
        with patch('zmala_terminal.linux.c20_volume.subprocess.run') as run:
            for value in [-1, 101, 50.5, '50', True, None]:
                with self.subTest(value=value), self.assertRaises(ValueError):
                    apply(value)
                with self.subTest(value=value), self.assertRaises(ValueError):
                    validate(config() | {'c20_speaker_volume': value}, 'test')
            run.assert_not_called()

    def test_playback_only_at_zero_and_full_volume(self):
        with patch('zmala_terminal.linux.c20_volume.subprocess.run') as run:
            for value in [0, 50, 100]:
                self.assertTrue(apply(value))
                run.assert_called_with(['amixer', '-q', '-c', 'C20', 'sset', 'PCM', f'{value}%'],
                                       check=True, capture_output=True, timeout=5)

    def test_missing_or_unresponsive_device_is_nonfatal(self):
        for error in [FileNotFoundError(), subprocess.CalledProcessError(1, 'amixer'),
                      subprocess.TimeoutExpired('amixer', 5)]:
            with self.subTest(error=error), patch('zmala_terminal.linux.c20_volume.subprocess.run', side_effect=error):
                self.assertFalse(apply(50))

    def test_old_configuration_without_volume_is_valid(self):
        self.assertEqual(validate(config(), 'test'), config())
