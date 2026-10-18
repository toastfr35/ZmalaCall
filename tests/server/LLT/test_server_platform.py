# @test S-LLT-029
# @requirements LLR-SRV-START-004, LLR-SRV-START-007, LLR-SRV-HOST-003, LLR-SRV-HOST-004, LLR-SRV-HOST-005
# @environment portable
# @plan Inspect runtime service and bounded RAM journal/zram policy. Inject systemctl and network observations to verify unprivileged startup, wired-only IPv4/IPv6 filtering, guard-before-SSH enablement and refusal during a deployment lock or incorrect guard interface. Exercise fixed-action command entrypoints with mocked subprocesses and bounded command arguments. Check Ethernet address preference and LAN fallback, and reject invalid nft rules before committing their file. Effective mounts and reboot persistence require HLT.
# @pass All service-policy and failure-path assertions must pass; no unit test may modify the host firewall, SSH service or filesystem outside its temporary fixture.

import configparser
import json
import os
import runpy
import sys
import unittest
from unittest.mock import Mock, mock_open, patch

from tests.support.linux_units import ROOT, load

guard = load('ssh-guard')
ssh = load('server-ssh')


class ServerPlatformTests(unittest.TestCase):
    def test_runtime_storage_policy_uses_bounded_ram_journal_and_zram(self):
        from tests.support.host_policy import assert_storage_policy
        assert_storage_policy(self)

    def test_launcher_prefers_ethernet_then_wifi_and_retries_without_lan(self):
        adapters = [{'ifname': name, 'operstate': state, 'addr_info': [{'scope': scope, 'local': ip}]}
                    for name, state, scope, ip in [('lo', 'UP', 'host', '127.0.0.1'),
                    ('eth1', 'UP', 'global', '192.0.2.3'), ('wlan0', 'UP', 'global', '192.0.2.2'),
                    ('eth0', 'UP', 'global', '192.0.2.1')]]
        for data, chosen in [(adapters, '192.0.2.1'), (adapters[:-1], '192.0.2.2'), (adapters[:2], '192.0.2.3')]:
            with patch('subprocess.check_output', return_value=json.dumps(data)) as command, \
                    patch.object(os, 'execv') as execute, patch.dict(os.environ, {}, clear=False):
                runpy.run_path(str(ROOT/'build_tools/linux/server-launch.py'))
                self.assertEqual(os.environ['VIDEOCALL_HOST'], chosen)
                execute.assert_called_once_with('/usr/bin/node', ['node', '/opt/zmalacall-server/current/zmala_server/main.js'])
                command.assert_called_once_with(['ip', '-j', '-4', 'address'], text=True)
        with patch('subprocess.check_output', return_value='[]'), patch.object(os, 'execv') as execute:
            with self.assertRaisesRegex(SystemExit, 'No LAN IPv4'):
                runpy.run_path(str(ROOT/'build_tools/linux/server-launch.py'))
            execute.assert_not_called()

    def test_guard_validates_before_applying_and_only_persists_success(self):
        for ports, failure in [('port 22\nport 2222\n', None), ('', 'ports'), ('port 22\n', 'syntax')]:
            path = Mock()
            path.read_text.return_value = 'eth0'
            def command(args, **kwargs):
                if args[0].endswith('sshd'):
                    return Mock(stdout=ports)
                if failure == 'syntax':
                    raise RuntimeError('syntax')
                self.assertIn('iifname != "eth0"', kwargs['input'])
            with patch.object(guard, 'Path', return_value=path), patch.object(guard.subprocess, 'run', side_effect=command) as run, \
                    patch.object(guard.os, 'replace') as replace:
                if failure:
                    with self.assertRaisesRegex(RuntimeError, failure):
                        guard.main()
                    replace.assert_not_called()
                    path.with_suffix.return_value.write_text.assert_not_called()
                else:
                    guard.main()
                    self.assertEqual([call.args[0] for call in run.call_args_list][1:],
                        [['/usr/sbin/nft', '-c', '-f', '-'], ['/usr/sbin/nft', '-f', '-']])
                    replace.assert_called_once_with(path.with_suffix.return_value, path)
        for port in [0, 65536]:
            with self.assertRaises(ValueError):
                guard.rules('eth0', [port])

    def test_service_is_unprivileged_and_independent_of_terminal(self):
        unit = configparser.ConfigParser(strict=False, interpolation=None)
        unit.read(ROOT/'build_tools/linux/zmalacall-server.service')
        self.assertEqual(unit['Service']['User'], 'zmalaserver')
        self.assertEqual(unit['Service']['Group'], 'zmalaserver')
        self.assertEqual(unit['Install']['WantedBy'], 'multi-user.target')
        self.assertEqual(unit['Service']['Restart'], 'on-failure')
        self.assertNotIn('terminal', str(dict(unit['Unit'])))

    def test_guard_applies_both_ip_families_and_input_interface_not_destination(self):
        rules = guard.rules('eth0', [22, 2222])
        self.assertIn('table inet zmala_ssh', rules)
        self.assertIn('iifname != "eth0" tcp dport { 22, 2222 } counter drop', rules)
        self.assertNotIn('ip daddr', rules)
        for value in ('wlan0; accept', '', '../eth0'):
            with self.assertRaises(ValueError):
                guard.rules(value, [22])

    def test_ssh_enable_applies_guard_first_and_disable_does_not_touch_server(self):
        result = Mock(stdout='loaded', returncode=0)
        with patch.object(ssh, 'Path') as path, patch.object(ssh, 'run', return_value=result) as run, \
                patch.object(sys, 'argv', ['helper','on']), patch('builtins.print'):
            path.return_value.read_text.return_value = 'eth0\n'
            ssh.main()
        commands = [c.args for c in run.call_args_list]
        self.assertEqual(commands[:3], [('systemctl','start','nftables','zmalacall-ssh-guard'),
            ('/usr/bin/python3','/usr/local/libexec/zmala-ssh-guard.py'), ('systemctl','enable','--now','ssh.service')])
        with patch.object(ssh, 'Path') as path, patch.object(ssh, 'run', return_value=result) as run, \
                patch.object(sys, 'argv', ['helper','off']), patch('builtins.print'), \
                patch('builtins.open', mock_open()), patch.object(ssh.fcntl, 'flock'):
            path.return_value.read_text.return_value = 'eth0'
            ssh.main()
        commands = [c.args for c in run.call_args_list]
        self.assertIn(('systemctl','disable','--now','ssh.socket'), commands)
        self.assertIn(('systemctl','disable','--now','ssh.service'), commands)
        self.assertFalse(any('zmalacall-server' in str(c) for c in commands))
        with patch.object(ssh, 'Path') as path, patch.object(ssh, 'run') as run, \
                patch.object(sys, 'argv', ['helper','off']), patch('builtins.open', mock_open()), \
                patch.object(ssh.fcntl, 'flock', side_effect=BlockingIOError):
            path.return_value.read_text.return_value = 'eth0'
            with self.assertRaisesRegex(RuntimeError, 'installation'):
                ssh.main()
            run.assert_not_called()




    def test_ssh_rejects_wrong_guard_before_any_command(self):
        with patch.object(ssh, 'Path') as path, patch.object(ssh, 'run') as run, \
                patch.object(sys, 'argv', ['helper', 'on']):
            path.return_value.read_text.return_value = 'wlan0'
            with self.assertRaisesRegex(RuntimeError, 'wired SSH guard'):
                ssh.main()
            run.assert_not_called()

    def test_status_entrypoint_uses_bounded_read_only_commands(self):
        with patch('subprocess.run', return_value=Mock(returncode=1)) as run, \
                patch.dict(sys.modules, {'fcntl': ssh.fcntl}), \
                patch.object(sys, 'argv', ['helper', 'status']), patch('builtins.print') as output:
            runpy.run_path(str(ROOT/'build_tools/linux/server-ssh.py'), run_name='__main__')
        self.assertEqual([call.args[0] for call in run.call_args_list], [
            ('systemctl', 'is-enabled', 'ssh.service'), ('systemctl', 'is-active', 'ssh.service')])
        for call in run.call_args_list:
            self.assertEqual(call.kwargs, {'check': False, 'capture_output': True, 'text': True, 'timeout': 30})
        self.assertEqual(json.loads(output.call_args.args[0]),
                         {'supported': True, 'enabled': False, 'active': False, 'interface': 'eth0'})

    def test_guard_entrypoint_validates_and_applies_same_rules(self):
        path = Mock()
        path.read_text.return_value = 'eth0'
        with patch('pathlib.Path', return_value=path), \
                patch('subprocess.run', return_value=Mock(stdout='port 22\n')) as run, \
                patch.object(os, 'replace') as replace:
            runpy.run_path(str(ROOT/'build_tools/linux/ssh-guard.py'), run_name='__main__')
        self.assertEqual(run.call_args_list[1].kwargs['input'], run.call_args_list[2].kwargs['input'])
        self.assertEqual(run.call_args_list[1].args[0], ['/usr/sbin/nft', '-c', '-f', '-'])
        self.assertEqual(run.call_args_list[2].args[0], ['/usr/sbin/nft', '-f', '-'])
        replace.assert_called_once_with(path.with_suffix.return_value, path)
