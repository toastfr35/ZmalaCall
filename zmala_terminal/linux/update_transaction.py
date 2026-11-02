"""Power-loss recovery journal, independent of application slots and UI.

Single writer: the updater service holds the external process lock. Only a
separately confirmed slot is a recovery target. Inputs here are already verified
release identities, not package-provided filesystem paths.
"""
import json
import os
from pathlib import Path
import re
import uuid


class RecoveryError(RuntimeError):
    pass


def sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


# @llr LLR-TERM-MAINT-022
class Transactions:
    """Durable, replayable activation. A crash at every checkpoint is safe."""
    def __init__(self, root, checkpoint=lambda event: None):
        self.root = Path(root)
        self.slots = self.root / 'slots'
        self.root.mkdir(parents=True, exist_ok=True)
        self.slots.mkdir(exist_ok=True)
        self.checkpoint = checkpoint

    def slot(self, identity):
        if not isinstance(identity, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,95}', identity):
            raise RecoveryError('Invalid release identity')
        path = self.slots / identity
        if path.is_symlink() or not path.is_dir() or path.resolve().parent != self.slots.resolve():
            raise RecoveryError('Release slot unavailable')
        return path

    def read(self, name):
        path = self.root / (name + '.json')
        try:
            value = json.loads(path.read_text(encoding='utf-8'))
        except FileNotFoundError:
            return None
        except (ValueError, UnicodeError) as error:
            raise RecoveryError('Invalid recovery record') from error
        if not isinstance(value, dict):
            raise RecoveryError('Invalid recovery record')
        return value

    def write(self, name, value):
        target = self.root / (name + '.json')
        temporary = self.root / (name + '.next')
        with temporary.open('w', encoding='utf-8') as stream:
            json.dump(value, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        self.checkpoint(name + ':file')
        os.replace(temporary, target)
        self.checkpoint(name + ':rename')
        sync_directory(self.root)
        self.checkpoint(name + ':durable')

    def select(self, identity):
        slot = self.slot(identity)
        temporary = self.root / 'current.next'
        temporary.unlink(missing_ok=True)
        temporary.symlink_to(slot.resolve(), target_is_directory=True)
        sync_directory(self.root)
        self.checkpoint('select:prepared')
        os.replace(temporary, self.root / 'current')
        self.checkpoint('select:rename')
        sync_directory(self.root)
        self.checkpoint('select:durable')

    def initialize(self, identity):
        if self.read('confirmed') is not None:
            raise RecoveryError('Already initialized')
        self.slot(identity)
        self.write('confirmed', {'slot': identity, 'transaction': 'initial'})
        self.select(identity)

    def prepare(self, identity):
        """Called only after the complete candidate tree has been fsynced."""
        self.slot(identity)
        confirmed = self.read('confirmed')
        if confirmed is None:
            raise RecoveryError('No confirmed release')
        self.slot(confirmed.get('slot'))
        if identity == confirmed['slot']:
            raise RecoveryError('Candidate is already confirmed')
        pending = self.read('pending')
        if pending and pending.get('state') in ('ready', 'trial'):
            raise RecoveryError('An update is already pending')
        self.write('pending', {'state': 'ready', 'candidate': identity,
                              'previous': confirmed['slot'], 'attempts': 0,
                              'transaction': uuid.uuid4().hex})

    def trial(self):
        pending = self.read('pending')
        confirmed = self.read('confirmed')
        if not pending or pending.get('state') != 'ready' or not confirmed:
            raise RecoveryError('No ready update')
        if pending['previous'] != confirmed['slot']:
            raise RecoveryError('Confirmed release changed')
        self.slot(pending['candidate'])
        pending.update(state='trial', attempts=1)
        self.write('pending', pending)
        self.select(pending['candidate'])
        return pending['transaction']

    def confirm(self, transaction):
        pending = self.read('pending')
        if not pending or pending.get('state') != 'trial' or pending['transaction'] != transaction:
            raise RecoveryError('Stale confirmation')
        self.slot(pending['candidate'])
        # Confirmation is committed before the convenience selection. A restart
        # may replay selection without treating the healthy release as failed.
        self.write('confirmed', {'slot': pending['candidate'], 'previous': pending['previous'],
                                 'transaction': transaction})
        self.select(pending['candidate'])
        pending['state'] = 'confirmed'
        self.write('pending', pending)

    def recover(self):
        """Boot never resumes an unconfirmed trial: one interrupted attempt rolls back."""
        confirmed = self.read('confirmed')
        if not confirmed:
            raise RecoveryError('No confirmed release; recovery installation required')
        self.slot(confirmed.get('slot'))
        try:
            pending = self.read('pending')
        except RecoveryError:
            pending = None
        if pending and pending.get('state') == 'trial':
            if pending.get('transaction') == confirmed.get('transaction'):
                pending['state'] = 'confirmed'
            else:
                pending['state'] = 'quarantined'
            self.write('pending', pending)
        self.select(confirmed['slot'])
        return confirmed['slot']
