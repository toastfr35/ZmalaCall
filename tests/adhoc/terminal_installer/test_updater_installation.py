"""Updater provisioning checks; installer behavior is outside product requirements."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]


@unittest.skipUnless(os.name == 'posix', 'Installer requires Linux account/filesystem APIs')
class UpdaterInstallationTests(unittest.TestCase):
    def test_bootstrap_uses_independent_code_and_preserves_live_data(self):
        import pwd
        specification = importlib.util.spec_from_file_location('install_updater', ROOT/'build_tools/linux/install-updater.py')
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root/'source'
            (source/'build_tools/linux').mkdir(parents=True)
            (source/'zmala_terminal/linux').mkdir(parents=True)
            for name in module.MODULES:
                (source/'zmala_terminal/linux'/(name+'.py')).write_bytes((ROOT/'zmala_terminal/linux'/(name+'.py')).read_bytes())
            for name in ('update-keys.json', 'zmalacall-update-recover.service', 'zmalacall-updater.service', 'zmalacall-update-screen.service',
                         'zmalacall-display.service', 'zmalacall-pairing.service', 'zmalacall-compositor.service', 'zmalacall-cec.service'):
                (source/'build_tools/linux'/name).write_bytes((ROOT/'build_tools/linux'/name).read_bytes())
            (source/'build_tools/linux/release-info.json').write_text(json.dumps({'version': '1.2.3', 'sequence': 99, 'commit': 'a'*40}))
            installed = root/'opt/zmalacall/releases/working'
            (installed/'zmala_terminal').mkdir(parents=True)
            data = root/'var/lib/zmalacall'
            data.mkdir(parents=True)
            (data/'enrollment').write_text('private enrollment')
            (installed/'zmala_terminal/data').symlink_to(data)
            (root/'opt/zmalacall/current').symlink_to(installed)
            (root/'etc/systemd/system').mkdir(parents=True)
            (root/'etc/os-release').write_text('VERSION_CODENAME=trixie\n')
            commands = []
            def command(*args):
                commands.append(args)
                if args[0] == 'dpkg-query':
                    return '5.3.105+dfsg'
                return 'not-found'
            with patch.object(module.os, 'geteuid', return_value=0), patch('os.chown'):
                module.install(source, pwd.getpwuid(os.getuid()).pw_name, layout=root, run=command)
            self.assertEqual((data/'enrollment').read_text(), 'private enrollment')
            current = (root/'opt/zmalacall/current').resolve()
            self.assertEqual((current/'zmala_terminal/data').resolve(), data)
            self.assertEqual(json.loads((current/'update-release.json').read_text())['sequence'], 99)
            stable = (root/'usr/local/lib/zmalacall-updater/current').resolve()
            self.assertFalse((stable/'zmala_terminal/common').exists())
            self.assertEqual((stable/'zmala_terminal/__init__.py').read_text(), '')
            self.assertIn('RemainAfterExit=yes', (root/'etc/systemd/system/zmalacall-update-recover.service').read_text())
            self.assertTrue(all(command[0] in ('systemctl', 'dpkg-query', 'useradd', 'python3') for command in commands))

    def test_host_helpers_are_copied_outside_application_slots(self):
        specification = importlib.util.spec_from_file_location('install_terminal_host', ROOT/'build_tools/linux/install-terminal-host.py')
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            dropin=root/'etc/systemd/system/zmalacall-terminal.service.d/usb-power.conf'
            dropin.parent.mkdir(parents=True)
            dropin.write_text('[Service]\nEnvironment=ZMALA_USB_POWER=1\nExecStopPost=+/usr/local/libexec/zmala-usb-power on\n')
            with patch('os.geteuid', return_value=0), patch('os.fchown'):
                module.install(ROOT,layout=root)
                module.install(ROOT,layout=root)
            destination=root/'usr/local/lib/zmalacall-terminal-host'
            self.assertIn('zmala-usb-power restore',dropin.read_text())
            self.assertEqual((root/'usr/local/libexec/zmala-usb-power').stat().st_mode & 0o777,0o755)
            for name,relative in module.FILES.items():
                self.assertEqual((destination/name).read_bytes(),(ROOT/relative).read_bytes())
                self.assertEqual((destination/name).stat().st_mode & 0o777,0o644)
            for name in ('display','pairing','compositor','cec'):
                unit=(ROOT/f'build_tools/linux/zmalacall-{name}.service').read_text()
                self.assertNotIn('/opt/zmalacall/current',unit)
                self.assertIn('/usr/local/lib/zmalacall-terminal-host/',unit)
