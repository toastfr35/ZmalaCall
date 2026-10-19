"""Distribution layout checks, outside the runtime requirements baseline."""
from pathlib import Path
import base64
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from build_tools.release.assemble import ASSETS, collect
from build_tools.release import github_release


class ReleaseAssetTests(unittest.TestCase):
    def fixtures(self, root):
        dist = root / 'dist'
        (dist / 'guides').mkdir(parents=True)
        apk = root / 'verified.apk'
        for name in ASSETS:
            path = apk if name.endswith('.apk') else (
                dist / 'guides' / name if name.endswith('.pdf') else dist / name)
            header = b'%PDF' if name.endswith('.pdf') else b'MZ' if name.endswith('.exe') else b'PK'
            path.write_bytes(header + b'fixture')
        return dist, apk

    def test_only_nine_named_assets_even_with_private_and_source_files_nearby(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            dist, apk = self.fixtures(root)
            for name in ('project-source.zip', 'signing.p12', 'account-qr.pdf', 'SHA256SUMS.txt'):
                (dist / name).write_text('must not ship')
            result = root / 'release'
            collect(dist, apk, result)
            self.assertEqual({p.name for p in result.iterdir()}, set(ASSETS))
            self.assertEqual(len(ASSETS), 9)

    def test_missing_guide_fails_before_creating_partial_release(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            dist, apk = self.fixtures(root)
            (dist / 'guides' / 'ZmalaPhone-Guide.pdf').unlink()
            with self.assertRaisesRegex(ValueError, 'Missing release input'):
                collect(dist, apk, root / 'release')
            self.assertFalse((root / 'release').exists())

    def test_existing_destination_is_never_overwritten_or_merged(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            dist, apk = self.fixtures(root)
            output = root / 'release'
            output.mkdir()
            sentinel = output / 'previous.apk'
            sentinel.write_text('previous')
            with self.assertRaises(ValueError):
                collect(dist, apk, output)
            self.assertEqual(sentinel.read_text(), 'previous')

    def test_ci_signing_uses_temporary_paths_and_only_expected_client(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            paths = (root / 'key.p12', root / 'signing.json', root / 'client.json')
            signing = {'storePassword': 'fixture-store', 'keyAlias': 'fixture',
                       'keyPassword': 'fixture-key', 'certificateSha256': 'f' * 64,
                       'storeFile': '/must/not/use/local/path'}
            client = {'client': [{'client_info': {'android_client_info': {'package_name': 'org.zmala.phone'}}}]}
            env = {'ZMALA_ANDROID_KEYSTORE_BASE64': base64.b64encode(b'fixture-key').decode(),
                   'ZMALA_ANDROID_SIGNING_JSON': json.dumps(signing),
                   'ZMALA_FIREBASE_CLIENT_JSON': json.dumps(client)}
            with patch.dict(os.environ, env), patch.object(github_release, 'private_paths', return_value=paths):
                github_release.prepare_signing()
            self.assertEqual(paths[0].read_bytes(), b'fixture-key')
            self.assertEqual(json.loads(paths[1].read_text())['storeFile'], str(paths[0]))
            if os.name != 'nt':
                self.assertEqual(paths[1].stat().st_mode & 0o777, 0o600)

    def test_ci_rejects_missing_secrets_without_creating_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            paths = tuple(root / name for name in ('key', 'signing', 'client'))
            with patch.dict(os.environ, {}, clear=True), \
                    patch.object(github_release, 'private_paths', return_value=paths), \
                    self.assertRaisesRegex(ValueError, 'three Zmala Android Actions secrets'):
                github_release.prepare_signing()
            self.assertFalse(any(root.iterdir()))

    def test_publication_rejects_extra_assets(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ASSETS:
                (root / name).write_bytes(b'fixture')
            (root / 'source.zip').write_bytes(b'must not publish')
            with self.assertRaisesRegex(ValueError, 'exactly the nine'):
                github_release.checked_assets(root)


if __name__ == '__main__':
    unittest.main()
