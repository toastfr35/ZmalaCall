# @test T-LLT-092
# @requirements LLR-TERM-MAINT-022
# @environment portable
# @plan Interrupt every durable record and selection checkpoint during preparation, trial and confirmation. Reopen the transaction owner and compare selection with the confirmed record; reject stale confirmations, path escape, symlink slots and malformed metadata.
# @pass Recovery selects only the separately confirmed slot, interrupted trials are quarantined, and invalid confirmation/paths fail closed. Windows skips POSIX cases; simulated exceptions are not physical power-loss evidence.
import os
from pathlib import Path
import tempfile
import unittest
from zmala_terminal.linux.update_transaction import Transactions, RecoveryError


@unittest.skipUnless(os.name == 'posix', 'POSIX durable directory/symlink semantics')
class UpdateRecoveryTests(unittest.TestCase):
    def owner(self, root):
        owner = Transactions(root)
        for name in ('working', 'candidate'):
            (owner.slots/name).mkdir(exist_ok=True)
        owner.initialize('working')
        return owner

    def test_every_prepare_trial_confirmation_checkpoint_recovers(self):
        events = []
        with tempfile.TemporaryDirectory() as root:
            owner = self.owner(root)
            owner.checkpoint = events.append
            owner.prepare('candidate'); ticket = owner.trial(); owner.confirm(ticket)
        for cut in range(len(events)):
            with self.subTest(cut=cut, event=events[cut]), tempfile.TemporaryDirectory() as root:
                owner = self.owner(root)
                count = [0]
                def crash(event):
                    if count[0] == cut: raise InterruptedError('power interruption')
                    count[0] += 1
                owner.checkpoint = crash
                with self.assertRaises(InterruptedError):
                    owner.prepare('candidate'); ticket = owner.trial(); owner.confirm(ticket)
                recovery = Transactions(root)
                confirmed = recovery.read('confirmed')['slot']
                self.assertEqual(recovery.recover(), confirmed)
                self.assertEqual((Path(root)/'current').resolve(), recovery.slot(confirmed).resolve())
                pending = recovery.read('pending')
                if pending and pending.get('state') == 'quarantined':
                    self.assertEqual(confirmed, 'working')

    def test_stale_confirmation_and_invalid_slots_are_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            owner = self.owner(root)
            owner.prepare('candidate'); owner.trial()
            with self.assertRaises(RecoveryError): owner.confirm('old ticket')
            self.assertEqual(owner.recover(), 'working')
            self.assertEqual(owner.read('pending')['state'], 'quarantined')
            for value in ('../escape','/tmp',None,'missing'):
                with self.assertRaises(RecoveryError): owner.slot(value)
            (owner.slots/'link').symlink_to(owner.slots/'working',target_is_directory=True)
            with self.assertRaises(RecoveryError): owner.slot('link')

    def test_invalid_pending_uses_confirmed_but_invalid_confirmed_fails_closed(self):
        with tempfile.TemporaryDirectory() as root:
            owner = self.owner(root)
            (Path(root)/'pending.json').write_text('{')
            self.assertEqual(owner.recover(),'working')
            (Path(root)/'confirmed.json').write_text('{')
            with self.assertRaises(RecoveryError): owner.recover()
