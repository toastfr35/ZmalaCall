# @test T-HLT-024
# @requirements HLR-TERM-HISTORY-013, HLR-TERM-HISTORY-014
# @environment display
# @plan Deliver signed text notifications at the native ABI boundary into the real Engine validator, UI controller, model and atomic notification store. Reject forged/duplicate/foreign messages, add a missed call, reconstruct persisted counts, acknowledge a contact and change account scope. Inspect saved JSON for content leakage.
# Render pending incoming callback snapshots on selected/adjacent cards in English/French at 900x620, 1280x720 and 1920x1080. Check the yellow flag/caption stays within the portrait; outgoing requests retain their separate tag; cancellation/completion removes the incoming flag and no call is dialed.
# Inject unanswered outgoing native-end events and terminal timeout/cancel actions through the real controllers. Check the rendered callback question omits an unavailable claim, No returns home, Yes dispatches one callback action, and answered/incoming calls do not offer it. No live SIP/HTTP delivery is claimed by this display fixture.
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
    def test_incoming_callback_has_persistent_flag_without_dialing(self):
        from unittest.mock import Mock
        with terminal_fixture() as (app, _):
            app.text_renderer.photo = Mock(wraps=app.text_renderer.photo)
            own = app.model.config['sip']['username']
            request = {'id': 'incoming-flag', 'from': 'alice', 'to': own, 'status': 'pending'}
            outgoing = {'id': 'outgoing-tag', 'from': own, 'to': 'bob', 'status': 'pending'}
            for language in ('en', 'fr'):
                config = copy.deepcopy(app.model.config); config['language'] = language
                app.apply_config(config)
                for width, height in ((900, 620), (1280, 720), (1920, 1080)):
                    app.root.geometry(f'{width}x{height}')
                    for selected in (0, 1):
                        app.model.index = selected
                        app.model.config['callbacks'] = [request, outgoing]
                        app.text_renderer.photo.reset_mock()
                        app.render(); pump(app)
                        self.assertIn(app.text('callback_received'), [c.args[0] for c in app.text_renderer.photo.call_args_list])
                        banners = app.avatar.find_withtag('callback-banner')
                        self.assertEqual(len(banners), 1)
                        rect = app.avatar.coords(banners[0]); self.assertGreaterEqual(rect[3]-rect[1], 40)
                        self.assertEqual(app.avatar.itemcget(banners[0], 'fill'), '#ffd166')
                        self.assertTrue(app.avatar.find_withtag('callback-received-alice'))
                        self.assertFalse(app.avatar.find_withtag('callback-received-bob'))
                        self.assertTrue(app.avatar.find_withtag('callback-pending-bob'))
                        label = app.avatar.bbox('callback-label')
                        self.assertGreaterEqual(label[0], rect[0]); self.assertLessEqual(label[2], rect[2]+1)
                        self.assertGreaterEqual(label[1], rect[1]-1); self.assertLessEqual(label[3], rect[3]+1)
                        app.engine.dial.assert_not_called()
            for status in ('cancelled', 'completed'):
                app.model.config['callbacks'] = [dict(request, status=status)]
                app.render(); pump(app)
                self.assertFalse(app.avatar.find_withtag('callback-received'))
                app.engine.dial.assert_not_called()

    def test_unanswered_outgoing_calls_offer_callback_on_the_real_ui(self):
        from unittest.mock import Mock
        import time
        with terminal_fixture() as (app, _):
            for ending in ('remote', 'cancel', 'timeout'):
                app.model.ended(); app.model.button('green'); app.model.button('green')
                app.engine.call = 41
                app.engine.end.side_effect = lambda **kw: setattr(app.engine, 'call', None)
                if ending == 'remote': app.call_event(41, 14, 'alice', 'family.test')
                elif ending == 'cancel': app.press('red')
                else:
                    app.outgoing_deadline = time.monotonic()-1
                    app.update_timers(time.monotonic())
                app.render(); pump(app)
                self.assertEqual(app.model.state, State.CONFIRM_CALLBACK)
                self.assertTrue(app.confirmation.winfo_ismapped())
                self.assertTrue(app.confirmation.find_withtag('confirmation-question'))
                self.assertFalse(app.confirmation.find_withtag('confirmation-unavailable'))
                self.assertEqual(app.model.contact['id'], 'alice')
                app.press('red'); self.assertEqual(app.model.state, State.HOME)
            app.model.button('green'); app.model.button('green'); app.engine.call = 42
            app.call_event(42, 14, 'alice', 'family.test'); pump(app)
            app.begin_callback = Mock(); app.press('green')
            app.begin_callback.assert_called_once_with(cancel=False)
            app.model.ended(); app.model.button('green'); app.model.button('green'); app.engine.call = 43
            app.call_event(43, 7, 'alice', 'family.test'); app.press('red')
            self.assertEqual(app.model.state, State.HOME)
            app.model.incoming('alice', 'family.test'); app.engine.call = 44; app.press('red')
            self.assertEqual(app.model.state, State.HOME)
            app.engine.dial.assert_not_called()

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
