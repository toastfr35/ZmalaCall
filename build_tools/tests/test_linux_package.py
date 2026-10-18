"""The distributable must be boot-installable and contain no runtime secrets."""
import importlib.util
import hashlib
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import subprocess

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('linux_package', ROOT / 'build_tools/linux/package-terminal.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class LinuxPackageTests(unittest.TestCase):
    def test_windows_text_line_endings_are_normalized_without_changing_assets(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name, content in {
                'build_tools/linux/install-kiosk.sh': b'#!/bin/sh\r\nset -eu\r\n',
                'build_tools/linux/dependencies.txt': b'build-essential\r\npython3-pil.imagetk\r\n',
                'build_tools/linux/terminal.service': b'[Service]\r\nExecStart=/usr/bin/true\r\n',
                'build_tools/linux/test.conf': b'[Journal]\r\nStorage=volatile\r\n',
                'zmala_terminal/common/image.bin': b'asset\r\nbytes',
                'docs/linux-terminal.md': b'Linux installation',
                'docs/pi-hardware-video.md': b'Hardware experiment',
                'docs/automatic-framing.md': b'Optional detector',
                'zmala_terminal/linux/media/models/person.tflite': b'downloaded model',
                'zmala_terminal/linux/media/framing-runtime/lib/runtime.py': b'installed runtime',
            }.items():
                file = root / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(content)
            with patch.object(module, 'ROOT', root):
                release = module.package(root / 'terminal.tar.gz')
            with tarfile.open(release) as archive:
                self.assertEqual(archive.extractfile('build_tools/linux/install-kiosk.sh').read(),
                                 b'#!/bin/sh\nset -eu\n')
                self.assertEqual(archive.extractfile('zmala_terminal/common/image.bin').read(),
                                 b'asset\r\nbytes')
                self.assertEqual(archive.extractfile('build_tools/linux/dependencies.txt').read(),
                                 b'build-essential\npython3-pil.imagetk\n')
                self.assertEqual(archive.extractfile('build_tools/linux/terminal.service').read(),
                                 b'[Service]\nExecStart=/usr/bin/true\n')
                self.assertEqual(archive.extractfile('build_tools/linux/test.conf').read(),
                                 b'[Journal]\nStorage=volatile\n')
                for line in archive.extractfile('SHA256SUMS').read().decode().splitlines():
                    digest, name = line.split('  ', 1)
                    self.assertEqual(hashlib.sha256(archive.extractfile(name).read()).hexdigest(), digest)
                self.assertFalse(any('framing-runtime' in name or name.endswith('.tflite')
                                     for name in archive.getnames()))

    def test_c20_has_one_installer_and_source_not_binaries_or_retired_bridges(self):
        with tempfile.TemporaryDirectory() as folder:
            release = module.package(Path(folder) / 'terminal.tar.gz')
            with tarfile.open(release) as archive:
                wrapper = archive.extractfile('install.sh').read().decode()
                self.assertIn('install-kiosk.sh', wrapper)
                names = archive.getnames()
                self.assertIn('zmala_terminal/linux/media/video/codec.c', names)
                self.assertIn('zmala_terminal/linux/media/video/filters.c', names)
                self.assertIn('build_tools/linux/build-media.sh', names)
                self.assertFalse(any(name.startswith('zmala_terminal/windows/') for name in names))
                self.assertFalse(any(name.startswith('zmala_terminal/windows/') for name in names))
                self.assertFalse(any('experimental' in Path(name).parts for name in names))
                self.assertFalse(any(Path(name).suffix in ('.so', '.o') for name in names))
                self.assertFalse(any('data' in Path(name).parts for name in names))

    def test_cold_boot_display_timeout_is_retried(self):
        source = importlib.util.spec_from_file_location('kiosk', ROOT / 'build_tools/linux/kiosk-session.py')
        kiosk = importlib.util.module_from_spec(source)
        source.loader.exec_module(kiosk)
        ready = subprocess.CompletedProcess(['xdpyinfo'], 0)
        with patch.object(kiosk.subprocess, 'run', side_effect=[
                subprocess.TimeoutExpired('xdpyinfo', 5), ready]) as run, \
                patch.object(kiosk.time, 'sleep'):
            kiosk.wait_for_display()
        self.assertEqual(run.call_count, 2)

    def test_release_contents_and_permissions(self):
        with tempfile.TemporaryDirectory() as folder:
            release = module.package(Path(folder) / 'terminal.tar.gz')
            with tarfile.open(release) as archive:
                names = set(archive.getnames())
                for name in ('install.sh', 'build_tools/linux/install-kiosk.sh',
                             'build_tools/linux/zmalacall-display.service',
                             'build_tools/linux/zmalacall-terminal.service',
                             'build_tools/linux/zmalacall-cec.service',
                             'build_tools/linux/zmalacall-compositor.service',
                             'build_tools/linux/picom.conf',
                             'build_tools/linux/21-zmalacall-pi4.conf',
                             'zmala_terminal/linux/cec_observer.py',
                             'zmala_terminal/common/main.py', 'docs/linux-terminal.md'):
                    self.assertIn(name, names)
                for name in names:
                    self.assertNotIn('data', Path(name).parts)
                    self.assertNotIn('__pycache__', Path(name).parts)
                    self.assertNotEqual(Path(name).suffix.lower(), '.dll')
                self.assertEqual(archive.getmember('install.sh').mode, 0o755)
                self.assertEqual(archive.getmember('build_tools/linux/install-kiosk.sh').mode, 0o755)
                self.assertEqual(archive.getmember('zmala_terminal/common/main.py').mode, 0o644)
                manifest = archive.extractfile('SHA256SUMS').read().decode().splitlines()
                checked = set()
                for line in manifest:
                    digest, name = line.split('  ', 1)
                    self.assertEqual(hashlib.sha256(archive.extractfile(name).read()).hexdigest(), digest)
                    checked.add(name)
                self.assertEqual(checked, names - {'SHA256SUMS'})
            self.assertEqual(release.with_name(release.name + '.sha256').read_text().split()[0],
                             hashlib.sha256(release.read_bytes()).hexdigest())


if __name__ == '__main__':
    unittest.main()
