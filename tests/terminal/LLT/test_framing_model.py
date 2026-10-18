# @test T-LLT-050
# @requirements LLR-TERM-VIDEO-017
# @environment portable
# @plan Inject detector construction failure into the actual call worker; assert wide-view fallback and unavailable status with no network fetch.
# @pass Runtime detector failure retains full-frame operation and cannot trigger a dependency download.

from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from zmala_terminal.linux.auto_framing import AutoFraming, WIDE

ROOT = Path(__file__).resolve().parents[3]


class FramingModelTests(unittest.TestCase):

    def test_detector_failure_returns_wide_without_runtime_download(self):
        framing = AutoFraming(Mock(), ROOT/'zmala_terminal')
        framing.enabled = True
        framing.closed = Mock(); framing.closed.is_set.side_effect = [False, True]
        framing.changed = Mock()
        framing.plugin.zmala_framing_take.return_value = 1 << 32
        with patch('zmala_terminal.linux.auto_framing.PersonDetector', side_effect=FileNotFoundError('model missing')) as detector, \
                patch('urllib.request.urlopen') as network, \
                patch('zmala_terminal.linux.auto_framing.os.setpriority', create=True), \
                patch('zmala_terminal.linux.auto_framing.os.PRIO_PROCESS', 0, create=True):
            with self.assertLogs(level='ERROR'):
                framing._run()
        detector.assert_called_once_with(framing.model)
        network.assert_not_called()
        framing.plugin.zmala_framing_target.assert_called_once_with(1 << 32, *WIDE)
        self.assertEqual(framing.status, 'unavailable')
