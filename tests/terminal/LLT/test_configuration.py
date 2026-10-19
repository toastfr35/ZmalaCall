# @test T-LLT-011
# @requirements LLR-TERM-COM-003, LLR-TERM-COM-006, LLR-TERM-COM-008
# @environment portable
# @plan Inject settings and polling replies, older revisions and redirects; assert cached configuration never rolls back, photo policy stays consistent and enrollment credentials are not forwarded to redirects.
# @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

"""Enrollment HTTP/cache boundaries; all endpoints and files are isolated fixtures."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from zmala_terminal.common.configuration import Configuration
from tests.terminal.LLT.test_terminal import config


class ConfigurationTests(unittest.TestCase):
    def test_settings_response_rejects_rollback_without_replacing_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            client = Configuration({'device_id': 'test'}, Path(folder) / 'cache.json')
            client.photos = Mock()
            latest = config() | {'configuration_version': 5}
            client.request = Mock(return_value=json.dumps(latest))
            client.fetch()
            saved = client.cache.read_bytes()
            client.request.return_value = json.dumps(config())
            with self.assertRaisesRegex(ValueError, 'older configuration'):
                client.update_settings({'language': 'fr'}, {'language': 'en'})
            self.assertEqual(client.cache.read_bytes(), saved)
            self.assertEqual(client.current['configuration_version'], 5)

    def test_poll_and_settings_responses_share_stable_cache_and_photo_policy(self):
        for operation in ('poll', 'settings'):
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as folder:
                client = Configuration({'device_id': 'test'}, Path(folder) / 'cache.json')
                client.photos = Mock()
                reply = config() | {'callbacks': []}
                reply['contacts'][0]['presence'] = 'push'
                reply['contacts'][0]['online'] = True
                client.request = Mock(return_value=json.dumps(reply))
                result = client.fetch() if operation == 'poll' else client.update_settings({}, {})
                self.assertTrue(result['contacts'][0]['online'])
                durable = json.loads(client.cache.read_text())
                self.assertNotIn('callbacks', durable)
                self.assertNotIn('online', durable['contacts'][0])
                self.assertNotIn('presence', durable['contacts'][0])
                client.photos.schedule.assert_called_once_with(reply['contacts'])
                client.deactivate()
                client.request.reset_mock()
                with self.assertRaises(RuntimeError):
                    client.fetch()
                client.request.assert_not_called()

    def test_redirect_does_not_forward_enrollment_token(self):
        received = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_GET(self):
                received.append((self.path, self.headers.get('Authorization')))
                self.send_response(302)
                self.send_header('Location', '/unexpected-target')
                self.end_headers()

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with tempfile.TemporaryDirectory() as folder:
                client = Configuration({'device_id': 'test', 'device_token': 'fixture-token',
                    'server_url': f'http://127.0.0.1:{server.server_port}'}, Path(folder) / 'cache.json')
                with self.assertRaises(HTTPError) as raised:
                    client.request('/api/config')
                self.assertEqual(raised.exception.code, 302)
                raised.exception.close()
                self.assertEqual(received, [('/api/config', 'Bearer fixture-token')])
        finally:
            server.shutdown()
            server.server_close()
            worker.join(2)
