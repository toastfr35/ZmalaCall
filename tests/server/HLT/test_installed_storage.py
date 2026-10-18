# @test S-HLT-028
# @requirements HLR-SRV-HOST-002, HLR-SRV-START-001
# @environment hardware
# @plan On the installed Pi server after reboot, set ZMALA_INSTALLED_HOST_TESTS=server and run this suite as an administrator. Inspect effective journal limits, RAM-only swap without backing storage, tmpfs temporary/runtime paths, noatime, active automatic service and persistent server/password paths. Read metadata only; do not change the host or print credentials.
# @pass All installed-policy assertions pass. Without the explicit target flag this test is skipped, never counted as installed-host acceptance. Reboot persistence is qualified only when the operator records the reboot and test result together.

import os
from pathlib import Path
import sys
import unittest

from tests.support.installed_host import assert_installed_storage, command


@unittest.skipUnless(sys.platform == 'linux' and os.environ.get('ZMALA_INSTALLED_HOST_TESTS') == 'server',
                     'Run explicitly on the installed Pi server after reboot')
class InstalledStorageTests(unittest.TestCase):
    def test_effective_storage_and_automatic_service(self):
        data = assert_installed_storage(self, 'zmalacall-server', '/var/lib/zmalacall-server')
        self.assertEqual(command('systemctl', 'is-enabled', 'zmalacall-server'), 'enabled')
        self.assertEqual(Path('/opt/zmalacall-server/current/zmala_server/data').resolve(), data)
        for name in ('server.json', 'admin-password.json'):
            target = data/name
            self.assertTrue(target.is_file())
            self.assertEqual(target.stat().st_mode & 0o077, 0, 'Server state must not be world/group readable')


if __name__ == '__main__':
    unittest.main()
