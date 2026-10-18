# Installer regression tests; outside the Pi runtime requirements baseline.
import unittest
from unittest.mock import MagicMock, Mock, patch
from build_tools.windows_installer import backend
from build_tools.windows_installer.backend import Deployment
from tests.support.ssh_deployment import SSHContract, Clock
from tests.adhoc.terminal_installer.test_windows_installer import target


class TerminalSSHTests(SSHContract, unittest.TestCase):
    deployment_class = Deployment

    def test_probe_and_preflight_error_messages(self):
        d = self.deployment()
        with patch.object(d, 'command', return_value='{"hostname":"pi"}') as command:
            self.assertEqual(d.probe(), {'hostname':'pi'})
            self.assertEqual(command.call_args.args[0], 'python3 -')
            self.assertIn('SSH_CONNECTION', command.call_args.args[1])
        for failure, message in ((backend.paramiko.AuthenticationException(), 'login failed'),
                                  (OSError('offline'), 'Cannot connect')):
            with patch.object(d, 'connect', side_effect=failure), self.assertRaisesRegex(backend.InstallError, message): d.check()
        with self.assertRaisesRegex(backend.InstallError, 'Ethernet'):
            backend.validate_target(target() | {'ssh_address':'bad'})

    def test_installation_upload_is_private_checked_and_survives_reboot_disconnect(self):
        for argon in (True,False):
            with self.subTest(argon=argon):
                d = self.deployment(); d.info=target(); d.client=MagicMock()
                sftp=d.client.open_sftp.return_value.__enter__.return_value
                def put(*args, **kwargs):
                    for sent,total in ((0,0),(5,100),(10,100),(10,100),(100,100)):
                        kwargs['callback'](sent,total)
                sftp.put.side_effect=put
                d.connect=Mock(); d.probe=Mock(return_value=target()); d.monitor=Mock(); d.verify_reboot=Mock()
                def command(text,*args,**kwargs):
                    if text.startswith('systemctl reboot'): raise EOFError()
                    return ''
                d.command=Mock(side_effect=command)
                with patch.object(backend,'verify_payload',return_value='verified'): d.install('archive.tgz',argon)
                commands=[c.args[0] for c in d.command.call_args_list]
                self.assertTrue(commands[0].startswith('mkdir -m 700 '))
                self.assertEqual(commands[1],'python3 -')
                self.assertIn('verified',d.command.call_args_list[1].args[1])
                self.assertIn("filter='data'",d.command.call_args_list[1].args[1])
                self.assertEqual('--argon-one' in commands[2],argon)
                self.assertEqual(sftp.chmod.call_args.args[1],0o600)
                self.assertEqual([c.args[0] for c in d.emit.call_args_list if c.args[0].startswith('Upload ')],['Upload 0%\n','Upload 10%\n','Upload 100%\n'])
                d.monitor.assert_called_once(); d.verify_reboot.assert_called_once_with('initial-boot')
                self.assertIn('running after reboot',d.emit.call_args.args[0])

    def service_state(self, restarts=0, active=True):
        return '\n\n'.join(f'Id={name}\nActiveState={"active" if active else "failed"}\nNRestarts={restarts}' for name in backend.SERVICES)

    def test_post_reboot_waits_for_all_services_and_stable_restart_counters(self):
        d=self.deployment(); clock=Clock(); d.connect=Mock()
        boots=iter(['old','new']); d.probe=Mock(side_effect=lambda:{'boot_id':next(boots,'new')})
        states=iter([self.service_state(active=False),self.service_state(),self.service_state(1),OSError(),self.service_state(1)])
        checks=[]
        def command(text):
            if text.startswith('systemctl show'):
                value=next(states,self.service_state(1))
                if isinstance(value,Exception): raise value
                return value
            checks.append((text,clock.now)); return ''
        d.command=Mock(side_effect=command)
        with patch.object(backend,'time',clock): d.verify_reboot('old')
        self.assertEqual(checks,[('python3 /opt/zmalacall/current/build_tools/linux/check-low-wear.py',27)])

    def test_post_reboot_timeout_and_low_wear_failure_never_succeed(self):
        d=self.deployment(); d.connect=Mock(); d.probe=Mock(return_value={'boot_id':'old'})
        d.command=Mock()
        with patch.object(backend,'time',Clock()), self.assertRaisesRegex(backend.InstallError,'startup checks'): d.verify_reboot('old')
        d.command.assert_not_called()
        d.probe.return_value={'boot_id':'new'}
        def command(text):
            if text.startswith('systemctl show'): return self.service_state()
            raise backend.InstallError('RAM logging failed')
        d.command.side_effect=command
        with patch.object(backend,'time',Clock()), self.assertRaisesRegex(backend.InstallError,'RAM logging failed'): d.verify_reboot('old')
