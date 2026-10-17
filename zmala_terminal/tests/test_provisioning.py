import json
import base64
from pathlib import Path
import sys
import tempfile
import threading
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from provisioning import Enrollment, parse_wifi, parse_server
from configuration import Configuration
from maintenance import run_command
from platforms.windows_wifi import profile_xml
import xml.etree.ElementTree as ET


class ProvisioningTests(unittest.TestCase):
    def test_enrollment_reset_survives_restart_without_affecting_legacy_bootstrap(self):
        with tempfile.TemporaryDirectory() as directory:
            legacy = Path(directory) / 'terminal.json'
            legacy.write_text('{"server_url":"http://127.0.0.1:8080"}')
            enrollment = Enrollment(Path(directory) / 'profile')
            self.assertIsNone(enrollment.stage)
            enrollment.reset()
            self.assertEqual(Enrollment(Path(directory) / 'profile').stage, 'wifi')
            enrollment.set_wifi({'ssid': 'Example', 'password': 'test12345'})
            self.assertEqual(Enrollment(Path(directory) / 'profile').stage, 'server')
            enrollment.set_server({'device_token': 'secret', 'device_id': 'one'})
            self.assertIsNone(enrollment.stage)
            enrollment.reset()
            self.assertEqual(enrollment.value, {'version': 1})
            self.assertTrue(legacy.exists())
            self.assertNotIn('test12345', enrollment.path.read_text())
            self.assertNotIn('secret', enrollment.path.read_text())

    def test_reset_keeps_only_language_through_wifi_setup_and_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            enrollment = Enrollment(directory)
            enrollment.reset()
            enrollment.set_server({'device_token': 'old-secret'})
            enrollment.reset(language='fr')
            self.assertEqual(enrollment.value, {'version': 1, 'language': 'fr'})
            enrollment.set_wifi({'ssid': 'test'})
            restored = Enrollment(directory)
            self.assertEqual(restored.value['language'], 'fr')
            self.assertEqual(restored.stage, 'server')
            self.assertNotIn('old-secret', restored.path.read_text())

    def test_qr_types_escaping_unicode_and_schema(self):
        wifi = parse_wifi('WIFI:T:WPA;S:Café\\;Wi\\:Fi\\\\\\";P:Secret\\;\\:\\\\\\,\\";H:true;;')
        self.assertEqual(wifi['ssid'], 'Café;Wi:Fi\\"')
        self.assertEqual(wifi['password'], 'Secret;:\\,"')
        self.assertTrue(wifi['hidden'])
        name = 'Café 日本語'.encode('utf-8')
        packed = bytes([3, len(name)]) + name + b'test12345'
        compact = 'FAMILY-WIFI:1:' + base64.urlsafe_b64encode(packed).decode().rstrip('=')
        decoded = parse_wifi(compact)
        self.assertEqual(decoded['ssid'], 'Café 日本語')
        self.assertEqual(decoded['password'], 'test12345')
        self.assertTrue(decoded['hidden'])
        self.assertEqual(parse_wifi('WIFI:T:nopass;S:Open;;')['security'], 'nopass')
        for bad in ['not wifi', 'WIFI:T:WPA;S:One;P:short;;', 'WIFI:T:WEP;S:One;;', 'WIFI:S:One;S:Two;;', 'WIFI:S:One', 'WIFI:T:nopass;S:One;P:secret;;']:
            with self.assertRaises(ValueError):
                parse_wifi(bad)
        bootstrap = {'type': 'family-call-server', 'version': 1, 'server_url': 'http://127.0.0.1:8080/', 'device_id': 'terminal-1', 'device_token': 'a'*40}
        self.assertEqual(parse_server(json.dumps(bootstrap))['server_url'], 'http://127.0.0.1:8080')
        for bad in [{'version': True}, {'type': 'wifi'}, {'server_url': 'file:///tmp/a'}, {'server_url': 'http://user:pass@host'}, {'device_token': 'short'}, {'device_id': '../escape'}]:
            with self.assertRaises(ValueError):
                parse_server(json.dumps(bootstrap | bad))

    def test_reset_blocks_stale_configuration_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / 'cache.json'
            configuration = Configuration({'device_id': 'one'}, cache)
            configuration.persist({'secret': 'old'})
            configuration.deactivate(erase=True)
            with self.assertRaises(RuntimeError):
                configuration.persist({'secret': 'late response'})
            self.assertFalse(cache.exists())

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
        cancelled = threading.Event()
        cmd = run_command('echo hello cmd\r\necho été 日本語\r\nexit /b 7', 5, cancelled, 'cmd')
        self.assertEqual(cmd['exit_code'], 7, cmd)
        self.assertEqual(cmd['status'], 'failed', cmd)
        self.assertIn('hello cmd', cmd['stdout'])
        self.assertIn('été 日本語', cmd['stdout'])
        self.assertEqual(run_command('echo success', 5, cancelled, 'cmd')['status'], 'completed')
        self.assertEqual(run_command('ping.exe -n 8 127.0.0.1 >nul', 1, cancelled, 'cmd')['status'], 'timed_out')
        pwsh = run_command("Write-Output $PSVersionTable.PSVersion.Major; Write-Output 'été 日本語'", 5, cancelled, 'pwsh')
        self.assertEqual(pwsh['status'], 'completed', pwsh)
        self.assertTrue(pwsh['stdout'].startswith('7'), pwsh)
        self.assertIn('été 日本語', pwsh['stdout'])
        self.assertEqual(run_command('exit 9', 5, cancelled, 'pwsh')['exit_code'], 9)
        self.assertEqual(run_command('echo hello', 5, cancelled, 'invalid')['status'], 'failed')

    def test_command_output_exit_failure_unicode_and_timeout(self):
        cancelled = threading.Event()
        result = run_command("Write-Output 'hello console'; Write-Output 'été 日本語'", 5, cancelled)
        self.assertEqual(result['status'], 'completed', result)
        self.assertEqual(result['exit_code'], 0)
        self.assertIn('été 日本語', result['stdout'])
        self.assertEqual(run_command('exit 7', 5, cancelled)['exit_code'], 7)
        error = run_command("Write-Error 'sample failure'", 5, cancelled)
        self.assertEqual(error['status'], 'failed', error)
        self.assertIn('sample failure', error['stderr'])
        timeout = run_command('Start-Sleep -Seconds 10', 1, cancelled)
        self.assertEqual(timeout['status'], 'timed_out', timeout)
        large = run_command("Write-Output ('x' * 100000)", 5, cancelled)
        self.assertTrue(large['truncated'])
        self.assertLessEqual(len(large['stdout']) + len(large['stderr']), 65536)


if __name__ == '__main__':
    unittest.main()
