# @test A-LLT-006
# @requirements LLR-AND-ENROLL-002
# @environment native-display
# @plan On an explicitly selected disposable emulator with the debug APK installed, write a
# synthetic enrollment into private no-backup storage. Clear app data through Android's package
# manager, verify the enrollment is absent, then launch and inspect the QR welcome action.
# @pass Android clears enrollment and the relaunched app offers Scan setup QR without Reset setup.
"""Host-side app-data check; never clears a physical phone or automatically chooses a device."""
import json
import os
import subprocess
import time
import unittest


class ClearAppDataTest(unittest.TestCase):
    def test_clear_returns_to_qr_setup(self):
        serial = os.environ.get('ANDROID_SERIAL', '')
        self.assertTrue(serial.startswith('emulator-'), 'Select a disposable emulator explicitly.')
        package = 'org.zmala.phone'

        def adb(*args, data=None, check=True):
            return subprocess.run(['adb', '-s', serial, *args], input=data, text=True,
                                  capture_output=True, check=check, timeout=30)

        adb('shell', 'am', 'force-stop', package)
        adb('shell', 'run-as', package, 'mkdir', '-p', 'no_backup')
        enrollment = json.dumps({'type': 'family-call-server', 'version': 1,
                                 'account_type': 'app', 'server_url': 'http://127.0.0.1:9',
                                 'device_id': 'ZP-12345678-1234-1234-1234-123456789abc',
                                 'device_token': 'abcdefghijklmnopqrstuvwx'})
        adb('shell', 'run-as', package, 'sh', '-c', "'cat > no_backup/enrollment.json'", data=enrollment)
        self.assertEqual(adb('shell', 'run-as', package, 'cat', 'no_backup/enrollment.json').stdout, enrollment)
        self.assertIn('Success', adb('shell', 'pm', 'clear', package).stdout)
        missing = adb('shell', 'run-as', package, 'ls', 'no_backup/enrollment.json', check=False)
        self.assertNotEqual(missing.returncode, 0)
        adb('shell', 'am', 'start', '-n', package + '/.MainActivity')
        deadline = time.monotonic() + 15
        xml = ''
        while time.monotonic() < deadline:
            adb('shell', 'uiautomator', 'dump', '/sdcard/zmala-clear-check.xml')
            xml = adb('shell', 'cat', '/sdcard/zmala-clear-check.xml').stdout
            if 'Scan setup QR' in xml:
                break
            time.sleep(.2)
        self.assertIn('Scan setup QR', xml)
        self.assertNotIn('Reset setup', xml)
        adb('shell', 'rm', '/sdcard/zmala-clear-check.xml')


if __name__ == '__main__':
    unittest.main()
