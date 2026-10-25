# Installer regression tests; outside the Pi runtime requirements baseline.
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, Mock, patch

from tests.support.linux_units import ROOT, load, shell
from tests.adhoc.terminal_installer.test_windows_installer import target
from build_tools.windows_installer import backend
from zmala_terminal.linux.usb_power import UsbPower

launcher = load('launcher')


class ApplianceInstallTests(unittest.TestCase):
    def test_installer_default_enables_argon_then_verifies_reboot(self):
        d = backend.Deployment('fixture'); d.info = target(); d.client = MagicMock()
        events = []
        with patch.object(d, 'connect'), patch.object(d, 'probe', return_value=target()), \
                patch.object(backend, 'verify_payload', return_value='fixture-digest'), \
                patch.object(d, 'command', side_effect=lambda cmd, *args, **kwargs: events.append(cmd) or ''), \
                patch.object(d, 'monitor', side_effect=lambda *args: events.append('monitor')), \
                patch.object(d, 'close'), patch.object(d, 'verify_reboot', side_effect=lambda boot: events.append('verified '+boot)):
            d.install('fixture.tar.gz')
        install = next(command for command in events if command.startswith('systemd-run'))
        self.assertIn('--argon-one', install)
        self.assertNotIn('--bootstrap', install)
        self.assertLess(events.index(install), events.index('monitor'))
        self.assertLess(events.index('monitor'), events.index('systemctl reboot --no-block'))
        self.assertEqual(events[-1], 'verified initial-boot')
        with patch.dict(os.environ, {}, clear=True), patch('zmala_terminal.linux.usb_power.sys.platform', 'linux'), \
                patch('zmala_terminal.linux.usb_power.threading.Thread') as thread:
            power = UsbPower(Mock())
            self.assertFalse(power.enabled); thread.assert_not_called()


    @unittest.skipIf(sys.platform == 'win32', 'POSIX release filesystem semantics run on Linux CI')
    def test_release_preparation_preserves_existing_enrollment_and_private_data(self):
        source = (ROOT/'build_tools/linux/install-kiosk.sh').read_text()
        block = source.split('# Prepare release and persistent appliance state.\n',1)[1].split("task_step 'Activating release",1)[0]
        # Fixed absolute appliance paths are redirected only into this test's
        # temporary root. Build and ownership operations are command doubles.
        for path in ('/opt/zmalacall', '/var/lib/zmalacall', '/etc/zmalacall'):
            block = block.replace(path, '"$unit_root"'+path)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ('source/zmala_terminal/common','source/build_tools/linux','var/lib/zmalacall','migrate'):
                (root/name).mkdir(parents=True,exist_ok=True)
            for name in ('tests/terminal/LLT/turn_parser.cpp', 'tests/terminal/LLT/turn_socket_io.cpp',
                         'tests/support/native/turn-write-cases.h'):
                fixture = root/'source'/name
                fixture.parent.mkdir(parents=True, exist_ok=True)
                fixture.write_bytes((ROOT/name).read_bytes())
            (root/'var/lib/zmalacall/terminal.json').write_text('existing-private-state')
            (root/'migrate/terminal.json').write_text('must-not-overwrite')
            (root/'migrate').chmod(0o755)  # Source permissions must not weaken private state.
            script = '''set -eu
unit_root=$(pwd)
task_root="$unit_root/source"; data_from="$unit_root/migrate"; bootstrap=; task_user=fixture; framing=yes
task_step() { :; }; chown() { printf 'OWNER %s\\n' "$*"; }; id() { echo fixture; }; sh() { printf 'BUILD %s\\n' "$*"; }; python3() { printf 'BUILD %s\\n' "$*"; }
'''+block+'\nprintf "RELEASE %s\\n" "$release"\n'
            result = shell(script, folder)
            self.assertEqual(result.returncode, 0, result.stderr)
            release = Path(next(line[8:] for line in result.stdout.splitlines() if line.startswith('RELEASE ')))
            self.assertTrue(release.resolve().is_relative_to(root.resolve()))
            self.assertEqual((release/'zmala_terminal/data').resolve(), root/'var/lib/zmalacall')
            self.assertEqual((root/'var/lib/zmalacall/terminal.json').read_text(), 'existing-private-state')
            self.assertEqual((root/'var/lib/zmalacall').stat().st_mode & 0o777, 0o700)
            self.assertIn('build-media.sh', result.stdout)
            self.assertIn('build-turn.py', result.stdout)
            self.assertIn('setup-auto-framing.sh', result.stdout)


    @unittest.skipIf(sys.platform == 'win32', 'POSIX display installer unit runs on Linux CI')
    def test_pi4_acceleration_workaround_requires_matching_board_and_driver(self):
        source = (ROOT/'build_tools/linux/install-kiosk.sh').read_text(encoding='utf-8')
        block = 'if [ -r /proc/device-tree/model ]' + source.split('if [ -r /proc/device-tree/model ]',1)[1].split('\nfi',1)[0] + '\nfi\n'
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for board in ('Raspberry Pi 4 Model B', 'Raspberry Pi 3 Model B', None):
                for driver in ('contains msdri3 path', 'generic modesetting', None):
                    for name, value in (('model',board),('driver',driver)):
                        path = root/name
                        if value is None:
                            path.unlink(missing_ok=True)
                        else:
                            path.write_text(value, encoding='utf-8')
                    script = block.replace('/proc/device-tree/model','./model').replace('/usr/lib/xorg/modules/drivers/modesetting_drv.so','./driver')
                    result = shell('task_root=fixture; mkdir() { :; }; install() { echo APPLY; };\n'+script, folder)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual('APPLY' in result.stdout, board == 'Raspberry Pi 4 Model B' and driver == 'contains msdri3 path')
