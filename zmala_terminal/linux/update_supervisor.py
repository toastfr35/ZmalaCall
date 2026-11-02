"""Bounded trial orchestration; platform operations are injected by the stable service."""
import time
from zmala_terminal.linux.update_transaction import RecoveryError


# @llr LLR-TERM-MAINT-026
class TrialSupervisor:
    def __init__(self, transactions, operations, clock=time.monotonic, sleep=time.sleep,
                 deadline=90, stable=15):
        self.transactions = transactions
        self.operations = operations
        self.clock = clock
        self.sleep = sleep
        self.deadline = deadline
        self.stable = stable

    def healthy(self):
        end = self.clock() + self.deadline
        first = None
        identity = None
        while self.clock() < end:
            state = self.operations.health()
            if state.get('failed'):
                return False
            current = (state.get('pid'), state.get('generation'))
            ready = (state.get('ready') is True and isinstance(current[0], int)
                     and current[0] > 0 and isinstance(current[1], str) and current[1])
            if ready:
                if identity is not None and identity != current:
                    return False  # A restart during trial is not a stable candidate.
                if first is None:
                    identity, first = current, self.clock()
                if self.clock() - first >= self.stable:
                    return True
            else:
                first = None
            self.sleep(1)
        return False

    def activate(self):
        """Return waiting/confirmed/rolled_back; errors retain the recovery overlay.

        The operations owner grants a lease only after call/setup admission is
        fenced in the app. Downloading and staging do not acquire this lease.
        """
        lease = self.operations.claim()
        if lease is None:
            return 'waiting'
        try:
            self.operations.display('updating')
            self.operations.stop()
            ticket = self.transactions.trial()
            self.operations.display('checking')
            self.operations.start()
            if not self.healthy():
                raise RecoveryError('Candidate did not become stable')
        except Exception:
            self.operations.display('rollback')
            self.operations.stop()
            self.transactions.recover()
            pending = self.transactions.read('pending')
            if pending and pending.get('state') == 'ready':
                pending['state'] = 'quarantined'
                self.transactions.write('pending', pending)
            self.operations.start()
            if not self.healthy():
                self.operations.display('recovery_failed')
                raise RecoveryError('Confirmed application requires recovery') from None
            self.operations.finish(lease)
            return 'rolled_back'
        # A confirmation/finish I/O failure is recovered by the stable launcher;
        # never reinterpret a possibly committed confirmation as trial failure.
        self.transactions.confirm(ticket)
        self.operations.finish(lease)
        return 'confirmed'
