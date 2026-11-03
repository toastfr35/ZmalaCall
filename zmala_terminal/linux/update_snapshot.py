"""Private durable settings checkpoint for an unconfirmed application trial.

The application is stopped while copying or exchanging directories. An atomic
exchange keeps the live path present across crashes; a protected marker makes
replaying that exchange safe even if the journal write was interrupted.
"""
import ctypes
import hashlib
import os
from pathlib import Path
import re
import shutil
import stat

from zmala_terminal.linux.update_transaction import RecoveryError, sync_directory

MARKER = '.zmala-update-checkpoint'


def flush_tree(root):
    for directory, directories, files in os.walk(root, followlinks=False):
        for name in files:
            path = Path(directory)/name
            if path.is_symlink():
                continue
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                    raise RecoveryError('Unsupported persistent data entry')
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    for directory, _, _ in os.walk(root, topdown=False, followlinks=False):
        sync_directory(directory)


def preserve_copy(source, target):
    shutil.copy2(source, target, follow_symlinks=False)
    info = os.lstat(source)
    os.chown(target, info.st_uid, info.st_gid, follow_symlinks=False)
    return target


# @llr LLR-TERM-MAINT-032
class DataCheckpoint:
    def __init__(self, transactions, data, root):
        self.transactions = transactions
        self.data = Path(data)
        self.root = Path(root)

    def identity(self, pending):
        identity = pending.get('transaction', '')
        if not isinstance(identity, str) or not re.fullmatch('[a-f0-9]{32}', identity):
            raise RecoveryError('Invalid data checkpoint identity')
        return identity

    def snapshot(self):
        pending = self.transactions.read('pending')
        if not pending or pending.get('state') != 'ready':
            raise RecoveryError('No prepared data checkpoint')
        identity = self.identity(pending)
        if self.data.is_symlink() or not self.data.is_dir():
            raise RecoveryError('Persistent data must be a real directory')
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if (self.root.is_symlink() or self.root.stat().st_mode & 0o077
                or self.root.stat().st_uid != os.geteuid()):
            raise RecoveryError('Data checkpoint directory is not private')
        if self.data.stat().st_dev != self.root.stat().st_dev:
            raise RecoveryError('Data checkpoint must share the data filesystem')
        target = self.root/identity
        if target.exists():
            # A ready transaction can have an incomplete copy from a crash.
            if target.is_symlink() or not target.is_dir():
                raise RecoveryError('Invalid data checkpoint')
            shutil.rmtree(target)
        shutil.copytree(self.data, target, symlinks=True, copy_function=preserve_copy)
        for directory, _, _ in os.walk(self.data, followlinks=False):
            relative = Path(directory).relative_to(self.data)
            info = os.stat(directory)
            os.chown(target/relative, info.st_uid, info.st_gid)
        marker = target/MARKER
        if marker.exists() or marker.is_symlink():
            marker.unlink()
        descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, 'w') as stream:
            stream.write(identity)
            stream.flush()
            os.fsync(stream.fileno())
        flush_tree(target)
        sync_directory(self.root)
        pending['data_checkpoint'] = True
        pending['data_restored'] = False
        self.transactions.write('pending', pending)

    def restore(self):
        pending = self.transactions.read('pending')
        confirmed = self.transactions.read('confirmed') or {}
        if (not pending or not pending.get('data_checkpoint')
                or pending.get('data_restored')
                or confirmed.get('transaction') == pending.get('transaction')):
            return
        identity = self.identity(pending)
        target = self.root/identity
        marker = self.data/MARKER
        restored = False
        if marker.exists() and not marker.is_symlink():
            info = marker.stat()
            restored = (info.st_uid == os.geteuid() and info.st_mode & 0o077 == 0
                        and marker.read_text() == identity)
        if not restored:
            if target.is_symlink() or not target.is_dir() or self.data.is_symlink():
                raise RecoveryError('Data checkpoint unavailable')
            # Linux renameat2 with RENAME_EXCHANGE: no absent-live-directory gap.
            libc = ctypes.CDLL(None, use_errno=True)
            exchange = libc.renameat2
            exchange.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
            exchange.restype = ctypes.c_int
            if exchange(-100, os.fsencode(self.data), -100, os.fsencode(target), 2):
                error = ctypes.get_errno()
                raise OSError(error, os.strerror(error))
            sync_directory(self.data.parent)
            sync_directory(self.root)
            self.transactions.checkpoint('data:exchange')
        pending['data_restored'] = True
        self.transactions.write('pending', pending)
        marker.unlink(missing_ok=True)
        sync_directory(self.data)

    def validate(self):
        """Trials are passive: persistent writes before confirmation are a failure."""
        pending = self.transactions.read('pending') or {}
        target = self.root/self.identity(pending)
        def inventory(root):
            result = {}
            for directory, directories, files in os.walk(root, followlinks=False):
                for name in directories + files:
                    path = Path(directory)/name
                    relative = path.relative_to(root).as_posix()
                    if relative == MARKER:
                        continue
                    info = path.lstat()
                    metadata = (info.st_mode, info.st_uid, info.st_gid)
                    if stat.S_ISLNK(info.st_mode):
                        content = os.readlink(path)
                    elif stat.S_ISREG(info.st_mode):
                        digest = hashlib.sha256()
                        with path.open('rb') as stream:
                            for block in iter(lambda: stream.read(262144), b''):
                                digest.update(block)
                        content = digest.hexdigest()
                    elif stat.S_ISDIR(info.st_mode):
                        content = None
                    else:
                        raise RecoveryError('Unsupported persistent data entry')
                    result[relative] = (metadata, content)
            return result
        if inventory(self.data) != inventory(target):
            raise RecoveryError('Trial changed persistent settings')

    def collect(self):
        """Retain only an in-flight checkpoint; never collect the live directory."""
        if not self.root.exists():
            return
        if (self.root.is_symlink() or self.root.stat().st_uid != os.geteuid()
                or self.root.stat().st_mode & 0o077):
            raise RecoveryError('Data checkpoint directory is not private')
        pending = self.transactions.read('pending') or {}
        keep = pending.get('transaction') if pending.get('state') in ('ready', 'trial') else None
        for target in self.root.iterdir():
            if (target.name != keep and re.fullmatch('[a-f0-9]{32}', target.name)
                    and target.is_dir() and not target.is_symlink()):
                shutil.rmtree(target)
        sync_directory(self.root)
