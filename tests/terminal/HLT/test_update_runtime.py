# @test T-HLT-046
# @requirements HLR-TERM-MAINT-029
# @environment portable
# @plan Use real durable slots and local heartbeat files with a controlled service-command adapter to grant an idle lease, trial a ready candidate, and recover an interrupted candidate. Include malformed/stale status and verify no OS installer command is issued.
# @pass Only fenced fresh service heartbeats admit a trial; stable candidate readiness confirms, and interrupted trials restore the confirmed slot before service restart. Linux-only service integration is not a hardware run.
import json
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from zmala_terminal.linux.update_transaction import Transactions
from zmala_terminal.linux.update_supervisor import TrialSupervisor


@unittest.skipUnless(os.name == 'posix', 'Requires Linux service filesystem semantics')
class RuntimeIntegrationTests(unittest.TestCase):
    def test_local_lease_confirm_and_interrupted_recovery(self):
        import pwd
        from zmala_terminal.linux.update_runtime import Runtime
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tx = Transactions(root/'updater')
            for name in ('old', 'new', 'bad'):
                (tx.slots/name).mkdir()
            tx.initialize('old')
            tx.prepare('new')
            data = root/'data'
            data.mkdir()
            (data/'enrollment').write_text('preserved')
            proc = root/'proc/123'
            proc.mkdir(parents=True)
            (proc/'cgroup').write_text('0::/system.slice/zmalacall-terminal.service\n')
            now = [100]
            commands = []
            def run(args, **kwargs):
                commands.append(args)
                return SimpleNamespace(stdout='ActiveState=active\nNRestarts=0\n')
            owner = Runtime({'user': pwd.getpwuid(os.getuid()).pw_name,
                             'request': str(root/'request/state.json'), 'status': str(root/'status.json'),
                             'proc_root': str(root/'proc'), 'data': str(data),
                             'data_checkpoints': str(root/'checkpoints')}, tx,
                            clock=lambda: now[0], run=run)
            publish = owner.publish
            def heartbeat():
                publish()
                cwd = proc/'cwd'
                cwd.unlink(missing_ok=True)
                cwd.symlink_to((tx.root/'current').resolve())
                owner.status.write_text(json.dumps({'nonce': owner.nonce, 'pid': 123,
                    'generation': 'a'*32, 'heartbeat': now[0], 'maintenance': True,
                    'eligible': True, 'ready': True, 'language': 'fr', 'sleeping': True}))
                owner.status.chmod(0o600)
            owner.publish = heartbeat
            def sleep(seconds):
                now[0] += seconds
            owner.sleep = sleep
            supervisor = TrialSupervisor(tx, owner, clock=lambda: now[0], sleep=sleep, stable=2)
            self.assertEqual(supervisor.activate(), 'confirmed')
            self.assertEqual(tx.read('confirmed')['slot'], 'new')
            self.assertEqual(owner.language, 'fr')
            self.assertTrue(owner.preserve_sleep)
            tx.prepare('bad')
            owner.checkpoint_data()
            tx.trial()
            (data/'enrollment').write_text('broken')
            self.assertTrue(owner.recover())
            self.assertEqual((data/'enrollment').read_text(), 'preserved')
            self.assertEqual((tx.root/'current').resolve(), tx.slot('new').resolve())
            self.assertTrue(all(command[0] == 'systemctl' for command in commands))
