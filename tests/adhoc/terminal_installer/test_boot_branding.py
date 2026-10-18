# Installer regression tests; outside the Pi runtime requirements baseline.
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tests.terminal.LLT.test_pi_install import module


class LinuxLifecycleTests(unittest.TestCase):
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
