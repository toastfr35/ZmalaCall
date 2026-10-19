"""Release automation checks, outside the product runtime requirements baseline."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from build_tools.release import github_release as release
from build_tools.release.assemble import ASSETS


def gradle(version, code):
    return f"versionCode {code}; versionName '{version}'"


class ReleaseAutomationTests(unittest.TestCase):
    def test_every_merge_requires_both_versions_to_increase(self):
        previous = gradle('0.3.8', 17)
        self.assertEqual(release.validate_version_increase(gradle('0.3.9', 18), previous), 'v0.3.9')
        self.assertEqual(release.validate_version_increase(gradle('0.4.0', 18), previous), 'v0.4.0')
        for version, code in [('0.3.8', 18), ('0.3.7', 19), ('0.3.9', 17), ('0.4.0', 16)]:
            with self.subTest(version=version, code=code), self.assertRaises(ValueError):
                release.validate_version_increase(gradle(version, code), previous)

    def test_invalid_or_ambiguous_versions_are_rejected(self):
        for text in [gradle('0.3.9-rc1', 18), gradle('0.03.9', 18), gradle('0.3.9', 0),
                     gradle('0.3.9', 2100000001), gradle('0.3.9', 18) + gradle('0.3.10', 19)]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                release.android_version(text)

    def test_automatic_tag_and_manual_consistency_check(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            file = root / 'zmala_phone/app/build.gradle'
            file.parent.mkdir(parents=True)
            file.write_text(gradle('0.3.9', 18))
            with patch.object(release, 'ROOT', root), patch.dict(os.environ, {'RELEASE_TAG': ''}):
                self.assertEqual(release.version_tag(), 'v0.3.9')
                with patch.dict(os.environ, {'RELEASE_TAG': 'v0.3.8'}), self.assertRaises(ValueError):
                    release.version_tag()

    def test_pr_checks_remote_tag_and_fails_closed_on_network_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            file = root / 'zmala_phone/app/build.gradle'
            file.parent.mkdir(parents=True)
            file.write_text(gradle('0.3.9', 18))
            with patch.object(release, 'ROOT', root), patch.dict(os.environ, {'BASE_SHA': 'a' * 40}), \
                    patch.object(release.subprocess, 'check_output', return_value=gradle('0.3.8', 17)):
                for code in (2, 0, 128):
                    with patch.object(release.subprocess, 'run',
                                      return_value=subprocess.CompletedProcess([], code)) as run:
                        if code == 2:
                            release.check_pr_version()
                        else:
                            with self.assertRaises(ValueError):
                                release.check_pr_version()
                        self.assertEqual(run.call_args.args[0][-1], 'refs/tags/v0.3.9')
        with patch.dict(os.environ, {'BASE_SHA': 'main:unexpected'}), self.assertRaises(ValueError):
            release.check_pr_version()

    def test_publish_validates_assets_before_semantic_latest_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            for name in ASSETS:
                (folder / name).write_bytes(b'fixture')
            draft = {'assets': [{'name': name, 'state': 'uploaded'} for name in ASSETS],
                     'databaseId': 123, 'isDraft': True, 'tagName': 'v0.3.9', 'targetCommitish': 'a' * 40}
            assets = json.dumps(draft)
            with patch.object(release, 'version_tag', return_value='v0.3.9'), \
                    patch.object(release.subprocess, 'check_output', side_effect=['a' * 40, assets]) as output, \
                    patch.object(release.subprocess, 'run') as run:
                release.publish(folder, Path('notes.md'))
                self.assertEqual(output.call_args.args[0], ['gh', 'release', 'view', 'v0.3.9', '--json',
                                 'assets,databaseId,isDraft,tagName,targetCommitish'])
                self.assertEqual(run.call_args.args[0], [
                    'gh', 'api', '--method', 'PATCH', 'repos/{owner}/{repo}/releases/123',
                    '-F', 'draft=false', '-f', 'make_latest=legacy', '--silent'])
            with patch.object(release, 'version_tag', return_value='v0.3.9'), \
                    patch.object(release.subprocess, 'check_output',
                                 side_effect=['a' * 40, json.dumps({'assets': []})]), \
                    patch.object(release.subprocess, 'run') as run:
                with self.assertRaisesRegex(ValueError, 'draft retained'):
                    release.publish(folder, Path('notes.md'))
                self.assertFalse(any('--method' in call.args[0] for call in run.call_args_list))
            for field, value in [('databaseId', 'invalid'), ('isDraft', False),
                                 ('tagName', 'v0.3.8'), ('targetCommitish', 'b' * 40)]:
                with self.subTest(field=field), \
                        patch.object(release, 'version_tag', return_value='v0.3.9'), \
                        patch.object(release.subprocess, 'check_output',
                                     side_effect=['a' * 40, json.dumps({**draft, field: value})]), \
                        patch.object(release.subprocess, 'run') as run:
                    with self.assertRaisesRegex(ValueError, 'Invalid draft release identity'):
                        release.publish(folder, Path('notes.md'))
                    self.assertFalse(any('--method' in call.args[0] for call in run.call_args_list))


if __name__ == '__main__':
    unittest.main()
