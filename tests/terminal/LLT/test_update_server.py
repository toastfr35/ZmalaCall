# @test T-LLT-099
# @requirements LLR-TERM-MAINT-034
# @environment portable
# @plan Read private enrollment fixtures and capture updater HTTP requests; test HTTPS origin restrictions, token/header placement, redirect refusal, response bounds, symlinks and writable enrollment rejection.
# @pass Credentials are attached only to the enrolled server, never GitHub/CDNs; redirects are refused and malformed/unbounded inputs fail before trusted update consumption. POSIX file checks skip on Windows.
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from zmala_terminal.linux.update_server import ServerLink, NoRedirect
from zmala_terminal.linux.update_transaction import RecoveryError


class Response(io.BytesIO):
    status = 200


@unittest.skipUnless(os.name == 'posix', 'Requires POSIX private enrollment checks')
class ServerLinkTests(unittest.TestCase):
    def test_private_server_transport_bounds_and_credentials(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'terminal.json'
            enrollment = {'server_url': 'https://family.example', 'device_token': 'fixture-token-123456789'}
            def save():
                path.write_text(json.dumps(enrollment))
                path.chmod(0o600)
            save()
            transport = Mock()
            transport.open.return_value = Response(b'{"manifest":{"payload":"signed"}}')
            link = ServerLink({'data': temporary}, transport)
            self.assertEqual(json.loads(link.manifest()), {'payload': 'signed'})
            request = transport.open.call_args.args[0]
            self.assertEqual(request.full_url, 'https://family.example/api/terminal-updates/manifest')
            self.assertEqual(request.get_header('Authorization'), 'Bearer '+enrollment['device_token'])
            self.assertIsNone(NoRedirect().redirect_request(request, None, 302, '', {}, 'https://github.com'))
            profile = Path(temporary)/'terminal/provisioning.json'
            profile.parent.mkdir()
            profile.write_text(json.dumps({'version': 1, 'bootstrap': enrollment}))
            profile.chmod(0o600)
            self.assertEqual(link.enrollment(), enrollment)
            profile.write_text('{"version":1}')
            with self.assertRaises(RecoveryError):
                link.enrollment()  # Reset profiles cannot revive legacy credentials.
            profile.unlink()
            for url in ('http://family.example', 'https://github.com', 'https://api.github.com', 'https://family.example/path', 'https://user@family.example'):
                enrollment['server_url'] = url
                save()
                with self.assertRaises(RecoveryError):
                    link.enrollment()
            enrollment['server_url'] = 'https://family.example'
            save()
            transport.open.return_value = Response(b'x'*131073)
            with self.assertRaises(RecoveryError):
                link.request('/api/terminal-updates/manifest')
            path.chmod(0o666)
            with self.assertRaises(RecoveryError):
                link.enrollment()
            path.unlink()
            path.symlink_to(Path(temporary)/'missing')
            with self.assertRaises(OSError):
                link.enrollment()
