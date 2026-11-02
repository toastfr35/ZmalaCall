# @test T-LLT-093
# @requirements LLR-TERM-MAINT-024
# @environment portable
# @plan Generate disposable signed manifests; alter trust, signature, sequence, compatibility, size, URL and JSON fields. Extract regular-file fixtures and reject traversal, hidden/runtime data, duplicate and link/device entries under bounded counts/sizes. Compare extracted bytes and reject package tampering.
# @pass Only authenticated compatible newer manifests and safe bounded payloads are accepted. POSIX extraction/fsync cases skip on Windows; keys are test-only.
import copy
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from tests.support.update_payload import COMPATIBILITY,archive_bytes,signed_fixture,envelope
from zmala_terminal.linux.update_package import verify_manifest,verify_package,extract_package
from zmala_terminal.linux.update_transaction import RecoveryError


class UpdatePackageTests(unittest.TestCase):
    def test_manifest_authentication_and_compatibility(self):
        payload,key,keys=signed_fixture(b'payload')
        self.assertEqual(verify_manifest(envelope(payload,key),keys,COMPATIBILITY,73),payload)
        for field,value in [('sequence',73),('sequence',True),('schema',2),('version','../escape'),('commit','x'*40),('compatibility',{})]:
            changed=copy.deepcopy(payload);changed[field]=value
            with self.subTest(field=field,value=value),self.assertRaises(RecoveryError):
                verify_manifest(envelope(changed,key),keys,COMPATIBILITY,73)
        for field,value in [('size',True),('size',0),('size',2**40),('sha256','bad'),('url','https://evil.invalid/payload')]:
            changed=copy.deepcopy(payload);changed['package'][field]=value
            with self.subTest(field=field),self.assertRaises(RecoveryError):
                verify_manifest(envelope(changed,key),keys,COMPATIBILITY,73)
        with self.assertRaises(RecoveryError):verify_manifest(envelope(payload,key),{},COMPATIBILITY,73)
        data=envelope(payload,key).replace(b'0.3.65',b'0.3.66')
        with self.assertRaises(RecoveryError):verify_manifest(data,keys,COMPATIBILITY,73)
        with self.assertRaises(RecoveryError):verify_manifest(b'{"payload":{},"payload":{}}',keys,COMPATIBILITY,73)
        with self.assertRaises(RecoveryError):verify_manifest(b' '*65537,keys,COMPATIBILITY,73)

    @unittest.skipUnless(os.name=='posix','POSIX fsync/chmod semantics')
    def test_valid_payload_and_digest_tampering(self):
        data=archive_bytes([('zmala_terminal/common/main.py',b'print("fixture")',tarfile.REGTYPE)])
        payload,_,_=signed_fixture(data)
        with tempfile.TemporaryDirectory() as root:
            package=Path(root)/'payload';package.write_bytes(data)
            verify_package(package,payload)
            extract_package(package,Path(root)/'candidate')
            self.assertEqual((Path(root)/'candidate/zmala_terminal/common/main.py').read_bytes(),b'print("fixture")')
            package.write_bytes(data[:-1]+bytes([data[-1]^1]))
            with self.assertRaises(RecoveryError):verify_package(package,payload)

    @unittest.skipUnless(os.name=='posix','POSIX fsync semantics')
    def test_unsafe_archive_members_are_rejected_before_extraction(self):
        cases=[('../outside',tarfile.REGTYPE),('/outside',tarfile.REGTYPE),
               ('zmala_terminal/common/../escape',tarfile.REGTYPE),('zmala_terminal/data/token',tarfile.REGTYPE),
               ('zmala_terminal/common/.secret',tarfile.REGTYPE),('zmala_terminal/linux/models/weights',tarfile.REGTYPE),
               ('zmala_terminal/common/link',tarfile.SYMTYPE),('zmala_terminal/common/hard',tarfile.LNKTYPE),
               ('zmala_terminal/common/fifo',tarfile.FIFOTYPE),('install.sh',tarfile.REGTYPE)]
        for name,kind in cases:
            with self.subTest(name=name),tempfile.TemporaryDirectory() as root:
                package=Path(root)/'payload';package.write_bytes(archive_bytes([(name,b'',kind)]))
                with self.assertRaises(RecoveryError):extract_package(package,Path(root)/'candidate')
                self.assertEqual(list((Path(root)/'candidate').iterdir()),[])
        with tempfile.TemporaryDirectory() as root:
            package=Path(root)/'payload';entry=('zmala_terminal/common/main.py',b'x',tarfile.REGTYPE)
            package.write_bytes(archive_bytes([entry,entry]))
            with self.assertRaises(RecoveryError):extract_package(package,Path(root)/'candidate')
