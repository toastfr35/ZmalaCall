# Installer regression tests; outside the Pi runtime requirements baseline.
"""Exercise real subprocess failures without installing or changing the host."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import signal
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('install_runner', ROOT / 'build_tools/linux/install-runner.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


@unittest.skipUnless(os.name == 'posix', 'Installer runs on Linux')
class InstallRunnerTests(unittest.TestCase):
    def test_interrupted_child_escalates_owned_process_group_and_preserves_log(self):
        import subprocess
        process = Mock(pid=123)
        class InterruptedOutput:
            def __iter__(self):
                raise KeyboardInterrupt
            close = Mock()
        process.stdout = InterruptedOutput()
        process.poll.return_value = None
        process.wait.side_effect = [subprocess.TimeoutExpired('installer', 10), -9]
        with patch.object(runner.subprocess, 'Popen', return_value=process), patch.object(runner.os, 'killpg') as kill:
            result, output, log = self.invoke(['unit-installer'])
        self.assertEqual(result, 130)
        self.assertIn('Installation interrupted', log)
        self.assertIn('INSTALLATION FAILED', output)
        self.assertEqual([call.args for call in kill.call_args_list], [(123, signal.SIGTERM), (123, signal.SIGKILL)])
        process.stdout.close.assert_called_once()
        with self.assertRaises(KeyboardInterrupt):
            runner.interrupted(signal.SIGTERM, None)

    def invoke(self, command):
        with tempfile.TemporaryDirectory() as folder:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = runner.run_install(command, folder)
            logs = list(Path(folder).glob('*.log'))
            self.assertEqual(len(logs), 1)
            self.assertEqual(logs[0].stat().st_mode & 0o777, 0o600)
            return result, output.getvalue(), logs[0].read_text()

    def test_failure_preserves_exit_code_stdout_and_stderr(self):
        result, output, log = self.invoke([sys.executable, '-c',
            'import sys; print("stage marker"); print("download failed", file=sys.stderr); sys.exit(23)'])
        self.assertEqual(result, 23)
        for text in ('stage marker', 'download failed', 'INSTALLATION FAILED', 'rerun the same install command'):
            self.assertIn(text, log)
            self.assertIn(text, output)
        self.assertNotIn('completed successfully', log)

    def test_success_is_logged(self):
        result, output, log = self.invoke([sys.executable, '-c', 'print("work finished")'])
        self.assertEqual(result, 0)
        self.assertIn('completed successfully', log)
        self.assertIn('work finished', output)
        self.assertNotIn('FAILED', log)

    def test_cannot_launch_installer(self):
        result, _, log = self.invoke(['/nonexistent/zmala-installer'])
        self.assertNotEqual(result, 0)
        self.assertIn('INSTALLATION FAILED', log)

    def test_killed_child_is_failure(self):
        result, _, log = self.invoke([sys.executable, '-c',
            'import os, signal; os.kill(os.getpid(), signal.SIGTERM)'])
        self.assertEqual(result, 128 + signal.SIGTERM)
        self.assertIn('INSTALLATION FAILED', log)


if __name__ == '__main__':
    unittest.main()
