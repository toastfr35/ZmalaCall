# @test T-LLT-021
# @requirements LLR-TERM-HISTORY-019, LLR-TERM-HISTORY-020
# @environment portable
# @plan Deliver signed, forged, repeated and excessive messages to a fake SIP receiver; assert only authorized proofs increment counts, duplicates are acknowledged once and retained history is bounded.
# @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

"""Only authenticated text notifications can create contact badges."""
from zmala_terminal.common.media_adapter import MediaAdapter
from zmala_terminal.common.engine import media_backend
import hashlib
import hmac
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from zmala_terminal.common.engine import Engine


class MessageTests(unittest.TestCase):
    def engine(self):
        engine = Engine.__new__(Engine); engine.media = MediaAdapter(media_backend())
        engine.config = {'sip': {'domain': 'family.test'}, 'account_type': 'terminal',
                         'call_auth_key': 'terminal-secret',
                         'contacts': [{'id': 'alice', 'can_receive': True}]}
        engine._seen_messages = set()
        engine.received = []
        engine.on_message = lambda user, domain: engine.received.append((user, domain))
        engine.chat_message_is_text = lambda message: True
        engine.chat_message_get_utf8_text = lambda message: 'Bonjour Evelyn'.encode()
        engine.chat_message_get_from_address = lambda message: 2
        engine.address_get_username = lambda address: b'alice'
        engine.address_get_domain = lambda address: b'family.test'
        engine.headers = {b'X-Zmala-Message-Id': b'one:1', b'X-Family-Auth': hmac.new(
            b'terminal-secret', b'message:one:1:alice', hashlib.sha256).hexdigest().encode()}
        engine.chat_message_get_custom_header = lambda message, name: engine.headers.get(name)
        return engine

    def test_verified_message_is_acknowledged_once_and_new_messages_still_arrive(self):
        e = self.engine()
        e._message_event(0, 0, 1)
        e._message_event(0, 0, 1)
        self.assertEqual(e.received, [('alice', 'family.test')])
        e.headers[b'X-Zmala-Message-Id'] = b'two:1'
        e.headers[b'X-Family-Auth'] = hmac.new(b'terminal-secret', b'message:two:1:alice', hashlib.sha256).hexdigest().encode()
        e._message_event(0, 0, 1)
        self.assertEqual(len(e.received), 2)

    def test_invalid_proof_sender_domain_identity_nontext_or_blank_is_ignored(self):
        for case in ('proof', 'call-proof', 'sender', 'permission', 'domain', 'identity', 'missing-proof', 'nontext', 'blank', 'phone'):
            with self.subTest(case=case):
                e = self.engine()
                if case == 'proof': e.headers[b'X-Family-Auth'] = b'forged'
                elif case == 'call-proof': e.headers[b'X-Family-Auth'] = hmac.new(b'terminal-secret', b'one:1:alice', hashlib.sha256).hexdigest().encode()
                elif case == 'sender': e.address_get_username = lambda address: b'bob'
                elif case == 'permission': e.config['contacts'][0]['can_receive'] = False
                elif case == 'domain': e.address_get_domain = lambda address: b'elsewhere.test'
                elif case == 'identity': e.headers[b'X-Zmala-Message-Id'] = b'x'*257
                elif case == 'missing-proof': e.headers.pop(b'X-Family-Auth')
                elif case == 'nontext': e.chat_message_is_text = lambda message: False
                elif case == 'blank': e.chat_message_get_utf8_text = lambda message: b' '
                elif case == 'phone': e.config['account_type'] = 'linphone'
                e._message_event(0, 0, 1)
                self.assertFalse(e.received)

    def test_duplicate_history_is_bounded(self):
        e = self.engine()
        e._seen_messages.update(str(i) for i in range(256))
        e._message_event(0, 0, 1)
        self.assertEqual(len(e._seen_messages), 256)
        self.assertIn('one:1', e._seen_messages)


if __name__ == '__main__':
    unittest.main()
