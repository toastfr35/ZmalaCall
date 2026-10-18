"""Read the installer-enabled pairing service without blocking the UI."""
import json
import os
from pathlib import Path
import time


class PairingStatus:
    def __init__(self):
        self.path = os.environ.get('ZMALA_PAIRING_STATUS')
        self.next_read = 0
        self.state = None
        self.bond = None

    def read(self):
        if not self.path:
            return None  # Desktop/test launchers do not require a Presenter.
        now = time.monotonic()
        if now >= self.next_read:
            self.next_read = now + .5
            try:
                payload = json.loads(Path(self.path).read_text())
                self.state = payload['state']
                self.bond = payload.get('bond') if isinstance(payload.get('bond'), str) else None
                if self.state not in ('paired', 'pairing', 'unpaired', 'bluetooth_unavailable'):
                    self.state = 'bluetooth_unavailable'
            except (OSError, ValueError, KeyError, TypeError):
                self.state = 'bluetooth_unavailable'
                self.bond = None
        return self.state
