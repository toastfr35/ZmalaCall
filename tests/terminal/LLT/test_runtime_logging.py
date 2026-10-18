# @test T-LLT-032
# @requirements LLR-TERM-MAINT-009, LLR-TERM-MAINT-010
# @environment portable
# @plan Use temporary debug-expiry state and mocked camera startup; assert verbose logging expires without restart and camera diagnostics inherit the journal stream without opening persistent log files.
# @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

"""Volatile diagnostics must expire and never open persistent camera logs."""
import logging
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from zmala_terminal.common.runtime_logging import DiagnosticFilter
from zmala_terminal.common.qr_scanner import QRScanner


class RuntimeLoggingTests(unittest.TestCase):
    def test_verbose_logging_expires_without_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            control = Path(directory) / 'debug-until'
            filtering = DiagnosticFilter(directory)
            debug, info = Mock(levelno=logging.DEBUG), Mock(levelno=logging.INFO)
            with patch('zmala_terminal.common.runtime_logging.time.monotonic', return_value=10):
                self.assertFalse(filtering.filter(debug))
                self.assertTrue(filtering.filter(info))
            control.write_text('20')
            with patch('zmala_terminal.common.runtime_logging.time.monotonic', return_value=12):
                self.assertTrue(filtering.filter(debug))
            with patch('zmala_terminal.common.runtime_logging.time.monotonic', return_value=21):
                self.assertFalse(filtering.filter(debug))
                self.assertTrue(filtering.filter(info))
            control.write_text('broken')
            with patch('zmala_terminal.common.runtime_logging.time.monotonic', return_value=25):
                self.assertFalse(filtering.filter(debug))

    def test_journal_camera_diagnostics_inherit_stderr_without_file(self):
        with patch('zmala_terminal.common.qr_scanner.journal_logging', return_value=True), \
                patch('zmala_terminal.common.qr_scanner.subprocess.Popen') as popen, patch('zmala_terminal.common.qr_scanner.ProcessJob'), \
                patch('zmala_terminal.common.qr_scanner.threading.Thread'), patch('pathlib.Path.open') as opening:
            scanner = QRScanner(lambda value: None)
            self.assertIsNone(scanner.error_log)
            self.assertIsNone(popen.call_args.kwargs['stderr'])
            opening.assert_not_called()
            scanner.close()


if __name__ == '__main__':
    unittest.main()
