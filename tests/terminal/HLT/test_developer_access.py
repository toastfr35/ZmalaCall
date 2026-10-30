# @test T-HLT-037
# @requirements HLR-TERM-NET-008
# @environment hardware
# @plan On an enrolled Pi with developer access manually enabled and C20 facing the TV, run this opt-in check with an operator-configured SSH alias that jumps through the server to loopback port 22001. Confirm the returned hostname is the intended Pi and normal terminal service remains active. Then deactivate through the admin UI, confirm the established shell closes and a new connection fails, and verify credentials/runtime files were removed. Repeat activation with a new password and verify the old password fails.
# @pass The automated opt-in assertions establish shell reachability and service continuity only. Closure, password rotation and TV picture checks require recorded hardware evidence; skipped checks are not passes.
import os
import subprocess
import unittest


@unittest.skipUnless(os.environ.get('ZMALA_DEVELOPER_SSH_ALIAS'), 'Explicit hardware SSH alias required')
class DeveloperShellTests(unittest.TestCase):
    def test_shell_reaches_expected_terminal_without_stopping_calls(self):
        result = subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10',
                                 os.environ['ZMALA_DEVELOPER_SSH_ALIAS'],
                                 'hostname; systemctl is-active zmalacall-terminal'],
                                capture_output=True,text=True,timeout=20,check=True)
        self.assertEqual(result.stdout.splitlines(),[os.environ['ZMALA_DEVELOPER_HOSTNAME'],'active'])
