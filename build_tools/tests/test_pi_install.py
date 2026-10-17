"""Safety boundaries of repeatable fresh-Pi deployment."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]


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
    def test_effective_journal_options_respect_later_vendor_overrides(self):
        first = '[Journal]\nStorage=volatile\nForwardToSyslog=no\nRuntimeMaxUse=64M\n'
        vendor = '# /usr/lib/systemd/journald.conf.d/syslog.conf\n[Journal]\nForwardToSyslog=yes\n'
        self.assertEqual(wear.journal_options(first + vendor)['ForwardToSyslog'], 'yes')
        self.assertEqual(wear.journal_options(first + vendor + first)['ForwardToSyslog'], 'no')
        self.assertEqual(wear.journal_options(first + '[Other]\nStorage=persistent')['Storage'], 'volatile')

    def test_boot_guard_prepares_sshd_directory_before_configuration_probe(self):
        events = []
        config, run_dir, rules_file, temp_file = Mock(), Mock(), Mock(), Mock()
        config.read_text.return_value = 'eth0\n'
        run_dir.mkdir.side_effect = lambda **kwargs: events.append('directory')
        rules_file.with_suffix.return_value = temp_file
        def run(args, **kwargs):
            events.append(args[0])
            if args[0] == '/usr/sbin/sshd':
                self.assertIn('directory', events)
                return Mock(stdout='port 2222\n')
            self.assertIn('22, 2222', kwargs['input'])
        paths = {'/etc/zmalacall/ssh-interface': config, '/run/sshd': run_dir,
                 '/etc/nftables.d/zmala-ssh.nft': rules_file}
        with patch.object(guard, 'Path', side_effect=paths.__getitem__), \
                patch.object(guard.subprocess, 'run', side_effect=run), patch.object(guard.os, 'replace') as replace:
            guard.main()
        self.assertEqual(events, ['directory', '/usr/sbin/sshd', '/usr/sbin/nft', '/usr/sbin/nft'])
        replace.assert_called_once_with(temp_file, rules_file)

    def test_display_mode_uses_only_connected_supported_outputs(self):
        query = ('HDMI-1 disconnected\n   1280x720 60.0\nHDMI-2 connected primary 3840x2160+0+0\n'
                 '   3840x2160 30.0*+\n   1280x720 60.0 50.0\nDP-1 connected\n   1024x768 60.0\n')
        self.assertEqual(kiosk.display_outputs(query, '1280x720'), ['HDMI-2'])
        self.assertEqual(kiosk.display_outputs(query, '1920x1080'), [])

    def test_guard_covers_ipv4_ipv6_custom_ports_and_socket_activation(self):
        value = guard.rules('eth0', [2222, 2222])
        self.assertIn('table inet zmala_ssh', value)
        self.assertIn('hook input priority -10', value)
        self.assertIn('iifname != "eth0" tcp dport { 22, 2222 } counter drop', value)
        self.assertNotIn('flush ruleset', value)
        for interface in ('eth0"; accept', '', '../eth0', 'x' * 16):
            with self.assertRaises(ValueError):
                guard.rules(interface, [22])
        with self.assertRaises(ValueError):
            guard.rules('eth0', [65536])

    def test_branding_preserves_disk_uart_country_and_video_mode(self):
        old = 'console=serial0,115200 console=tty1 root=PARTUUID=abc rootwait cfg80211.ieee80211_regdom=GB video=HDMI-A-1:1280x720@60D\n'
        new = boot.quiet_command_line(old)
        self.assertNotIn('console=tty1', new)
        for value in old.split():
            if value != 'console=tty1':
                self.assertIn(value, new.split())
        self.assertEqual(boot.quiet_command_line(new), new)
        self.assertEqual(new.count('\n'), 1)

    def test_pair_only_one_presenter_currently_advertising_hid(self):
        props = {'Name': pair.NAME, 'UUIDs': [pair.HID], 'RSSI': -40}
        self.assertEqual(pair.candidate({'/one': props}), '/one')
        self.assertIsNone(pair.candidate({'/one': props, '/two': props}))
        for invalid in ({**props, 'Name': 'Keyboard'}, {**props, 'UUIDs': []},
                        {**props, 'Blocked': True}, {**props, 'Paired': True},
                        {key: value for key, value in props.items() if key != 'RSSI'}):
            self.assertIsNone(pair.candidate({'/one': invalid}))

    def test_agent_rejects_other_devices_and_passkey_requests(self):
        agent = pair.Pairing.__new__(pair.Pairing)
        agent.target = '/chosen'
        for method, path, allowed in [('RequestAuthorization', '/other', False),
                                      ('RequestConfirmation', '/chosen', True),
                                      ('RequestPasskey', '/chosen', False),
                                      ('AuthorizeService', '/chosen', True)]:
            parameters, invocation = Mock(), Mock()
            parameters.unpack.return_value = (path,)
            agent.authorize(None, None, None, None, method, parameters, invocation)
            self.assertEqual(invocation.return_value.called, allowed)
            self.assertEqual(invocation.return_dbus_error.called, not allowed)

    def test_status_changes_written_atomically_without_device_secrets(self):
        agent = pair.Pairing.__new__(pair.Pairing)
        agent.state = None
        with tempfile.TemporaryDirectory() as folder, patch.object(pair, 'STATUS', Path(folder) / 'status.json'):
            agent.publish('paired')
            self.assertEqual(json.loads(pair.STATUS.read_text()), {'state': 'paired'})
            self.assertFalse(pair.STATUS.with_suffix('.tmp').exists())

    def test_pairing_token_survives_restart_but_changes_when_repaired(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(pair, 'BOND', Path(folder)/'bond.json'):
            first = pair.bond_token('/remote')
            self.assertEqual(first, pair.bond_token('/remote'))
            renewed = pair.bond_token('/remote', renew=True)
            self.assertNotEqual(first, renewed)
            self.assertEqual(renewed, pair.bond_token('/remote'))
            self.assertNotEqual(renewed, pair.bond_token('/replacement'))


if __name__ == '__main__':
    unittest.main()
