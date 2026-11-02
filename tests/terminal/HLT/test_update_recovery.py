# @test T-HLT-040
# @requirements HLR-TERM-MAINT-021
# @environment portable
# @plan Launch the real transaction owner in subprocesses and SIGKILL after each record/selection checkpoint, then start boot recovery against the persisted files and inspect selected slot and an unchanged enrollment fixture.
# @pass Every killed candidate recovers to the durable confirmed release without touching shared state. This is process-death qualification, not evidence of SD-controller behavior during physical power loss.
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from zmala_terminal.linux.update_transaction import Transactions


@unittest.skipUnless(os.name == 'posix', 'Requires SIGKILL and POSIX filesystem semantics')
class UpdateBootRecoveryTests(unittest.TestCase):
    def test_process_death_at_every_record_boundary_preserves_confirmed_boot(self):
        events = []
        with tempfile.TemporaryDirectory() as root:
            owner = Transactions(root)
            for name in ('working','candidate'): (owner.slots/name).mkdir()
            owner.initialize('working'); owner.checkpoint = events.append
            owner.prepare('candidate'); ticket=owner.trial(); owner.confirm(ticket)
        source = """import os,signal,sys
from zmala_terminal.linux.update_transaction import Transactions
count=[0]
def checkpoint(event):
 if count[0]==int(sys.argv[2]):os.kill(os.getpid(),signal.SIGKILL)
 count[0]+=1
owner=Transactions(sys.argv[1],checkpoint)
owner.prepare('candidate');ticket=owner.trial();owner.confirm(ticket)
"""
        for cut,event in enumerate(events):
            with self.subTest(event=event, cut=cut), tempfile.TemporaryDirectory() as root:
                owner=Transactions(root)
                for name in ('working','candidate'): (owner.slots/name).mkdir()
                owner.initialize('working')
                shared=Path(root)/'enrollment-fixture';shared.write_bytes(b'preserve-state')
                result=subprocess.run([sys.executable,'-c',source,root,str(cut)],timeout=10)
                self.assertEqual(result.returncode,-signal.SIGKILL)
                boot=Transactions(root);confirmed=boot.read('confirmed')['slot']
                self.assertEqual(boot.recover(),confirmed)
                self.assertEqual((Path(root)/'current').resolve(),boot.slot(confirmed).resolve())
                self.assertEqual(shared.read_bytes(),b'preserve-state')
