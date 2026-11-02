# @test T-HLT-041
# @requirements HLR-TERM-MAINT-023
# @environment portable
# @plan Build a disposable signed archive and run manifest authentication, digest verification and real bounded extraction; inspect candidate bytes and preserved confirmed/shared fixtures, then reject a changed archive before staging.
# @pass A compatible signed candidate stages without changing confirmed/shared files; altered payload bytes fail before extraction. POSIX-only system scenario; no production key, network or host installation is used.
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from tests.support.update_payload import COMPATIBILITY,archive_bytes,signed_fixture,envelope
from zmala_terminal.linux.update_package import verify_manifest,verify_package,extract_package
from zmala_terminal.linux.update_transaction import RecoveryError

@unittest.skipUnless(os.name=='posix','Requires POSIX staging durability')
class StagingIntegrationTests(unittest.TestCase):
    def test_authenticated_staging_preserves_confirmed_and_shared_state(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);confirmed=root/'confirmed';shared=root/'shared'
            confirmed.write_bytes(b'working');shared.write_bytes(b'enrollment')
            data=archive_bytes([('zmala_terminal/common/main.py',b'candidate',tarfile.REGTYPE)])
            payload,key,keys=signed_fixture(data)
            manifest=verify_manifest(envelope(payload,key),keys,COMPATIBILITY,73)
            package=root/'download';package.write_bytes(data)
            verify_package(package,manifest);extract_package(package,root/'candidate')
            self.assertEqual((root/'candidate/zmala_terminal/common/main.py').read_bytes(),b'candidate')
            package.write_bytes(b'tampered')
            with self.assertRaises(RecoveryError):verify_package(package,manifest)
            self.assertEqual(confirmed.read_bytes(),b'working');self.assertEqual(shared.read_bytes(),b'enrollment')
