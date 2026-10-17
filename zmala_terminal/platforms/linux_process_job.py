"""Own a POSIX session so cancellation also stops command descendants."""
import os
import signal


class ProcessJob:
    def __init__(self):
        self.group = None

    def assign(self, process):
        # Callers start a new session before handing the process to this owner.
        try:
            if os.getpgid(process.pid) != process.pid:
                raise RuntimeError('Managed processes must start in their own session')
        except ProcessLookupError:
            pass  # A fast command may have exited before ownership is attached.
        self.group = process.pid

    def close(self):
        if self.group is not None:
            try:
                os.killpg(self.group, signal.SIGKILL)
            except ProcessLookupError:
                pass
            finally:
                self.group = None
