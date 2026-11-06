"""Development image assembly regressions; no hardware boot qualification."""
import gzip
import json
import os
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zlib

from build_tools.images import build_space, image_assembly, image_payload, image_state, image_worker, package_lock
from tests.adhoc.test_image_root_build import SELECTED
from tests.adhoc.test_image_state import fixture
from zmala_system import boot_media, boot_state


class ImageAssemblyTests(unittest.TestCase):
    def test_wsl_capacity_is_limited_by_physical_backing_volume(self):
        with patch.object(build_space.shutil, 'disk_usage', return_value=SimpleNamespace(free=10**12)), \
                patch.object(build_space.Path, 'is_file', return_value=True), \
                patch.object(build_space.Path, 'read_text', return_value='microsoft-standard-WSL2'), \
                patch.dict(os.environ, {'WSL_DISTRO_NAME': "build'quoted"}), \
                patch.object(build_space.shutil, 'which', return_value='/path/powershell.exe'), \
                patch.object(build_space.subprocess, 'check_output', return_value='123456\n') as query:
            self.assertEqual(build_space.available('/tmp'), 123456)
            self.assertIn("'build''quoted'", query.call_args.args[0][-1])
            query.return_value = 'unavailable'
            with self.assertRaises(ValueError):
                build_space.available('/tmp')

    def test_kernel_memory_bound_architecture_and_compression(self):
        body = bytes(56)+b'ARMd'+bytes(68)
        for encoded in (body, gzip.compress(body)):
            self.assertEqual(image_payload.kernel_image(encoded), body)
        for encoded in (b'not a kernel', bytes(128), gzip.compress(bytes(33*1024**2))):
            with self.assertRaises(ValueError):
                image_payload.kernel_image(encoded)

    def test_factory_environment_crc_redundancy_and_complete_state(self):
        for role in ('server', 'terminal', 'combined'):
            for flag in (0, 1):
                body = image_payload.environment('bootcmd=local only\n', role, flag)
                self.assertEqual(len(body), boot_media.ENV_BYTES)
                self.assertEqual(body[4], flag)
                self.assertEqual(struct.unpack('<I', body[:4])[0], zlib.crc32(body[5:]))
                fields = dict(row.decode().split('=', 1) for row in body[5:].split(b'\0\0')[0].split(b'\0'))
                self.assertEqual({k: v for k, v in fields.items() if k.startswith('zm_')},
                                 boot_state.State(role, 'A').fields())
                self.assertEqual(fields['bootcmd'], 'local only')
        for initial in ('zm_schema=1\n', 'key=one\nkey=two\n', 'key=bad\0data\n', 'key='+'x'*65536):
            with self.assertRaises(ValueError):
                image_payload.environment(initial, 'terminal', 1)

    def test_component_digest_and_link_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); marker = root/'READY.json'; marker.write_text('{"schema":1}')
            checksum = package_lock.digest(marker)
            self.assertEqual(image_assembly.component(root, checksum), {'schema': 1})
            with self.assertRaises(ValueError):
                image_assembly.component(root, '0'*64)
            if os.name != 'nt':
                marker.rename(root/'actual.json'); marker.symlink_to('actual.json')
                with self.assertRaises(ValueError):
                    image_assembly.component(root, checksum)

    def test_host_root_and_windows_refused_before_inputs_or_output(self):
        for system, uid in (('Windows', 1000), ('Linux', 0)):
            with patch.object(image_assembly.platform, 'system', return_value=system), \
                    patch.object(image_assembly.os, 'geteuid', return_value=uid, create=True), \
                    patch.object(image_assembly.local_repo, 'inputs') as inputs, self.assertRaises(ValueError):
                image_assembly.build('server', 'src', 'hash', 'init', 'hash', 'loader', 'hash', 'base', 'role', 'out')
            inputs.assert_not_called()

    def test_application_marker_survives_preparation_and_incomplete_records_fail(self):
        good = {'schema': 1, 'role': 'server', 'application_installed': True,
                'target_application_imports_checked': True, 'target_unit_graph_checked': True,
                'joint_health_implemented': False}
        for change in ({}, {'role': 'combined'}, {'target_application_imports_checked': False},
                       {'joint_health_implemented': True}, {'application_installed': False}):
            with tempfile.TemporaryDirectory() as folder:
                root = Path(folder); source = root/'source.tar'
                fixture(source, {'usr/lib/zmala-application-build.json': ('file', json.dumps({**good, **change}).encode())})
                if not change:
                    self.assertTrue(image_state.prepare(source, package_lock.digest(source), SELECTED,
                                                        'server', root/'out')['application_installed'])
                else:
                    with self.assertRaises(ValueError):
                        image_state.prepare(source, package_lock.digest(source), SELECTED, 'server', root/'out')
                    self.assertFalse((root/'out/READY.json').exists())

    @unittest.skipUnless(hasattr(os, 'SEEK_DATA'), 'Linux sparse regular-file extent support')
    def test_sparse_copy_preserves_bytes_and_refuses_partition_overflow(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); source = root/'fs'; target = root/'image'
            length = 4*1024**2; offset = boot_media.FIRST_PARTITION_BYTES
            with source.open('xb') as stream:
                stream.truncate(length); stream.seek(12345); stream.write(b'filesystem fixture')
            with target.open('x+b') as destination:
                destination.truncate(offset+length)
                image_worker.sparse_copy(source, destination, offset, length)
                destination.seek(offset)
                self.assertEqual(destination.read(), source.read_bytes())
                with self.assertRaises(ValueError):
                    image_worker.sparse_copy(source, destination, offset+512, length)
                with self.assertRaises(ValueError):
                    image_worker.sparse_copy(source, destination, 0, length)


if __name__ == '__main__':
    unittest.main()
