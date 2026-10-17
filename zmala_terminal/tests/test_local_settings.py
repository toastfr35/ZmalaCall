import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_settings import FIELDS, SettingsHold, SettingsDraft, ANSWER_DELAYS
from localization import LANGUAGES
from configuration import Configuration, validate
from model import TerminalModel, State
from management import ManagementLoop
from test_terminal import config


class LocalSettingsTests(unittest.TestCase):
    def test_hold_indicator_after_two_seconds_opens_after_ten(self):
        hold = SettingsHold(); hold.start(100)
        self.assertFalse(hold.update(101.99)); self.assertFalse(hold.capturing)
        self.assertFalse(hold.update(102)); self.assertTrue(hold.capturing)
        self.assertAlmostEqual(hold.progress, .2)
        hold.start(105)  # Repeated down events must not restart the clock.
        self.assertFalse(hold.update(109.99))
        self.assertTrue(hold.update(110))
        hold.clear()
        self.assertFalse(hold.update(120)); self.assertFalse(hold.capturing)

    def controller(self):
        from settings_control import SettingsControl
        app = SettingsControl()
        app.settings_hold, app.settings_open = SettingsHold(), False
        app.setup_stage, app.keys_down, app.key_release_jobs = None, set(), {}
        app.model = TerminalModel(); app.model.configure(config())
        app.render, app.root, app._press_action = Mock(), Mock(), Mock()
        return app

    def test_early_release_focus_loss_and_other_input_cancel_hold(self):
        for duration in (.5, 2, 9.99):
            app = self.controller(); app.keys_down.add('red')
            with patch('settings_control.time.monotonic', return_value=100):app.press('red')
            app.tick_settings_access(100+duration)
            with patch('settings_control.time.monotonic', return_value=100+duration):app.keyrelease('red')
            app.tick_settings_access(120)
            self.assertFalse(app.settings_open)
            self.assertEqual(app._press_action.call_count, 1 if duration < 2 else 0)
        for cancel in ('focus', 'button'):
            app = self.controller(); app.keys_down.add('red')
            app.press('red'); app.settings_hold.started = 100
            app.tick_settings_access(103)
            app.input_focus_lost() if cancel == 'focus' else app.press('left')
            app.tick_settings_access(120)
            self.assertFalse(app.settings_open)

    def test_call_buttons_and_programmatic_red_never_start_hold(self):
        app = self.controller()
        app.press('red')
        self.assertIsNone(app.settings_hold.started)
        app.keys_down.add('red')
        for state in (State.RINGING, State.CALLING, State.IN_CALL):
            app.model.state = state; app.press('red')
            self.assertIsNone(app.settings_hold.started)
        self.assertEqual(app._press_action.call_count, 4)

    def test_focus_loss_releases_motion_and_invalidates_pending_pointer(self):
        app = self.controller()
        app.keys_down.add('pointer')
        app.pointer_serial = 4
        app.volume_control = Mock()
        app.input_focus_lost()
        self.assertEqual(app.keys_down, set())
        self.assertEqual(app.pointer_serial, 5)
        app.volume_control.pointer.assert_called_once_with(False)

    def test_drafts_do_not_mutate_config_and_combine_auto_answer(self):
        c = config() | {'auto_answer': False, 'auto_answer_seconds': 10}
        original = json.dumps(c)
        draft = SettingsDraft(); draft.row = 1; draft.open(c)
        self.assertEqual(draft.options, list(ANSWER_DELAYS))
        draft.index = 6
        self.assertEqual(draft.change(c), {'auto_answer': True, 'auto_answer_seconds': 600})
        self.assertEqual(json.dumps(c), original)
        draft.index = 0
        self.assertEqual(draft.change(c), {'auto_answer': False, 'auto_answer_seconds': 10})
        draft.row = 3; draft.open(c); draft.index = 100; draft.move(1)
        self.assertEqual(draft.index, 100)

    def test_legacy_answer_delay_selects_next_supported_delay_not_never(self):
        for old, selected in ((5, 10), (20, 30), (90, 120)):
            draft = SettingsDraft(); draft.row = 1
            draft.open(config() | {'auto_answer': True, 'auto_answer_seconds': old})
            self.assertEqual(draft.options[draft.index], selected)
            self.assertEqual(draft.expected['auto_answer_seconds'], old)

    def test_long_countdown_does_not_answer_early_and_red_cancels(self):
        for seconds in ANSWER_DELAYS[1:]:
            c = config() | {'auto_answer': True, 'auto_answer_seconds': seconds}
            validate(c, 'test')
            m = TerminalModel(); m.configure(c)
            with patch('model.time.monotonic', return_value=100):
                m.incoming('alice', 'family.test')
            self.assertIsNone(m.tick(100+seconds-.01))
            self.assertEqual(m.tick(100+seconds), 'answer')
            m.ended(); m.incoming('alice', 'family.test'); m.button('red')
            self.assertIsNone(m.tick(100000))
            self.assertEqual(m.state, State.STOPPING)

    def test_acknowledged_write_persists_and_old_poll_cannot_roll_back(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)/'config.json'
            cfg = Configuration({'device_id': 'test'}, cache)
            reply = config() | {'configuration_version': 5, 'language': 'fr'}
            cfg.request = Mock(return_value=json.dumps(reply).encode())
            self.assertEqual(cfg.update_settings({'language': 'fr'}, {'language': 'en'}), reply)
            self.assertEqual(cfg.cached()['language'], 'fr')
            loop = ManagementLoop(); loop.model = TerminalModel(); loop.model.configure(reply)
            loop.apply_config = Mock()
            loop.apply_poll_config(config() | {'configuration_version': 4, 'language': 'en'})
            loop.apply_config.assert_not_called()
            self.assertEqual(loop.model.config['language'], 'fr')

    def test_native_incoming_timeout_tracks_long_answer_delay(self):
        from engine import Engine
        e = Mock()
        for enabled, seconds, expected in ((False, 600, 60), (True, 10, 60), (True, 120, 150), (True, 600, 630)):
            e.config = {'auto_answer': enabled, 'auto_answer_seconds': seconds}
            Engine.apply_call_timeout(e)
            e.core_set_inc_timeout.assert_called_with(e.core, expected)

    def test_second_green_is_immediate_and_completed_hold_release_keeps_settings(self):
        app = self.controller()
        actions = []
        app._press_action = lambda button: actions.append(app.model.button(button, True))
        app.press('green'); app.press('green')
        self.assertEqual(actions, [None, 'dial'])
        app.model.ended(); app.keys_down.add('red')
        with patch('settings_control.time.monotonic', return_value=100):app.press('red')
        app.tick_settings_access(110)
        self.assertTrue(app.settings_open)
        app.keyrelease('red')
        self.assertTrue(app.settings_open)
        self.assertEqual(actions, [None, 'dial'])

    def test_reset_requires_opening_settings_entry_then_separate_confirmation(self):
        from main import Terminal
        app = self.controller()
        app.settings_open = True; app.settings_draft = SettingsDraft(); app.settings_draft.row = FIELDS.index('reset')
        app.factory_reset = Mock()
        app.press('green')
        self.assertEqual(app.setup_stage, 'reset')
        app.factory_reset.assert_not_called()
        Terminal._press_action(app, 'red')
        self.assertIsNone(app.setup_stage); self.assertTrue(app.settings_open)
        app.press('green')
        app.setup_busy = False
        Terminal._press_action(app, 'green')
        app.factory_reset.assert_called_once()

    def test_only_accepted_incoming_call_interrupts_settings(self):
        from call_control import CallControl
        app = CallControl()
        app.settings_open, app.settings_hold = True, SettingsHold()
        app.setup_stage = None
        app.model = TerminalModel(); app.model.configure(config())
        app.engine, app.reset_gesture, app.root = Mock(), Mock(), Mock()
        app.render = Mock()
        app.call_event(123, 1, 'stranger', 'family.test')
        self.assertTrue(app.settings_open)
        app.call_event(124, 1, 'alice', 'family.test')
        self.assertFalse(app.settings_open)
        self.assertEqual(app.model.state, State.RINGING)

    def test_settings_messages_cover_every_selected_language(self):
        messages = json.loads((Path(__file__).resolve().parents[1]/'shared/settings-messages.json').read_text(encoding='utf-8'))
        self.assertEqual(set(messages), set(LANGUAGES))
        for values in messages.values():
            self.assertEqual(len(values), 12)
            self.assertTrue(all(isinstance(v, str) and v.strip() for v in values))


if __name__ == '__main__':
    unittest.main()
