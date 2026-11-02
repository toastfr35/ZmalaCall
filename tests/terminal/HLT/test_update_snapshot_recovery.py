# @test T-HLT-045
# @requirements HLR-TERM-MAINT-031
# @environment portable
# @plan SIGKILL a real rollback immediately after directory exchange and at each subsequent journal checkpoint; restart recovery twice and inspect live enrollment and current selection.
# @pass Every interrupted restore retains the confirmed settings and application; replay never swaps failed settings back. This qualifies process death, not physical SD power loss.
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from zmala_terminal.linux.update_transaction import Transactions


@unittest.skipUnless(os.name == 'posix', 'Requires Linux directory exchange and SIGKILL')
class DataRecoveryTests(unittest.TestCase):
    def test_restore_survives_process_death_and_replay(self):
        from zmala_terminal.linux.update_snapshot import DataCheckpoint
        source = '''import os,signal,sys
from zmala_terminal.linux.update_transaction import Transactions
from zmala_terminal.linux.update_snapshot import DataCheckpoint
def cut(event):
 if event==sys.argv[2]:os.kill(os.getpid(),signal.SIGKILL)
tx=Transactions(sys.argv[1]+'/updater',cut)
DataCheckpoint(tx,sys.argv[1]+'/data',sys.argv[1]+'/checkpoints').restore()
'''
        for event in ('data:exchange', 'pending:file', 'pending:rename', 'pending:durable'):
            with self.subTest(event=event), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                tx = Transactions(root/'updater')
                for name in ('old', 'new'):
                    (tx.slots/name).mkdir()
                tx.initialize('old')
                tx.prepare('new')
                data = root/'data'
                data.mkdir()
                (data/'enrollment').write_text('confirmed settings')
                owner = DataCheckpoint(tx, data, root/'checkpoints')
                owner.snapshot()
                tx.trial()
                (data/'enrollment').write_text('broken trial settings')
                tx.recover()
                result = subprocess.run([sys.executable, '-c', source, temporary, event], timeout=15)
                self.assertEqual(result.returncode, -signal.SIGKILL)
                owner.restore()
                owner.restore()
                self.assertEqual((data/'enrollment').read_text(), 'confirmed settings')
                self.assertEqual((tx.root/'current').resolve(), tx.slot('old').resolve())
