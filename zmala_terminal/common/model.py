"""Platform-independent four-button behaviour and caller permissions."""
from enum import Enum
import time
from zmala_terminal.common.carousel import carousel_contacts


class State(str, Enum):
    HOME = 'home'
    CONFIRMING = 'confirming call'
    CONFIRM_CALLBACK = 'confirming callback request'
    REQUESTING_CALLBACK = 'requesting callback'
    CALLING = 'calling'
    RINGING = 'ringing'
    CONNECTING = 'connecting'
    IN_CALL = 'in call'
    STOPPING = 'ending call'


class TerminalModel:
    def __init__(self):
        self.state = State.HOME
        self.config = None
        self.index = 0
        self.contact = None
        self.deadline = None
        self.callback_request = None
        self.missed_calls = set()
        self.notification_counts = {}
        # Legacy flag-based callers still use missed_calls. Missing counts mean
        # one notification; every production mutation goes through the methods below.

    def notification_count(self, person):
        return self.notification_counts.get(person, 1) if person in self.missed_calls else 0

    @property
    def notifications(self):
        return {person: self.notification_count(person) for person in self.missed_calls}

    @property
    def notification_total(self):
        return sum(self.notifications.values())

    def mark_notification(self, person):
        count = self.notification_count(person)+1
        self.missed_calls.add(person)
        self.notification_counts[person] = count

    def acknowledge_notifications(self, person):
        changed = person in self.missed_calls
        self.missed_calls.discard(person)
        self.notification_counts.pop(person, None)
        return changed

    def restore_notifications(self, counts):
        self.missed_calls = set(counts)
        self.notification_counts = dict(counts)

    @property
    def contacts(self):
        return [c for c in self.config.get('contacts', []) if c['can_call']] if self.config else []

    @property
    def selected(self):
        return self.contacts[self.index % len(self.contacts)] if self.contacts else None

    @property
    def carousel(self):
        return carousel_contacts(self.contacts, self.index)

    def pending_callback(self, person):
        """Only requests sent by this terminal can be cancelled here."""
        if not self.config or not person:
            return None
        own = self.config['sip']['username']
        return next((r for r in self.config.get('callbacks', [])
                     if r.get('status') == 'pending' and r.get('from') == own and r.get('to') == person['id']), None)

    def confirm_callback_cancellation(self):
        request = self.pending_callback(self.selected)
        if request:
            self.contact = dict(self.selected)
            self.callback_request = dict(request)
            self.state = State.CONFIRM_CALLBACK

    def configure(self, config):
        old = self.selected
        if self.config and (self.config['sip']['username'], self.config['sip']['domain'].lower()) != (config['sip']['username'], config['sip']['domain'].lower()):
            self.missed_calls.clear()
            self.notification_counts.clear()
        self.config = config
        self.missed_calls.intersection_update(c['id'] for c in config.get('contacts', []) if c['can_call'])
        self.notification_counts = self.notifications
        if old:
            self.index = next((i for i, c in enumerate(self.contacts) if c['id'] == old['id']), 0)
        else:
            self.index = 0

    def incoming(self, username, domain):
        if self.state not in (State.HOME, State.CONFIRMING, State.CONFIRM_CALLBACK, State.REQUESTING_CALLBACK) or not self.config or domain.lower() != self.config['sip']['domain'].lower():
            return False
        contact = next((c for c in self.config['contacts'] if c['id'] == username and c['can_receive']), None)
        if not contact:
            return False
        self.contact = dict(contact)
        self.state = State.RINGING
        auto_answer = self.config.get('auto_answer', contact.get('auto_answer', False))
        self.deadline = time.monotonic() + self.config['auto_answer_seconds'] if auto_answer else None
        return True

    def button(self, button, registered=True):
        if self.state == State.HOME:
            if button == 'red' and self.pending_callback(self.selected):
                self.confirm_callback_cancellation()
            elif button in ('left', 'right') and self.contacts:
                self.index = (self.index + (-1 if button == 'left' else 1)) % len(self.contacts)
            elif button == 'green' and self.selected and (registered or self.selected.get('online') is not True):
                self.confirm_selected(self.selected.get('online') is True)
        elif self.state in (State.CONFIRMING, State.CONFIRM_CALLBACK):
            if button != 'green':
                self.ended()
            elif self.state == State.CONFIRM_CALLBACK:
                self.state = State.REQUESTING_CALLBACK
                return 'cancel_callback' if self.callback_request else 'request_callback'
            elif registered:
                self.state = State.CALLING
                return 'dial'
        elif self.state == State.REQUESTING_CALLBACK:
            if button != 'green':
                self.ended()
        elif button == 'red' and self.state != State.STOPPING:
            decline = self.state == State.RINGING
            self.deadline = None
            self.state = State.STOPPING
            return 'decline' if decline else 'end'
        elif button == 'green' and self.state == State.RINGING:
            self.deadline = None
            self.state = State.CONNECTING
            return 'answer'
        return None

    def tick(self, now=None):
        if self.state == State.RINGING and self.deadline is not None and (time.monotonic() if now is None else now) >= self.deadline:
            return self.button('green')
        return None

    def connected(self):
        # A late answer event must not reverse an already requested hang-up.
        changed = False
        if self.state not in (State.STOPPING, State.IN_CALL):
            # Clear only when the call succeeds, not when an answer is attempted.
            # Repeated SIP connected/media events must preserve newer messages.
            if self.contact:
                changed = self.acknowledge_notifications(self.contact['id'])
            self.state = State.IN_CALL
            self.deadline = None
        return changed

    def confirm_selected(self, online):
        self.contact = dict(self.selected)
        self.callback_request = None
        self.acknowledge_notifications(self.contact['id'])
        self.state = State.CONFIRMING if online else State.CONFIRM_CALLBACK
        if not online:
            self.confirm_callback_cancellation()

    def ended(self, remote=False):
        if remote and self.state == State.RINGING and self.contact:
            self.mark_notification(self.contact['id'])
        self.state = State.HOME
        self.contact = None
        self.callback_request = None
        self.deadline = None
