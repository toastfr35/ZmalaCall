import json
import base64
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from zmala_terminal.common.provisioning import Enrollment, parse_wifi, parse_server
from zmala_terminal.common.configuration import Configuration


class ProvisioningTests(unittest.TestCase):
    def test_existing_provisioning_file_survives_source_reorganization(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'provisioning.json'
            saved = {'version': 1, 'language': 'fr', 'wifi': {'linux_uuid': 'saved-profile'},
                     'bootstrap': {'device_id': 'term2', 'device_token': 'saved-token'}}
            path.write_text(json.dumps(saved), encoding='utf-8')
            enrollment = Enrollment(directory)
            self.assertEqual(enrollment.value, saved)
            self.assertIsNone(enrollment.stage)
            enrollment.reset()
            self.assertNotIn('bootstrap', json.loads(path.read_text(encoding='utf-8')))
            self.assertEqual(Enrollment(directory).stage, 'wifi')

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



if __name__ == '__main__':
    unittest.main()
