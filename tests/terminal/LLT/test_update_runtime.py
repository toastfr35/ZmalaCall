# @test T-LLT-098
# @requirements LLR-TERM-MAINT-030
# @environment portable
# @plan Exercise bounded public downloads with fake transports and authenticated local heartbeat fixtures; reject bad origin, size, digest, nonce, ownership permissions, cgroup and selected-directory mismatches.
# @pass Only verified complete files are cached, partial failures leave no package, and only the current terminal service can acknowledge maintenance. Linux process fixtures skip on Windows.
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from zmala_terminal.linux.update_download import download, fetch, public_asset, ReleaseRedirect
from zmala_terminal.linux.update_transaction import Transactions, RecoveryError


class Response(io.BytesIO):
    status = 200


class DownloadTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'posix', 'Requires POSIX durable cache directory synchronization')
    def test_origin_limits_digest_and_partial_cleanup(self):
        url = 'https://github.com/toastfr35/ZmalaCall/releases/download/v1.0.0/ZmalaTerminal-Update.tar.gz'
        body = b'package'
        manifest = {'package': {'url': url, 'size': len(body), 'sha256': hashlib.sha256(body).hexdigest()}}
        transport = Mock()
        with tempfile.TemporaryDirectory() as root:
            transport.open.return_value = Response(body)
            target = download(manifest, root, transport=transport)
            self.assertEqual(target.read_bytes(), body)
            target.unlink()
            for invalid in (b'wrong', body+b'extra'):
                transport.open.return_value = Response(invalid)
                with self.assertRaises(RecoveryError):
                    download(manifest, root, transport=transport)
                self.assertEqual(list(Path(root).iterdir()), [])
        for invalid in ('http://github.com/a', 'https://evil.test/a', 'https://user@github.com/a', 'https://github.com:123/a'):
            self.assertFalse(public_asset(invalid))
            with self.assertRaises(RecoveryError):
                fetch(invalid, 10, transport)
        transport.open.return_value = Response(b'oversized')
        with self.assertRaises(RecoveryError):
            fetch(url, 2, transport)
        request = Mock(full_url=url)
        with self.assertRaises(RecoveryError):
            ReleaseRedirect().redirect_request(request, None, 302, '', {}, 'https://evil.test/file')


@unittest.skipUnless(os.name == 'posix', 'Requires Linux process and ownership fixtures')
class HeartbeatTests(unittest.TestCase):
    def test_preparation_rejects_links_and_quarantine_retains_recovery_slots(self):
        from zmala_terminal.linux.update_prepare import validate_built_tree
        from zmala_terminal.linux.update_service import UpdateService
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tree = root/'built'
            tree.mkdir()
            (tree/'regular').write_text('safe')
            validate_built_tree(tree)
            (tree/'link').symlink_to(root)
            with self.assertRaises(RecoveryError):
                validate_built_tree(tree)
            (tree/'link').unlink()
            os.link(tree/'regular', tree/'hardlink')
            with self.assertRaises(RecoveryError):
                validate_built_tree(tree)
            tx = Transactions(root/'updater')
            for name in ('old', 'new', 'obsolete'):
                slot = tx.slots/name
                slot.mkdir()
                (slot/'update-release.json').write_text(json.dumps({'owned_by_updater': 1}))
            tx.initialize('old')
            tx.prepare('new')
            key = root/'keys.json'
            key.write_text(json.dumps({'test': 'YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWE='}))
            with patch('zmala_terminal.linux.update_service.trusted_json',
                       side_effect=lambda path, *args: json.loads(Path(path).read_text())):
                service = UpdateService({'keys': str(key), 'data_checkpoints': str(root/'checkpoints')}, tx, Mock())
                service.quarantine('failed-digest')
                self.assertTrue(service.quarantined('failed-digest'))
                self.assertFalse(service.quarantined('new-digest'))
                service.collect()
                self.assertTrue((tx.slots/'old').is_dir())
                self.assertTrue((tx.slots/'new').is_dir())
                self.assertFalse((tx.slots/'obsolete').exists())

    def test_only_fresh_current_service_heartbeat_is_accepted(self):
        import pwd
        from zmala_terminal.linux.update_runtime import Runtime
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tx = Transactions(root/'updater')
            (tx.slots/'working').mkdir()
            tx.initialize('working')
            proc = root/'proc/123'
            proc.mkdir(parents=True)
            (proc/'cwd').symlink_to(tx.slot('working'))
            (proc/'cgroup').write_text('0::/system.slice/zmalacall-terminal.service\n')
            owner = Runtime({'user': pwd.getpwuid(os.getuid()).pw_name, 'root': str(tx.root),
                             'proc_root': str(root/'proc'), 'request': str(root/'request/state.json'),
                             'status': str(root/'status.json')}, tx, clock=lambda: 100)
            value = {'pid': 123, 'nonce': owner.nonce, 'heartbeat': 100, 'generation': 'a'*32}
            def write():
                owner.status.write_text(json.dumps(value))
                owner.status.chmod(0o600)
            write()
            self.assertEqual(owner.read_status(), value)
            for key, invalid in (('nonce', 'wrong'), ('heartbeat', 90), ('pid', True), ('generation', 'short')):
                previous = value[key]
                value[key] = invalid
                write()
                self.assertIsNone(owner.read_status())
                value[key] = previous
            write()
            owner.status.chmod(0o666)
            self.assertIsNone(owner.read_status())
            write()
            (proc/'cgroup').write_text('0::/other.service\n')
            self.assertIsNone(owner.read_status())
