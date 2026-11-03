"""Root-owned updater platform adapter. Never execute a package-supplied root hook."""
import json
import os
from pathlib import Path
import pwd
import stat
import subprocess
import time
import uuid
from zmala_terminal.linux.update_transaction import RecoveryError
from zmala_terminal.linux.update_snapshot import DataCheckpoint


# @llr LLR-TERM-MAINT-030
class Runtime:
    def __init__(self, config, transactions, clock=time.monotonic, run=subprocess.run, sleep=time.sleep):
        self.config = config
        self.transactions = transactions
        self.clock = clock
        self.run = run
        self.sleep = sleep
        self.proc = Path(config.get("proc_root", "/proc"))
        self.user = config['user']
        self.uid = pwd.getpwnam(self.user).pw_uid
        if self.uid == 0:
            raise RecoveryError('Application user must be unprivileged')
        self.request = Path(config.get('request', '/run/zmalacall-updater/state.json'))
        self.status = Path(config.get('status', '/run/zmalacall/update.json'))
        self.nonce = uuid.uuid4().hex
        self.phase = 'idle'
        self.language = 'en'
        self.preserve_sleep = False
        self.baseline_restarts = None
        self.request.parent.mkdir(parents=True, exist_ok=True)

    def checkpoint_data(self):
        DataCheckpoint(self.transactions, self.config.get('data', '/var/lib/zmalacall'),
                       self.config.get('data_checkpoints', '/var/lib/zmalacall-update-data')).snapshot()

    def restore_data(self):
        DataCheckpoint(self.transactions, self.config.get('data', '/var/lib/zmalacall'),
                       self.config.get('data_checkpoints', '/var/lib/zmalacall-update-data')).restore()

    def validate_data(self):
        DataCheckpoint(self.transactions, self.config.get('data', '/var/lib/zmalacall'),
                       self.config.get('data_checkpoints', '/var/lib/zmalacall-update-data')).validate()

    def command(self, args, timeout=30):
        return self.run(args, check=True, capture_output=True, text=True, timeout=timeout)

    def publish(self):
        temporary = self.request.with_suffix('.next')
        value = {'phase': self.phase, 'language': self.language, 'nonce': self.nonce,
                 'preserve_sleep': self.preserve_sleep, 'heartbeat': self.clock()}
        temporary.write_text(json.dumps(value), encoding='utf-8')
        temporary.chmod(0o644)
        os.replace(temporary, self.request)
        report = getattr(self, 'report', None)
        if report:
            report()

    def read_status(self):
        try:
            descriptor = os.open(self.status, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(descriptor, 'r', encoding='utf-8') as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_uid != self.uid or info.st_mode & 0o022 or info.st_size > 8192:
                    return None
                value = json.loads(stream.read(8193))
            pid = value['pid']
            if (type(pid) is not int or pid <= 1 or value['nonce'] != self.nonce
                    or not 0 <= self.clock() - value['heartbeat'] <= 4
                    or not isinstance(value['generation'], str) or len(value['generation']) != 32):
                return None
            process = self.proc / str(pid)
            if process.stat().st_uid != self.uid:
                return None
            groups = (process/'cgroup').read_text().splitlines()
            if not any('zmalacall-terminal.service' in line.split('/') for line in groups):
                return None
            selected = self.transactions.root/'current'
            if selected.exists() and (process/'cwd').resolve() != selected.resolve():
                return None
            return value
        except (OSError, ValueError, TypeError, KeyError):
            return None

    def claim(self):
        self.nonce = uuid.uuid4().hex
        self.phase = 'request'
        deadline = self.clock() + 12
        while self.clock() < deadline:
            self.publish()
            state = self.read_status()
            if state and state.get('maintenance') is True and state.get('eligible') is True:
                language = state.get('language', 'en')
                from zmala_terminal.linux.update_screen import MESSAGES
                self.language = language if isinstance(language, str) and language in MESSAGES else 'en'
                self.preserve_sleep = state.get('sleeping') is True
                pending = self.transactions.read('pending')
                if not pending or pending.get('state') != 'ready':
                    raise RecoveryError('Prepared update disappeared')
                pending.update(language=self.language, preserve_sleep=self.preserve_sleep)
                self.transactions.write('pending', pending)
                return self.nonce
            self.sleep(.5)
        self.phase = 'idle'
        self.publish()
        return None

    def display(self, phase):
        self.phase = phase
        self.publish()
        self.command(['systemctl', 'start', 'zmalacall-update-screen.service'])

    def stop(self):
        self.command(['systemctl', 'stop', 'zmalacall-terminal.service'], timeout=35)

    def start(self):
        self.command(['systemctl', 'reset-failed', 'zmalacall-terminal.service'])
        self.command(['systemctl', 'start', 'zmalacall-terminal.service'])
        self.baseline_restarts = None

    def health(self):
        self.publish()
        result = self.command(['systemctl', 'show', 'zmalacall-terminal.service',
                               '-p', 'ActiveState', '-p', 'NRestarts'])
        values = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
        if values.get('ActiveState') == 'failed':
            return {'failed': True}
        restarts = values.get('NRestarts')
        if self.baseline_restarts is None:
            self.baseline_restarts = restarts
        elif restarts != self.baseline_restarts:
            return {'failed': True}
        state = self.read_status()
        if values.get('ActiveState') != 'active' or not state:
            return {'ready': False}
        return {'ready': state.get('ready') is True and state.get('maintenance') is True,
                'pid': state['pid'], 'generation': state['generation']}

    def finish(self, lease):
        if lease != self.nonce:
            raise RecoveryError('Stale maintenance lease')
        self.phase = 'idle'
        self.publish()

    def recover(self):
        try:
            pending = self.transactions.read('pending')
            invalid = False
        except RecoveryError:
            pending, invalid = None, True
        if pending and 'language' in pending:
            self.language = pending['language']
        if pending and 'preserve_sleep' in pending:
            self.preserve_sleep = pending['preserve_sleep'] is True
        confirmed = self.transactions.read('confirmed')
        if not confirmed:
            raise RecoveryError('No confirmed application')
        selected = self.transactions.root/'current'
        inconsistent = selected.resolve() != self.transactions.slot(confirmed.get('slot')).resolve()
        if invalid or inconsistent or pending and pending.get('state') == 'trial':
            phase = ('checking' if pending and pending.get('transaction') == confirmed.get('transaction')
                     else 'rollback')
            self.display(phase)
            self.stop()
            self.transactions.recover()
            self.restore_data()
            self.start()
            return True
        self.transactions.recover()
        if self.phase not in ('checking', 'updating', 'rollback', 'recovery_failed'):
            self.phase = 'idle'
        self.publish()
        return False
