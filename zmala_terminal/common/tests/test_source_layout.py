"""Source moves must preserve data paths and isolated-worker module entry points."""
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from zmala_terminal.common import configuration, native_runtime, qr_scanner
from zmala_terminal.common.paths import ROOT
from zmala_terminal.linux.auto_framing import AutoFraming


class SourceLayoutTests(unittest.TestCase):
    def test_state_stays_outside_common_and_platform_packages(self):
        self.assertEqual(ROOT, Path(__file__).resolve().parents[2])
        for module in (configuration, native_runtime, qr_scanner):
            self.assertEqual(module.ROOT, ROOT)
        self.assertTrue((ROOT / 'common/assets/gentle-chime.wav').is_file())
        self.assertTrue((ROOT / 'common/assets/zmala-icon.png').is_file())

    def test_framing_model_matches_linux_installer_directory(self):
        framing = AutoFraming(Mock(), ROOT)
        self.assertEqual(framing.model, ROOT / 'linux/media/models/person.tflite')

    def test_qr_worker_module_starts_without_camera_or_native_sdk(self):
        result = subprocess.run([sys.executable, '-m', 'zmala_terminal.common.qr_worker', '--help'],
                                cwd=ROOT.parent, capture_output=True, text=True, timeout=10,
                                **native_runtime.process_options())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--window', result.stdout)
