"""Windows WLAN profile and real shell regression checks."""
from pathlib import Path
import sys
import threading
import unittest
import xml.etree.ElementTree as ET
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from zmala_terminal.common.maintenance import run_command
from zmala_terminal.windows.wifi import profile_xml

class WifiProfileTests(unittest.TestCase):
    def test_windows_profile_escapes_network_credentials(self):
        wifi = {'ssid': 'A&B<>', 'password': 'secret<&123', 'security': 'WPA', 'hidden': True}
        xml = profile_xml(wifi, 'FamilyCall-test-123')
        root = ET.fromstring(xml)
        ns = {'w': 'http://www.microsoft.com/networking/WLAN/profile/v1'}
        self.assertEqual(root.find('w:SSIDConfig/w:SSID/w:name', ns).text, wifi['ssid'])
        self.assertEqual(root.find('w:MSM/w:security/w:sharedKey/w:keyMaterial', ns).text, wifi['password'])


@unittest.skipUnless(sys.platform == 'win32', 'Windows shell integration')
class MaintenanceTests(unittest.TestCase):
    def test_configured_windows_shells_preserve_output_and_failures(self):
        # Cold PowerShell startup on hosted runners can exceed five seconds.
        # Explicit timeout probes below still use one second.
        cancelled = threading.Event()
        cmd = run_command('echo hello cmd\r\necho été 日本語\r\nexit /b 7', 30, cancelled, 'cmd')
        self.assertEqual(cmd['exit_code'], 7, cmd)
        self.assertEqual(cmd['status'], 'failed', cmd)
        self.assertIn('hello cmd', cmd['stdout'])
        self.assertIn('été 日本語', cmd['stdout'])
        self.assertEqual(run_command('echo success', 30, cancelled, 'cmd')['status'], 'completed')
        self.assertEqual(run_command('ping.exe -n 8 127.0.0.1 >nul', 1, cancelled, 'cmd')['status'], 'timed_out')
        pwsh = run_command("Write-Output $PSVersionTable.PSVersion.Major; Write-Output 'été 日本語'", 30, cancelled, 'pwsh')
        self.assertEqual(pwsh['status'], 'completed', pwsh)
        self.assertTrue(pwsh['stdout'].startswith('7'), pwsh)
        self.assertIn('été 日本語', pwsh['stdout'])
        self.assertEqual(run_command('exit 9', 30, cancelled, 'pwsh')['exit_code'], 9)
        self.assertEqual(run_command('echo hello', 30, cancelled, 'invalid')['status'], 'failed')

    def test_command_output_exit_failure_unicode_and_timeout(self):
        # Cold PowerShell startup on hosted runners can exceed five seconds.
        # Explicit timeout probes below still use one second.
        cancelled = threading.Event()
        result = run_command("Write-Output 'hello console'; Write-Output 'été 日本語'", 30, cancelled)
        self.assertEqual(result['status'], 'completed', result)
        self.assertEqual(result['exit_code'], 0)
        self.assertIn('été 日本語', result['stdout'])
        self.assertEqual(run_command('exit 7', 30, cancelled)['exit_code'], 7)
        error = run_command("Write-Error 'sample failure'", 30, cancelled)
        self.assertEqual(error['status'], 'failed', error)
        self.assertIn('sample failure', error['stderr'])
        timeout = run_command('Start-Sleep -Seconds 10', 1, cancelled)
        self.assertEqual(timeout['status'], 'timed_out', timeout)
        large = run_command("Write-Output ('x' * 100000)", 30, cancelled)
        self.assertTrue(large['truncated'])
        self.assertLessEqual(len(large['stdout']) + len(large['stderr']), 65536)
