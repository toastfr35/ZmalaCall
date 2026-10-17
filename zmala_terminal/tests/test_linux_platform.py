"""Linux process ownership and network adapter tests; no physical devices required."""
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@unittest.skipUnless(sys.platform.startswith('linux'), 'Linux integration')
class LinuxPlatformTests(unittest.TestCase):
    def test_shell_output_unicode_failure_and_bound(self):
        from maintenance import run_command
        result = run_command("printf 'été 日本語'; printf 'error' >&2; exit 7", 5, threading.Event(), 'sh')
        self.assertEqual(result['status'], 'failed', result)
        self.assertEqual(result['exit_code'], 7)
        self.assertEqual(result['stdout'], 'été 日本語')
        self.assertEqual(result['stderr'], 'error')
        large = run_command("head -c 100000 /dev/zero | tr '\\0' x", 5, threading.Event(), 'bash')
        self.assertTrue(large['truncated'])
        self.assertLessEqual(len(large['stdout']) + len(large['stderr']), 65536)

    def test_timeout_and_cancellation_stop_descendants(self):
        from maintenance import run_command
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / 'child-survived'
            command = f"(sleep 2; touch '{marker}') & sleep 10"
            result = run_command(command, .3, threading.Event(), 'sh')
            self.assertEqual(result['status'], 'timed_out', result)
            cancelled = threading.Event()
            timer = threading.Timer(.2, cancelled.set)
            timer.start()
            result = run_command(command, 5, cancelled, 'bash')
            self.assertEqual(result['status'], 'cancelled', result)
            timer.join(); time.sleep(2.1)
            self.assertFalse(marker.exists(), 'A command descendant survived cancellation')

    def test_wifi_reset_only_removes_owned_connection(self):
        from platforms.linux_wifi import forget_wifi
        with patch('platforms.linux_wifi._nmcli', return_value='one') as command:
            forget_wifi({'linux_profile': 'Home', 'linux_uuid': 'one'}, 'terminal')
            command.assert_not_called()
            forget_wifi({'linux_profile': 'ZmalaCall-terminal-one', 'linux_uuid': 'one'}, 'terminal')
            self.assertEqual(command.call_args_list[0].args[0], ['-t', '-f', 'UUID', 'connection', 'show'])
            self.assertEqual(command.call_args_list[1].args[0], ['connection', 'delete', 'uuid', 'one'])
            command.reset_mock()
            command.return_value = ''
            forget_wifi({'linux_profile': 'ZmalaCall-terminal-one', 'linux_uuid': 'one'}, 'terminal')
            command.assert_called_once_with(['-t', '-f', 'UUID', 'connection', 'show'])


if __name__ == '__main__':
    unittest.main()
