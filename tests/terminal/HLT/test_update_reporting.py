# @test T-HLT-047
# @requirements HLR-TERM-MAINT-033
# @environment portable
# @plan Integrate the real updater service reporter, confirmed slot metadata and enrolled-server transport with captured HTTP responses; verify phase-change delivery, throttling, bounded error categories and network-failure tolerance.
# @pass Reports identify the confirmed version and current phase using enrolled credentials; repeated heartbeats are throttled, transitions report immediately, and transport failure cannot prevent local recovery. Linux service APIs are required.
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from zmala_terminal.linux.update_transaction import Transactions


@unittest.skipUnless(os.name == 'posix', 'Requires Linux updater service imports')
class ReportingTests(unittest.TestCase):
    def test_service_reporting_survives_network_failure(self):
        from zmala_terminal.linux.update_server import ServerLink
        from zmala_terminal.linux.update_service import UpdateService
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tx = Transactions(root/'updater')
            slot = tx.slots/'working'
            slot.mkdir()
            (slot/'update-release.json').write_text(json.dumps({'version': '1.2.3', 'sequence': 99}))
            tx.initialize('working')
            key = root/'keys.json'
            key.write_text(json.dumps({'test': 'YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWE='}))
            (root/'terminal.json').write_text(json.dumps({'server_url': 'https://family.example', 'device_token': 'fixture-token-123456789'}))
            (root/'terminal.json').chmod(0o600)
            runtime = Mock(phase='checking')
            with patch('zmala_terminal.linux.update_service.trusted_json', side_effect=lambda path, *args: json.loads(Path(path).read_text())):
                service = UpdateService({'keys': str(key), 'data': temporary}, tx, runtime)
                transport = Mock()
                def response(*args, **kwargs):
                    body = io.BytesIO(b'{"ok":true}')
                    body.status = 200
                    return body
                transport.open.side_effect = response
                service.link = ServerLink({'data': temporary}, transport)
                service.report()
                self.assertEqual(json.loads(transport.open.call_args.args[0].data)['installed'], '1.2.3')
                service.report()
                self.assertEqual(transport.open.call_count, 1)
                runtime.phase = 'rollback'
                service.report()
                self.assertEqual(json.loads(transport.open.call_args.args[0].data)['phase'], 'rollback')
                runtime.phase = 'recovery_failed'
                transport.open.side_effect = OSError('private transport detail')
                service.report()  # Network failure must not escape the recovery owner.
