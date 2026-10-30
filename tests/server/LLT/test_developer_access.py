# @test S-LLT-065
# @requirements LLR-SRV-HOST-007
# @environment portable
# @plan Mock system commands and isolate persistent state; activate one terminal, reject a second, scope credentials to account and device, rotate passwords after deactivation, and assert daemon termination precedes password locking and secret removal. Generate IPv4/IPv6 subnet rules and verify only wired source prefixes permit ordinary SSH while tunnel port is separate.
# @pass Assertions pass without changing real users or firewall rules; live tunnel and subnet enforcement require HLT.
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tests.support.developer_access import module




class DeveloperAccessTests(unittest.TestCase):
    def test_exclusive_scoped_rotating_session_and_revocation(self):
        helper = module('developer-access')
        with tempfile.TemporaryDirectory() as folder, patch.object(helper, 'run') as run, patch.object(helper, 'connected', return_value=False):
            helper.STATE = Path(folder) / 'session.json'
            request = {'terminal_id': 'term2', 'device_id': 'serial123', 'host': 'example.test'}
            original_read = Path.read_text
            def read(path, *args, **kwargs):
                return 'ssh-ed25519 ' + 'a' * 68 if str(path).endswith('ssh_host_ed25519_key.pub') else original_read(path, *args, **kwargs)
            with patch.object(Path, 'read_text', read):
                public = helper.server('on', request, {})
                self.assertEqual(public['terminal_id'], 'term2')
                self.assertNotIn('password', public)
                private = helper.server('config', request, {})
                self.assertGreaterEqual(len(private['password']), 40)
                self.assertNotIn('account_id', private)
                self.assertIsNone(helper.server('config', request | {'terminal_id': 'term1'}, {}))
                self.assertIsNone(helper.server('config', request | {'device_id': 'other'}, {}))
                with self.assertRaises(ValueError):
                    helper.server('on', request | {'terminal_id': 'term1'}, {})
                with self.assertRaises(ValueError):
                    helper.server('on', request | {'device_id': 'replacement'}, {})
                run.reset_mock()
                helper.server('off', {}, {})
                self.assertEqual(run.call_args_list[0].args, ('systemctl', 'disable', '--now', 'zmalacall-developer.service'))
                self.assertEqual(run.call_args_list[1].args, ('usermod', '-L', 'terminal'))
                self.assertFalse(helper.STATE.exists())
                helper.server('on', request, {})
                self.assertNotEqual(private['password'], helper.server('config', request, {})['password'])

    def test_activation_failure_removes_secret_and_locks_account(self):
        helper = module('developer-access')
        with tempfile.TemporaryDirectory() as folder, patch.object(helper, 'run') as run:
            helper.STATE = Path(folder) / 'state.json'
            request = {'terminal_id':'term2','device_id':'serial','host':'example.test'}
            original_read = Path.read_text
            def read(path, *args, **kwargs):
                return 'ssh-ed25519 ' + 'a' * 68 if str(path).endswith('ssh_host_ed25519_key.pub') else original_read(path, *args, **kwargs)
            def fail(*args, **kwargs):
                if args[:2] == ('systemctl','enable'): raise OSError('failure')
            run.side_effect = fail
            with patch.object(Path, 'read_text', read), self.assertRaises(OSError): helper.server('on',request,{})
            self.assertFalse(helper.STATE.exists())
            self.assertEqual(run.call_args.args, ('usermod', '-L', 'terminal'))

    def test_subnet_rules_cover_both_families_without_public_ssh(self):
        guard = module('developer-lan-guard')
        rules = guard.rules('eth0', [{'local':'192.168.1.181','prefixlen':24}, {'local':'fd00::2','prefixlen':64}], [22])
        self.assertIn('iifname "eth0" ip saddr 192.168.1.0/24 tcp dport { 22 } accept', rules)
        self.assertIn('iifname "eth0" ip6 saddr fd00::/64 tcp dport { 22 } accept', rules)
        self.assertIn('tcp dport { 22 } counter drop', rules)
        self.assertNotIn('2222', rules)
        self.assertNotIn('established', rules)
        self.assertNotIn(' accept', guard.rules('eth0', [], [22]).split('policy accept;')[1])
        with self.assertRaises(ValueError): guard.rules('eth0', [], [2222])
        with self.assertRaises(ValueError): guard.rules('eth0;evil', [], [22])
