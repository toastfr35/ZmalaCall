"""A durable, bond-specific check of real Presenter press/release events."""
import json
from pathlib import Path
from zmala_terminal.common.json_storage import write_json

BUTTONS = ('left', 'right', 'green', 'red', 'pointer')


class RemoteTest:
    def __init__(self, path):
        self.path = Path(path)
        try:
            saved = json.loads(self.path.read_text())
            self.verified = saved.get('bond') if saved.get('version') == 1 else None
        except (OSError, ValueError, AttributeError):
            self.verified = None
        self.bond = None
        self.ready = False
        self.index = 0
        self.held = set()
        self.armed = False
        self.error = False

    def sync(self, bond, ready):
        if bond != self.bond or not ready:
            self.index = 0
            self.held.clear()
            self.armed = False
            self.error = False
        self.bond, self.ready = bond, ready

    @property
    def complete(self):
        return bool(self.bond) and self.bond == self.verified

    @property
    def expected(self):
        return BUTTONS[min(self.index, len(BUTTONS)-1)]

    # @llr LLR-TERM-SETUP-007
    def event(self, button, pressed):
        if not self.ready or not self.bond or self.complete:
            return
        if pressed:
            if button in self.held:
                return
            self.held.add(button)
            self.armed = button == self.expected and len(self.held) == 1
        else:
            valid = self.armed and button == self.expected and button in self.held
            self.held.discard(button)
            if not valid:
                return
            self.armed = False
            if self.index == len(BUTTONS)-1:
                try:
                    # @llr LLR-TERM-SETUP-008
                    write_json(self.path, {'version': 1, 'bond': self.bond})
                except OSError:
                    self.error = True
                    return  # Remain on the final step; a new press retries.
                self.verified = self.bond
            else:
                self.index += 1

    def reset(self):
        self.path.unlink(missing_ok=True)
        self.verified = None
        self.sync(None, False)
