# Installer regression tests; outside the Pi runtime requirements baseline.
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tests.terminal.LLT.test_pi_install import module


class LinuxLifecycleTests(unittest.TestCase):
    def test_version_service_is_installed_only_with_the_splash(self):
        root = Path(__file__).resolve().parents[3]
        installer = (root/'build_tools/linux/install-kiosk.sh').read_text()
        splash = installer.split('if [ "$splash" = yes ]; then', 1)[1].split('\nfi', 1)[0]
        self.assertIn('install -m 644 "$task_root/build_tools/linux/zmalacall-boot-version.service"', splash)
        self.assertIn('systemctl enable zmalacall-boot-version.service', splash)
        host = module('install-terminal-host')
        self.assertEqual(host.FILES['boot-version.py'], 'build_tools/linux/boot-version.py')

    def test_boot_branding_keeps_first_backups_and_is_idempotent(self):
        boot=module('boot-branding')
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory); original='console=tty1 root=PARTUUID=keep rootwait\n'; settings='[pi4]\ndtoverlay=vc4-kms-v3d\n'
            (folder/'cmdline.txt').write_text(original); (folder/'config.txt').write_text(settings)
            with patch.object(boot,'Path',return_value=folder): boot.main(); boot.main()
            self.assertEqual((folder/'cmdline.txt.before-zmala').read_text(),original)
            self.assertEqual((folder/'config.txt.before-zmala').read_text(),settings)
            self.assertIn('root=PARTUUID=keep',(folder/'cmdline.txt').read_text())
            self.assertEqual((folder/'config.txt').read_text().count('# ZmalaCall boot logo'),1)
