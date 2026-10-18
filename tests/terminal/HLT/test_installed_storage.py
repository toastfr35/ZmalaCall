# @test T-HLT-030
# @requirements HLR-TERM-MAINT-012
# @environment hardware
# @plan On the installed Pi terminal after reboot, set ZMALA_INSTALLED_HOST_TESTS=terminal and run as an administrator. Inspect effective journal, swap, temporary/runtime mounts, root access-time policy, service logging and persistent terminal data. Read configuration metadata only; do not modify files or display enrollment secrets.
# @pass Installed volatile storage and service settings match the policy and terminal data remains on persistent storage. Without explicit opt-in the test skips. Pair this result with a recorded reboot; a workstation run cannot qualify Pi storage.

import os
import sys
import unittest

from tests.support.installed_host import assert_installed_storage, command


@unittest.skipUnless(sys.platform == 'linux' and os.environ.get('ZMALA_INSTALLED_HOST_TESTS') == 'terminal',
                     'Run explicitly on the installed Pi terminal after reboot')
class InstalledStorageTests(unittest.TestCase):
    def test_effective_storage_and_journal_environment(self):
        assert_installed_storage(self, 'zmalacall-terminal', '/opt/zmalacall/current/zmala_terminal/data')
        environment = command('systemctl', 'show', 'zmalacall-terminal', '-p', 'Environment', '--value')
        self.assertIn('ZMALA_LOG_STDERR=1', environment)
        self.assertIn('ZMALA_RUNTIME_DIR=/run/zmalacall', environment)


if __name__ == '__main__':
    unittest.main()
