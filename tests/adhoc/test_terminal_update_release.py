"""Release packaging/signing regressions; use disposable keys, never release secrets."""
import base64
import hashlib
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from build_tools.release import terminal_update as release


class TerminalUpdateReleaseTests(unittest.TestCase):
    def test_payload_signature_identity_bounds_and_private_exclusions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            files = ['zmala_terminal/common/main.py', 'zmala_terminal/linux/entry.py']
            for name in [*files, *('build_tools/linux/'+name for name in release.EXTRA), *release.NATIVE_TESTS]:
                path = root/name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'// fixture\r\n')
            private = root/'zmala_terminal/data/private.json'
            private.parent.mkdir()
            private.write_text('must not ship')
            upstream = {name: b'public source fixture' for name in release.UPSTREAM}
            hashes = {name: hashlib.sha256(data).hexdigest() for name, data in upstream.items()}
            output = root/'dist'
            archive = output/'ZmalaTerminal-Update.tar.gz'
            with patch.object(release, 'UPSTREAM', hashes):
                release.package(root, archive, upstream, tracked=[*files, 'zmala_terminal/data/private.json'])
                with tarfile.open(archive) as package:
                    names = package.getnames()
                    self.assertNotIn('zmala_terminal/data/private.json', names)
                    self.assertNotIn('build_tools/linux/install-updater.py', names)
                    self.assertTrue(all(release.allowed_path(name) for name in names))
                    self.assertEqual(package.extractfile(files[0]).read(), b'// fixture\n')
                    self.assertIn('zmala_terminal/linux/native/upstream/turn_tcp.cpp', names)
                with self.assertRaises(ValueError):
                    release.package(root, output/'invalid.tar.gz', {name: b'tampered' for name in upstream}, tracked=files)
            key = Ed25519PrivateKey.generate()
            public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
            pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
            trusted = {release.KEY_ID: public}
            (root/'build_tools/linux/update-keys.json').write_text(json.dumps({release.KEY_ID: base64.b64encode(public).decode()}))
            gradle = root/'zmala_phone/app/build.gradle'
            gradle.parent.mkdir(parents=True)
            gradle.write_text("versionCode 99; versionName '1.2.3'")
            payload = {'schema': 1, 'version': '1.2.3', 'sequence': 99, 'commit': 'a'*40,
                       'compatibility': release.COMPATIBILITY,
                       'package': {'size': archive.stat().st_size,
                                   'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
                                   'url': 'https://github.com/toastfr35/ZmalaCall/releases/download/v1.2.3/ZmalaTerminal-Update.tar.gz'}}
            (output/'ZmalaTerminal-Update.json').write_bytes(release.sign(payload, pem, trusted))
            with patch.object(release.subprocess, 'check_output', return_value='a'*40):
                self.assertEqual(release.verify(root, output), payload)
            with patch.object(release.subprocess, 'check_output', return_value='b'*40), self.assertRaises(ValueError):
                release.verify(root, output)
            with self.assertRaises(ValueError):
                release.sign(payload, pem, {})
            archive.write_bytes(b'corrupt')
            with patch.object(release.subprocess, 'check_output', return_value='a'*40), self.assertRaises(RuntimeError):
                release.verify(root, output)

    def test_real_signing_secret_is_referenced_only_by_release_workflow(self):
        root = Path(__file__).resolve().parents[2]
        workflow = (root/'.github/workflows/release.yml').read_text()
        verify = (root/'.github/workflows/verify.yml').read_text()
        self.assertIn('secrets.ZMALA_TERMINAL_UPDATE_KEY', workflow)
        self.assertNotIn('ZMALA_TERMINAL_UPDATE_KEY', verify)
        self.assertIn('needs: [windows, android, terminal-update]', workflow)
        self.assertIn('terminal_update.py verify', workflow)
