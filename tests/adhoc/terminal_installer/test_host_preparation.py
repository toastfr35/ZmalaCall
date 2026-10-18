# Installer regression tests; outside the Pi runtime requirements baseline.
"""Safety boundaries of repeatable fresh-Pi deployment."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'build_tools/linux' / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


guard = module('ssh-guard')
boot = module('boot-branding')
pair = module('pair-presenter')
kiosk = module('kiosk-session')
wear = module('check-low-wear')


class PiInstallTests(unittest.TestCase):
    def test_effective_low_wear_checks_reject_disk_backing_and_lost_runtime_settings(self):
        files = {'/proc/swaps':'Filename Type Size Used Priority\n/dev/zram0 partition 10 0 100\n',
                 '/sys/block/zram0/backing_dev':'none\n'}
        def read(path, *args, **kwargs):
            return files[str(path).replace('\\', '/')]
        def command(*args):
            if args[0] == 'systemd-analyze':
                return '[Journal]\nStorage=volatile\nRuntimeMaxUse=64M\nForwardToSyslog=no'
            if args[0] == 'systemctl':
                return 'ZMALA_LOG_STDERR=1 ZMALA_RUNTIME_DIR=/run/zmalacall'
            return 'tmpfs' if 'FSTYPE' in args else 'rw,noatime'
        with patch.object(Path, 'read_text', read), patch.object(Path, 'is_dir', return_value=True), \
                patch.object(wear, 'command', side_effect=command):
            self.assertTrue(all(wear.inspect().values()))
            files['/sys/block/zram0/backing_dev'] = '/dev/mmcblk0p2'
            self.assertFalse(wear.inspect()['ram_only_swap'])
            files['/proc/swaps'] = 'Filename Type Size Used Priority\n'
            self.assertFalse(wear.inspect()['ram_only_swap'])
        with patch.object(wear.subprocess, 'check_output', return_value=' result \n') as run:
            self.assertEqual(wear.command('systemctl', 'show'), 'result')
            run.assert_called_once_with(('systemctl', 'show'), text=True, timeout=15)


    def test_effective_journal_options_respect_later_vendor_overrides(self):
        first = '[Journal]\nStorage=volatile\nForwardToSyslog=no\nRuntimeMaxUse=64M\n'
        vendor = '# /usr/lib/systemd/journald.conf.d/syslog.conf\n[Journal]\nForwardToSyslog=yes\n'
        self.assertEqual(wear.journal_options(first + vendor)['ForwardToSyslog'], 'yes')
        self.assertEqual(wear.journal_options(first + vendor + first)['ForwardToSyslog'], 'no')
        self.assertEqual(wear.journal_options(first + '[Other]\nStorage=persistent')['Storage'], 'volatile')


    def test_branding_preserves_disk_uart_country_and_video_mode(self):
        old = 'console=serial0,115200 console=tty1 root=PARTUUID=abc rootwait cfg80211.ieee80211_regdom=GB video=HDMI-A-1:1280x720@60D\n'
        new = boot.quiet_command_line(old)
        self.assertNotIn('console=tty1', new)
        for value in old.split():
            if value != 'console=tty1':
                self.assertIn(value, new.split())
        self.assertEqual(boot.quiet_command_line(new), new)
        self.assertEqual(new.count('\n'), 1)
