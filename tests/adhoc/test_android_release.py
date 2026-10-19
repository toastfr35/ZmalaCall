"""Release packaging guards; deliberately outside the runtime requirement baseline."""
import unittest
from build_tools.android.release import verify_manifest


class ReleaseManifestTests(unittest.TestCase):
    def manifest(self, attributes='android:allowBackup="false"', package='org.zmala.phone'):
        return (f'<manifest xmlns:android="http://schemas.android.com/apk/res/android" '
                f'package="{package}" android:versionName="0.3.6" android:versionCode="15">'
                f'<application {attributes}/></manifest>')

    def test_release_metadata(self):
        self.assertEqual(verify_manifest(self.manifest()), ('0.3.6', '15'))

    def test_rejects_development_packages(self):
        for flag in ('debuggable', 'testOnly'):
            with self.subTest(flag=flag), self.assertRaises(ValueError):
                verify_manifest(self.manifest(f'android:allowBackup="false" android:{flag}="true"'))

    def test_rejects_wrong_app_and_backup(self):
        for xml in (self.manifest(package='example.fixture'), self.manifest(''),
                    self.manifest('android:allowBackup="true"')):
            with self.subTest(xml=xml), self.assertRaises(ValueError):
                verify_manifest(xml)


if __name__ == '__main__':
    unittest.main()
