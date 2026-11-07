# @test T-LLT-087
# @requirements LLR-TERM-NET-009
# @environment portable
# @plan Apply live developer settings with mocked sudo/systemd; reject wrong enrollment, non-HTTPS and alternate host; validate fixed ports and pinned key; confirm cache redaction, tunnel restart on credential changes and deactivation removing runtime secrets. Inspect the SSH command for loopback-only forwarding and strict host-key checking. Check appliance caller separation and unique first-boot host-key preparation without a factory secret.
# @pass No real tunnel is opened. Assertions cover credential scope and process configuration; HLT establishes remote-shell behaviour.
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from tests.support.developer_access import module
from zmala_terminal.linux import developer_access
from zmala_terminal.common.configuration import stable_configuration


class DeveloperTerminalTests(unittest.TestCase):
    def test_image_role_selection_and_private_identity_preparation(self):
        helper = module('developer-access')
        legacy = {'role': 'terminal'}
        self.assertEqual(helper.image_settings(legacy, 'apply', None), legacy)
        settings = {'role': 'combined', 'image': True}
        self.assertEqual(helper.image_settings(settings, 'apply', 'zmalaterminal')['role'], 'terminal')
        for caller in (None, 'zmala', 'other'):
            with self.assertRaises(PermissionError):
                helper.image_settings(settings, 'apply', caller)
        with self.assertRaises(PermissionError):
            helper.image_settings({'role': 'server', 'image': True}, 'apply', 'zmalaterminal')
        self.assertEqual(helper.image_settings(settings, 'prepare', None), settings)
        with tempfile.TemporaryDirectory() as folder, patch.object(helper, 'run') as run:
            helper.HOST_KEY = Path(folder)/'keys/ssh_host_ed25519_key'
            self.assertEqual(helper.prepare({'role': 'terminal', 'image': True}), {'prepared': True})
            self.assertEqual(run.call_args.args, ('ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(helper.HOST_KEY)))
            helper.HOST_KEY.write_text('test fixture')
            run.reset_mock()
            helper.prepare({'role': 'terminal', 'image': True})
            run.assert_not_called()
            with self.assertRaises(ValueError):
                helper.prepare(legacy)

    def setUp(self):
        developer_access._applied = None

    def config(self):
        return {'terminal_id':'serial','session_id':'a'*32,'host':'example.test','port':2222,
                'remote_port':22001,'host_key':'ssh-ed25519 '+'a'*68,'password':'b'*48}

    def test_enrollment_and_https_are_required_and_credentials_not_cached(self):
        bootstrap = {'server_url':'https://example.test','device_id':'serial'}
        with patch.object(Path,'exists',return_value=True), patch.object(developer_access.subprocess,'run',return_value=Mock(returncode=0)) as run:
            developer_access.apply(self.config(), bootstrap)
            self.assertEqual(json.loads(run.call_args.kwargs['input']),self.config())
            for wrong in (bootstrap | {'server_url':'http://example.test'},bootstrap | {'device_id':'other'},bootstrap | {'server_url':'https://other.test'}):
                with self.assertRaises(ValueError):developer_access.apply(self.config(),wrong)
            developer_access.apply(None,bootstrap)
            self.assertEqual(run.call_args.kwargs['input'],'null')
        self.assertNotIn('developer_access',stable_configuration({'contacts':[], 'developer_access':self.config()}))

    def test_validation_restart_and_stop_remove_runtime_credentials(self):
        helper=module('developer-access')
        for field,value in [('port',22),('remote_port',22),('host','-oProxyCommand=bad'),('host_key','unverified'),('password','short')]:
            with self.assertRaises(ValueError):helper.validate(self.config() | {field:value})
        with tempfile.TemporaryDirectory() as folder, patch.object(helper,'run') as run:
            helper.RUNTIME=Path(folder)
            helper.terminal('apply',self.config())
            self.assertEqual(helper.read(helper.RUNTIME/'client.json'),self.config())
            self.assertIn('[example.test]:2222 ssh-ed25519 ',(helper.RUNTIME/'known_hosts').read_text())
            run.reset_mock();helper.terminal('apply',self.config())
            self.assertEqual(len(run.call_args_list),1)
            helper.terminal('off',{})
            self.assertFalse((helper.RUNTIME/'client.json').exists())
            self.assertFalse((helper.RUNTIME/'known_hosts').exists())
            self.assertEqual(run.call_args.args,('systemctl','stop','zmalacall-developer-tunnel.service','zmalacall-developer-shell.service'))

    def test_tunnel_pins_host_uses_private_askpass_and_loopback_forward(self):
        helper=module('developer-access')
        with patch.object(helper,'read',return_value=self.config()),patch.object(helper.os,'execve') as execute:
            helper.tunnel()
            args=execute.call_args.args[1];env=execute.call_args.args[2]
            self.assertIn('127.0.0.1:22001:127.0.0.1:2223',args)
            self.assertIn('StrictHostKeyChecking=yes',args)
            self.assertIn('ExitOnForwardFailure=yes',args)
            self.assertEqual(env['SSH_ASKPASS_REQUIRE'],'force')
            self.assertNotIn(self.config()['password'],str(args)+str(env))
