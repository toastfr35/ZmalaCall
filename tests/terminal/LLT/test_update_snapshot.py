# @test T-LLT-097
# @requirements LLR-TERM-MAINT-032
# @environment portable
# @plan Copy enrollment, nested files and an external symlink into a private checkpoint; detect trial writes, restore twice, and test committed confirmation and unsafe paths.
# @pass Rollback restores original bytes without following symlinks, replay cannot exchange failed data back, and confirmation preserves the accepted live directory. POSIX cases require Linux renameat2.
import os
from pathlib import Path
import tempfile
import unittest
from zmala_terminal.linux.update_transaction import Transactions, RecoveryError


@unittest.skipUnless(os.name == 'posix', 'Requires POSIX atomic directory exchange')
class DataCheckpointTests(unittest.TestCase):
    def setUp(self):
        from zmala_terminal.linux.update_snapshot import DataCheckpoint
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.tx = Transactions(self.root/'updater')
        for name in ('old', 'new'):
            (self.tx.slots/name).mkdir()
        self.tx.initialize('old')
        self.tx.prepare('new')
        self.data = self.root/'data'
        self.data.mkdir()
        (self.data/'enrollment.json').write_text('original')
        (self.data/'nested').mkdir()
        (self.data/'nested/cache').write_text('cached')
        self.external = self.root/'outside'
        self.external.write_text('external')
        (self.data/'link').symlink_to(self.external)
        self.owner = DataCheckpoint(self.tx, self.data, self.root/'checkpoints')

    def test_restore_and_replay_preserve_enrollment_and_symlinks(self):
        self.owner.snapshot()
        self.owner.collect()
        self.owner.validate()
        self.tx.trial()
        (self.data/'enrollment.json').write_text('broken')
        with self.assertRaises(RecoveryError):
            self.owner.validate()
        self.tx.recover()
        self.owner.restore()
        self.owner.restore()
        self.assertEqual((self.data/'enrollment.json').read_text(), 'original')
        self.assertTrue((self.data/'link').is_symlink())
        self.assertEqual(self.external.read_text(), 'external')

    def test_confirmation_never_restores_old_data(self):
        self.owner.snapshot()
        ticket = self.tx.trial()
        self.tx.confirm(ticket)
        (self.data/'enrollment.json').write_text('confirmed')
        self.owner.restore()
        self.assertEqual((self.data/'enrollment.json').read_text(), 'confirmed')
        self.owner.collect()
        self.assertEqual(list(self.owner.root.iterdir()), [])

    def test_checkpoint_rejects_public_or_symlink_directories(self):
        self.owner.root.mkdir(mode=0o755)
        with self.assertRaises(RecoveryError):
            self.owner.snapshot()
        self.owner.root.rmdir()
        self.owner.root.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(RecoveryError):
            self.owner.snapshot()
