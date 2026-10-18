# @test T-LLT-032
# @requirements LLR-TERM-MAINT-019, LLR-TERM-MAINT-020
# @environment portable
# @plan Check the installed Linux logging flag and inspect real handlers with logger registration mocked; assert journal output has an expiry filter and no persistent filename. Use temporary debug-expiry state and mocked camera startup; assert verbose logging expires without restart and camera diagnostics inherit the journal stream without opening persistent log files. Exercise the debug helper with a temporary runtime directory; assert duration bounds, running-terminal prerequisite and atomic expiry replacement.
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
from zmala_terminal.common import runtime_logging
from zmala_terminal.common.qr_scanner import QRScanner


class RuntimeLoggingTests(unittest.TestCase):
    def test_installed_linux_logging_uses_filtered_journal_handler(self):
        with patch.object(runtime_logging.sys, 'platform', 'linux'), \
                patch.dict(runtime_logging.os.environ, {}, clear=True):
            self.assertFalse(runtime_logging.journal_logging())
            runtime_logging.os.environ['ZMALA_LOG_STDERR'] = '0'
            self.assertFalse(runtime_logging.journal_logging())
            runtime_logging.os.environ.update(ZMALA_LOG_STDERR='1', ZMALA_RUNTIME_DIR='/run/zmala-test')
            self.assertTrue(runtime_logging.journal_logging())
            with patch.object(runtime_logging.logging, 'basicConfig') as configure:
                runtime_logging.configure('/persistent-data')
            options = configure.call_args.kwargs
            self.assertNotIn('filename', options)
            self.assertEqual(options['level'], logging.DEBUG)
            handler, = options['handlers']
            self.assertIsInstance(handler, logging.StreamHandler)
            self.assertIs(handler.stream, sys.stderr)
            filtering, = handler.filters
            self.assertIsInstance(filtering, DiagnosticFilter)
            self.assertEqual(filtering.control, Path('/run/zmala-test/debug-until'))

    def test_diagnostic_helper_bounds_duration_requires_runtime_and_replaces_expiry(self):
        from tests.terminal.LLT.test_pi_install import module
        helper = module('diagnostics')
        with tempfile.TemporaryDirectory() as directory, patch.object(helper, 'Path', return_value=Path(directory)), \
                patch.object(helper.time, 'monotonic', return_value=100), patch('builtins.print'), \
                patch.object(sys, 'argv', ['diagnostics', '10']):
            helper.main()
            self.assertEqual((Path(directory)/'debug-until').read_text(), '700')
            self.assertFalse((Path(directory)/'debug-until.tmp').exists())
            sys.argv = ['diagnostics', '0']; helper.main()
            self.assertEqual((Path(directory)/'debug-until').read_text(), '100')
            for value in ('-1', '61'):
                sys.argv = ['diagnostics', value]
                with patch.object(sys, 'stderr', Mock()), self.assertRaises(SystemExit) as error:
                    helper.main()
                self.assertEqual(error.exception.code, 2)
            sys.argv = ['diagnostics']
            with patch.object(Path, 'is_dir', return_value=False), patch.object(sys, 'stderr', Mock()), self.assertRaises(SystemExit) as error:
                helper.main()
            self.assertEqual(error.exception.code, 2)

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
