# @test T-LLT-052
# @requirements TLLR005, TLLR116, TLLR117, TLLR123
# @environment portable
# @plan Inject launcher locks and PID observations to reject concurrent profiles and reused processes; inspect service cleanup policy. Run the release-state shell unit in a temporary filesystem with ownership/build commands replaced, verifying upgrade preservation and release/data separation. Exercise installer orchestration with fake SSH and confirm default Argon and reboot verification.
# @pass A duplicate profile or reused PID must never launch/kill a process; installation preserves private enrollment and verifies startup before reporting completion.

import configparser
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, Mock, patch

from tests.support.linux_units import ROOT, load, shell
from tests.terminal.LLT.test_windows_installer import target
from build_tools.windows_installer import backend
from zmala_terminal.linux.usb_power import UsbPower

launcher = load('launcher')


class ApplianceInstallTests(unittest.TestCase):
    def test_profile_lock_refuses_second_instance_before_running_app(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(launcher, 'ROOT', Path(folder)), \
                patch.dict(os.environ, {'ZMALA_RUNTIME_DIR':folder}), patch.object(sys, 'argv', ['launcher','run','--profile','fixture']), \
                patch.object(launcher.fcntl, 'flock', side_effect=BlockingIOError), patch.object(launcher.runpy, 'run_path') as run, \
                patch.object(launcher.os, 'umask'):
            with self.assertRaises(SystemExit):
                launcher.main()
            run.assert_not_called()

    def test_stop_does_not_signal_reused_pid(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(launcher, 'ROOT', Path(folder)), \
                patch.dict(os.environ, {'ZMALA_RUNTIME_DIR':folder}), patch.object(sys, 'argv', ['launcher','stop','--profile','fixture']), \
                patch.object(launcher, 'start_time', return_value='new-start'), \
                patch.object(launcher.os, 'killpg', create=True) as kill, patch.object(launcher.os, 'umask'):
            record = Path(folder)/'fixture.pid.json'
            record.write_text(json.dumps({'pid':123,'started':'old-start'}))
            launcher.main()
            kill.assert_not_called(); self.assertFalse(record.exists())
        unit = configparser.ConfigParser(strict=False, interpolation=None)
        unit.read(ROOT/'build_tools/linux/zmalacall-terminal.service')
        self.assertEqual(unit['Service']['KillMode'], 'control-group')

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
        block = source.split('# @llr TLLR117\n',1)[1].split("task_step 'Activating release",1)[0]
        # Fixed absolute appliance paths are redirected only into this test's
        # temporary root. Build and ownership operations are command doubles.
        for path in ('/opt/zmalacall', '/var/lib/zmalacall', '/etc/zmalacall'):
            block = block.replace(path, '"$unit_root"'+path)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ('source/zmala_terminal/common','source/build_tools/linux','var/lib/zmalacall','migrate'):
                (root/name).mkdir(parents=True,exist_ok=True)
            (root/'var/lib/zmalacall/terminal.json').write_text('existing-private-state')
            (root/'migrate/terminal.json').write_text('must-not-overwrite')
            script = '''set -eu
unit_root=$(pwd)
task_root="$unit_root/source"; data_from="$unit_root/migrate"; bootstrap=; task_user=fixture; framing=yes
task_step() { :; }; chown() { printf 'OWNER %s\\n' "$*"; }; id() { echo fixture; }; sh() { printf 'BUILD %s\\n' "$*"; }
'''+block+'\nprintf "RELEASE %s\\n" "$release"\n'
            result = shell(script, folder)
            self.assertEqual(result.returncode, 0, result.stderr)
            release = Path(next(line[8:] for line in result.stdout.splitlines() if line.startswith('RELEASE ')))
            self.assertTrue(release.resolve().is_relative_to(root.resolve()))
            self.assertEqual((release/'zmala_terminal/data').resolve(), root/'var/lib/zmalacall')
            self.assertEqual((root/'var/lib/zmalacall/terminal.json').read_text(), 'existing-private-state')
            self.assertEqual((root/'var/lib/zmalacall').stat().st_mode & 0o777, 0o700)
            self.assertIn('build-media.sh', result.stdout)
            self.assertIn('setup-auto-framing.sh', result.stdout)
