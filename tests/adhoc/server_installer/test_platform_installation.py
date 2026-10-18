# Installer regression tests; outside the Pi runtime requirements baseline.
import io
import json
import sys
import unittest
from unittest.mock import patch

from tests.support.linux_units import ROOT, load, shell
from build_tools.server_installer.backend import Deployment, InstallError

guard = load('ssh-guard')
ssh = load('server-ssh')
check = load('check-server')


class ServerPlatformTests(unittest.TestCase):
    def test_post_reboot_inspection_rejects_each_failed_readiness_or_storage_policy(self):
        values = {'/var/lib/zmalacall-server/server.json':json.dumps({'http_port':8080,'sip_port':5060}),
                  '/proc/swaps':'Filename Type\n/dev/zram0 partition\n', '/sys/block/zram0/backing_dev':'none'}
        observations = {('systemd-analyze','cat-config','systemd/journald.conf'):'[Journal]\nStorage=volatile\nRuntimeMaxUse=64M\nForwardToSyslog=no',
            ('ss','-H','-ltn'):'0.0.0.0:8080 \n0.0.0.0:5060 ', ('ss','-H','-lun'):'0.0.0.0:5060 ',
            ('systemctl','is-active','zmalacall-server'):'active', ('systemctl','is-active','zmalacall-ssh-guard'):'active',
            ('findmnt','-no','FSTYPE','/tmp'):'tmpfs', ('findmnt','-no','OPTIONS','/'):'rw,noatime'}
        with patch.object(check.Path, 'read_text', autospec=True, side_effect=lambda p: values[str(p).replace('\\','/')]), \
                patch.object(check, 'command', side_effect=lambda *args: observations[args]), \
                patch.object(check.urllib.request, 'urlopen', side_effect=lambda *a, **k: io.BytesIO(b'{"ok":true}')):
            self.assertTrue(all(check.inspect().values()))
            observations[('ss','-H','-ltn')] = '0.0.0.0:8080 '
            self.assertFalse(check.inspect()['sip_all_interfaces'])
            observations[('ss','-H','-ltn')] = '0.0.0.0:8080 \n0.0.0.0:5060 '
            for key in list(observations):
                previous = observations[key]; observations[key] = 'wrong'
                self.assertFalse(all(check.inspect().values()), key)
                observations[key] = previous
            values['/proc/swaps'] = 'Filename Type\n/swapfile file\n'
            self.assertFalse(check.inspect()['ram_only_swap'])


    def test_reboot_waits_for_changed_boot_and_stable_pid_then_runs_checks(self):
        deployment = Deployment('fixture')
        times = iter([0, 1, 4, 7, 8, 20, 21])
        with patch.object(deployment, 'connect'), patch.object(deployment, 'probe', side_effect=[{'boot_id':'old'}, {'boot_id':'new'}, {'boot_id':'new'}]), \
                patch.object(deployment, 'command', return_value='123') as command, \
                patch('build_tools.server_installer.backend.time.monotonic', side_effect=lambda: next(times)), \
                patch('build_tools.server_installer.backend.time.sleep'):
            deployment.verify_server_reboot('old')
        self.assertTrue(any('check-server.py' in c.args[0] for c in command.call_args_list))
        self.assertTrue(any('nft list table' in c.args[0] for c in command.call_args_list))
        with patch('build_tools.server_installer.backend.time.monotonic', side_effect=[0,301]):
            with self.assertRaises(InstallError):
                deployment.verify_server_reboot('old')


    @unittest.skipIf(sys.platform == 'win32', 'Shell rollback unit executes on Linux CI')
    def test_switched_release_failure_runs_only_application_rollback(self):
        source = (ROOT/'build_tools/linux/install-server.sh').read_text()
        function = source.split('task_finish() {',1)[1].split('\n}\n',1)[0]
        for code, switched, old, rollback in ((1,'yes','/previous',True),(0,'yes','/previous',False),(1,'no','/previous',False),(1,'yes','',False)):
            script = 'task_finish() {'+function+'\n}\n'
            script += 'ln() { echo "LINK $*"; }; systemctl() { echo "SERVICE $*"; };\n'
            script += f"task_stage=test; task_switched={switched}; task_old='{old}'; (exit {code}); task_finish\n"
            result = shell(script)
            self.assertEqual(result.returncode, code)
            self.assertEqual('SERVICE restart zmalacall-server' in result.stdout, rollback)
            self.assertEqual('LINK -sfn /previous /opt/zmalacall-server/current' in result.stdout, rollback)
