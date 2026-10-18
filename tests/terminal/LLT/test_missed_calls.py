# @test T-LLT-022
# @requirements TLLR063, TLLR064, TLLR065, TLLR066
# @environment portable
# @plan Drive incoming, rejected, answered, failed and late call events and reload temporary notification state; assert exact per-contact counts, acknowledgement boundaries, identity isolation and restart persistence.
# @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from zmala_terminal.common.missed_calls import MissedCallsStore
from zmala_terminal.common.model import State, TerminalModel
from zmala_terminal.common.call_control import CallControl


def configuration():
    return {'sip': {'username': 'term1', 'domain': 'family.test'}, 'auto_answer': False,
            'auto_answer_seconds': 5,
            'contacts': [{'id': name, 'name': name.title(), 'can_call': True, 'can_receive': True,
                          'auto_answer': False, 'online': True} for name in ('alice', 'bob')]}


class MissedCallsTests(unittest.TestCase):
    def model(self):
        model = TerminalModel()
        model.configure(configuration())
        return model

    def test_remote_hangup_marks_each_contact_once_and_other_calls_preserve_flags(self):
        m = self.model()
        for name in ('alice', 'alice', 'bob'):
            self.assertTrue(m.incoming(name, 'family.test'))
            m.ended(remote=True)
        self.assertEqual(m.missed_calls, {'alice', 'bob'})
        self.assertEqual(m.notifications, {'alice': 2, 'bob': 1})
        self.assertEqual(m.notification_total, 3)
        self.assertTrue(m.incoming('alice', 'family.test'))
        m.button('green')
        m.connected()
        m.ended(remote=True)
        self.assertEqual(m.missed_calls, {'bob'})
        self.assertEqual(m.notifications, {'bob': 1})

    def test_successful_manual_and_auto_answers_persist_only_callers_reset(self):
        for auto_answer in (False, True):
            with self.subTest(auto_answer=auto_answer), tempfile.TemporaryDirectory() as directory:
                m = self.model()
                m.restore_notifications({'alice': 3, 'bob': 2})
                m.config['auto_answer'] = auto_answer
                store = MissedCallsStore(Path(directory)/'missed-calls.json')
                store.save(m.config, m.notifications)
                self.assertTrue(m.incoming('alice', 'family.test'))
                action = m.tick(m.deadline) if auto_answer else m.button('green')
                self.assertEqual(action, 'answer')
                self.assertEqual(m.notification_count('alice'), 3)
                terminal = SimpleNamespace(model=m, engine=SimpleNamespace(call='call'),
                                           missed_calls_store=store, root=Mock(), render=Mock())
                CallControl.call_event(terminal, 'call', 7, 'alice', 'family.test')
                self.assertEqual(m.notifications, {'bob': 2})
                self.assertEqual(MissedCallsStore(store.path).load_counts(m.config), {'bob': 2})
                m.mark_notification('alice')
                CallControl.call_event(terminal, 'call', 8, 'alice', 'family.test')
                self.assertEqual(m.notification_count('alice'), 1)

    def test_unsuccessful_answer_and_late_connection_preserve_notifications(self):
        for action in ('answer', 'decline'):
            with self.subTest(action=action):
                m = self.model()
                m.restore_notifications({'alice': 3})
                m.incoming('alice', 'family.test')
                m.button('green' if action == 'answer' else 'red')
                if action == 'decline':
                    self.assertFalse(m.connected())
                    self.assertEqual(m.state, State.STOPPING)
                m.ended()
                self.assertEqual(m.notifications, {'alice': 3})

    def test_call_and_text_counts_combine_and_confirmation_clears_only_selected(self):
        m = self.model()
        m.mark_notification('alice')
        m.mark_notification('alice')
        self.assertTrue(m.incoming('alice', 'family.test'))
        m.ended(remote=True)
        m.mark_notification('bob')
        self.assertEqual(m.notifications, {'alice': 3, 'bob': 1})
        self.assertEqual(m.notification_total, 4)
        m.button('green')
        self.assertEqual(m.notifications, {'bob': 1})
        m.button('red')
        self.assertEqual(m.notification_total, 1)
        m.mark_notification('alice')
        self.assertEqual(m.notification_count('alice'), 1, 'New notifications after acknowledgment start at one')

    def test_counts_survive_updates_and_restart_with_legacy_flags_migrating_to_one(self):
        m = self.model()
        m.mark_notification('alice');m.mark_notification('alice');m.mark_notification('bob')
        c = configuration()
        m.configure(c)
        self.assertEqual(m.notifications, {'alice': 2, 'bob': 1})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'missed-calls.json'
            store = MissedCallsStore(path)
            store.save(c, m.notifications)
            restored = self.model()
            restored.restore_notifications(MissedCallsStore(path).load_counts(c))
            self.assertEqual(restored.notifications, {'alice': 2, 'bob': 1})
            self.assertEqual(restored.notification_total, 3)
            c['contacts'].pop()
            restored.configure(c)
            self.assertEqual(restored.notifications, {'alice': 2})
            c = copy.deepcopy(c)
            c['sip']['username'] = 'term2'
            restored.configure(c)
            self.assertFalse(restored.notifications)
            path.write_text(json.dumps({'account': store.account(configuration()), 'contacts': ['alice','bob']}))
            self.assertEqual(store.load_counts(configuration()), {'alice': 1, 'bob': 1})
            for count in (0,-1,True,'2'):
                path.write_text(json.dumps({'account': store.account(configuration()), 'contacts': ['alice'], 'counts': {'alice':count}}))
                self.assertFalse(store.load_counts(configuration()))

    def test_declined_answered_failed_and_outgoing_calls_do_not_create_badges(self):
        for action in ('decline', 'answer', 'auto-answer', 'connected', 'failure', 'outgoing'):
            with self.subTest(action=action):
                m = self.model()
                if action == 'outgoing':
                    m.button('green')
                    m.button('green')
                else:
                    self.assertTrue(m.incoming('alice', 'family.test'))
                    if action == 'decline':
                        m.button('red')
                    elif action == 'answer':
                        m.button('green')
                    elif action == 'auto-answer':
                        m.deadline = 1
                        self.assertEqual(m.tick(2), 'answer')
                    elif action == 'connected':
                        m.connected()
                m.ended(remote=action != 'failure')
                self.assertFalse(m.missed_calls)
                self.assertEqual(m.state, State.HOME)

    def test_navigation_keeps_badges_but_call_or_callback_confirmation_clears_only_selected(self):
        for online in (True, False):
            with self.subTest(online=online):
                m = self.model()
                m.missed_calls.update(('alice', 'bob'))
                m.button('right')
                m.button('left')
                self.assertEqual(m.missed_calls, {'alice', 'bob'})
                m.selected['online'] = online
                m.button('green')
                self.assertEqual(m.missed_calls, {'bob'})
                self.assertEqual(m.state, State.CONFIRMING if online else State.CONFIRM_CALLBACK)
                m.button('red')
                self.assertEqual(m.missed_calls, {'bob'})
                self.assertEqual(m.state, State.HOME)

    def test_configuration_updates_preserve_flags_and_remove_deleted_contacts_or_other_account(self):
        m = self.model()
        m.missed_calls.update(('alice', 'bob'))
        c = configuration()
        c['contacts'][0]['name'] = 'Alice Smith'
        m.configure(c)
        self.assertEqual(m.missed_calls, {'alice', 'bob'})
        c = copy.deepcopy(c)
        c['contacts'].pop()
        m.configure(c)
        self.assertEqual(m.missed_calls, {'alice'})
        c = copy.deepcopy(c)
        c['sip']['username'] = 'term2'
        m.configure(c)
        self.assertFalse(m.missed_calls)

    def test_persistence_restart_acknowledgment_account_isolation_and_reset(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'missed-calls.json'
            c = configuration()
            store = MissedCallsStore(path)
            self.assertFalse(store.load(c))
            store.save(c, {'alice', 'bob'})
            restarted = MissedCallsStore(path)
            self.assertEqual(restarted.load(c), {'alice', 'bob'})
            different = copy.deepcopy(c)
            different['sip']['username'] = 'term2'
            self.assertFalse(restarted.load(different))
            different['sip'] = {'username': 'term1', 'domain': 'another.test'}
            self.assertFalse(restarted.load(different))
            restarted.save(c, {'bob'})
            self.assertEqual(MissedCallsStore(path).load(c), {'bob'})
            c['contacts'].pop()
            self.assertFalse(MissedCallsStore(path).load(c))
            restarted.clear()
            self.assertFalse(path.exists())
            self.assertFalse(MissedCallsStore(path).load(c))

    def test_invalid_saved_data_does_not_break_startup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'missed-calls.json'
            c = configuration()
            for value in ('not json', [], {'account': ['family.test', 'term1'], 'contacts': [None]},
                          {'account': ['family.test', 'term1'], 'contacts': ['alice']*41}):
                path.write_text(value if isinstance(value, str) else json.dumps(value), encoding='utf-8')
                self.assertFalse(MissedCallsStore(path).load(c))


if __name__ == '__main__':
    unittest.main()
