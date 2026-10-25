# @test T-HLT-029
# @requirements HLR-TERM-MAINT-012
# @environment display
# @plan Run installed-mode logging in a separate Python process with disposable persistent/runtime directories. Log before, during and after a real debug-expiry interval. Inspect stderr and persistent files. Use a real HTTP status exchange to verify operational peripheral connection, battery/charger and C20 power/unknown fields leave the terminal; inspect installed volatile storage separately in the opt-in host test.
# @pass INFO continues, DEBUG expires without restart, no terminal log file is created and status JSON omits credentials. The subprocess verifies application logging; RAM mounts and swap require the installed-host scenario.

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tests.support.terminal.config_endpoint import config_endpoint
from tests.support.terminal.ui_fixture import terminal_fixture, pump
from zmala_terminal.common.configuration import Configuration


@unittest.skipUnless(sys.platform == 'linux', 'Installed Linux logging mode')
class DiagnosticTests(unittest.TestCase):
    def test_real_process_debug_expiry_uses_stderr_not_persistent_log(self):
        code = '''import logging,sys,time
from pathlib import Path
from zmala_terminal.common.runtime_logging import configure
data=Path(sys.argv[1]); runtime=Path(sys.argv[2])
configure(data)
logging.info('normal-before'); logging.debug('hidden-before')
(runtime/'debug-until').write_text(str(time.monotonic()+2.2))
time.sleep(1.1)
logging.debug('visible-during')
time.sleep(1.2)
logging.debug('hidden-after'); logging.info('normal-after')
'''
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data, runtime = root/'persistent', root/'runtime'
            data.mkdir(); runtime.mkdir()
            result = subprocess.run([sys.executable, '-c', code, str(data), str(runtime)],
                env=dict(os.environ, ZMALA_LOG_STDERR='1', ZMALA_RUNTIME_DIR=str(runtime)),
                capture_output=True, text=True, timeout=8, check=True)
            self.assertEqual(result.stdout, '')
            for expected in ('normal-before', 'visible-during', 'normal-after'):
                self.assertIn(expected, result.stderr)
            self.assertNotIn('hidden-before', result.stderr)
            self.assertNotIn('hidden-after', result.stderr)
            self.assertEqual(list(data.iterdir()), [])

    @unittest.skipUnless(os.environ.get('DISPLAY'), 'Tk display required')
    def test_operational_status_request_is_separate_from_configuration_secrets(self):
        with terminal_fixture() as (app, directory), config_endpoint() as server, \
                patch('zmala_terminal.common.management.wifi_link_available', return_value=True):
            app.configuration = Configuration(server.bootstrap, directory/'cache.json')
            app.poll()
            pump(app, lambda: not app.worker_busy and not app.network_worker_busy)
            route, auth, body = next(r for r in server.requests if r[0] == '/api/status')
            self.assertEqual(auth, 'Bearer fixture-bearer-token')
            self.assertEqual(body, {'registered': True, 'camera': 'Fixture C20',
                                   'state': 'home', 'configuration_version': 1,
                                   'remote_status':'connected','remote_battery':75,'remote_charger_connected':False,
                                   'camera_powered':None,'camera_connected':None,'camera_status':'unknown'})
            encoded = json.dumps(body)
            for secret in (app.model.config['sip']['password'], app.model.config['call_auth_key'], server.bootstrap['device_token']):
                self.assertNotIn(secret, encoded)


if __name__ == '__main__':
    unittest.main()
