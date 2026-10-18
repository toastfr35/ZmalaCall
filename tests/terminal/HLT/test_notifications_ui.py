# @test T-HLT-024
# @requirements HLR-TERM-HISTORY-013
# @environment display
# @plan Deliver signed text notifications at the native ABI boundary into the real Engine validator, UI controller, model and atomic notification store. Reject forged/duplicate/foreign messages, add a missed call, reconstruct persisted counts, acknowledge a contact and change account scope. Inspect saved JSON for content leakage.
# @pass Only authorized new notifications increase counts; the model restores unread counts and saves acknowledgements without message bodies or credentials. Native transport is substituted; this test does not establish cross-engine deduplication beyond the implemented in-memory window.

import copy
import hashlib
import hmac
import json
import os
import sys
import unittest
from types import SimpleNamespace

from tests.support.terminal.ui_fixture import terminal_fixture, pump
from zmala_terminal.common.engine import Engine
from zmala_terminal.common.missed_calls import MissedCallsStore
from zmala_terminal.common.model import TerminalModel, State


@unittest.skipUnless(sys.platform == 'linux' and os.environ.get('DISPLAY'), 'Linux Tk display required')
class NotificationUITests(unittest.TestCase):
    def test_signed_messages_missed_call_restart_and_acknowledgement(self):
        with terminal_fixture() as (app, directory):
            message = {'id': 'message-1', 'sender': 'alice', 'domain': 'family.test', 'proof': ''}
            config = app.model.config
            adapter = SimpleNamespace(config=config, on_message=app.message_event, _seen_messages=set(),
                chat_message_is_text=lambda _: True,
                chat_message_get_utf8_text=lambda _: b'PRIVATE MESSAGE BODY',
                chat_message_get_from_address=lambda _: 1,
                address_get_username=lambda _: message['sender'].encode(),
                address_get_domain=lambda _: message['domain'].encode(),
                chat_message_get_custom_header=lambda _, name:
                    message['id'].encode() if name == b'X-Zmala-Message-Id' else message['proof'].encode())

            def deliver(valid=True):
                message['proof'] = hmac.new(config['call_auth_key'].encode(),
                    f"message:{message['id']}:{message['sender']}".encode(), hashlib.sha256).hexdigest() if valid else 'forged'
                Engine._message_event(adapter, 0, 0, 1)
                pump(app)

            deliver(False)
            self.assertEqual(app.model.notifications, {})
            deliver(); deliver()
            self.assertEqual(app.model.notifications, {'alice': 1})
            for sender, domain in [('outsider', 'family.test'), ('alice', 'foreign.test')]:
                message.update(id='rejected', sender=sender, domain=domain)
                deliver()
            self.assertEqual(app.model.notifications, {'alice': 1})
            message.update(id='message-2', sender='alice', domain='family.test')
            deliver()
            app.call_event(42, 1, 'bob', 'family.test')
            self.assertEqual(app.model.state, State.RINGING)
            app.call_event(42, 14, 'bob', 'family.test')
            pump(app)
            self.assertEqual(app.model.notifications, {'alice': 2, 'bob': 1})
            path = directory/'notifications.json'
            raw = path.read_text()
            self.assertEqual(set(json.loads(raw)), {'account', 'contacts', 'counts'})
            for private in ('PRIVATE MESSAGE BODY', config['call_auth_key'], config['sip']['password'], 'message-1'):
                self.assertNotIn(private, raw)

            # Reconstruct both store and model, as after a process restart.
            restored = TerminalModel()
            restored.configure(config)
            restored.restore_notifications(MissedCallsStore(path).load_counts(config))
            self.assertEqual(restored.notifications, {'alice': 2, 'bob': 1})
            app.model = restored
            app.missed_calls_store = MissedCallsStore(path)
            app.model.index = next(i for i, c in enumerate(app.model.contacts) if c['id'] == 'alice')
            app.press('green')  # Opening the contact acknowledges its badge.
            self.assertEqual(app.model.notifications, {'bob': 1})
            self.assertEqual(MissedCallsStore(path).load_counts(config), {'bob': 1})
            other = copy.deepcopy(config)
            other['sip']['username'] = 'other-terminal'
            self.assertEqual(MissedCallsStore(path).load_counts(other), {})


if __name__ == '__main__':
    unittest.main()
