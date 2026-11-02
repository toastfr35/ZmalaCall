# @test T-HLT-042
# @requirements HLR-TERM-MAINT-025
# @environment portable
# @plan Supervise actual disposable child processes with the durable transaction owner. Trial a live candidate and an immediately crashing candidate, then inspect confirmation/rollback, maintenance events and cleanup.
# @pass Healthy child readiness confirms its slot; a crashing candidate restores the working child and selected slot. POSIX-only process/system scenario, not real Pi systemd/display qualification.
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from zmala_terminal.linux.update_transaction import Transactions
from zmala_terminal.linux.update_supervisor import TrialSupervisor

@unittest.skipUnless(os.name=='posix','POSIX recovery and process semantics')
class SupervisionIntegrationTests(unittest.TestCase):
    def test_actual_candidate_process_confirmation_and_rollback(self):
        for fail in (False,True):
            with self.subTest(fail=fail),tempfile.TemporaryDirectory() as root:
                transactions=Transactions(root)
                for slot in ('working','candidate'):(transactions.slots/slot).mkdir()
                transactions.initialize('working');transactions.prepare('candidate')
                class Operations:
                    process=None
                    events=[]
                    def claim(self):return 'exclusive'
                    def display(self,state):self.events.append(state)
                    def stop(self):
                        if self.process and self.process.poll() is None:
                            self.process.terminate();self.process.wait(timeout=5)
                    def start(self):
                        selected=(Path(root)/'current').resolve().name
                        code='raise SystemExit(1)' if fail and selected=='candidate' else 'import time;time.sleep(10)'
                        self.process=subprocess.Popen([sys.executable,'-c',code])
                    def health(self):
                        if self.process.poll() is not None:return {'failed':True}
                        return {'ready':True,'pid':self.process.pid,'generation':str(self.process.pid)}
                    def finish(self,lease):self.events.append('finished')
                operations=Operations()
                try:
                    supervisor=TrialSupervisor(transactions,operations,sleep=lambda _:time.sleep(.02),deadline=2,stable=.2)
                    self.assertEqual(supervisor.activate(),'rolled_back' if fail else 'confirmed')
                    expected='working' if fail else 'candidate'
                    self.assertEqual(transactions.read('confirmed')['slot'],expected)
                    self.assertEqual((Path(root)/'current').resolve(),transactions.slot(expected).resolve())
                    self.assertEqual(operations.events[-1],'finished')
                finally:operations.stop()
