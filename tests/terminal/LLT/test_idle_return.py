# @test T-LLT-013
# @requirements LLR-TERM-TV-010, LLR-TERM-TV-013, LLR-TERM-TV-014
# @environment portable
# @plan Advance a controlled clock and inject physical input, TV visibility, calls and pending writes; assert countdown reset, ten-second bar delay, inhibition and one expiry without saving a draft.
# @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from zmala_terminal.common.idle_return import IdleCountdown, IdleReturn
from zmala_terminal.common.local_settings import FIELDS, SettingsDraft, SettingsHold, TV_IDLE_DELAYS
from zmala_terminal.common.model import State, TerminalModel
from tests.terminal.LLT.test_terminal import config
from zmala_terminal.common.configuration import validate


class IdleTests(unittest.TestCase):
    def test_options_default_and_validation(self):
        draft = SettingsDraft()
        draft.row = FIELDS.index('tv_idle_seconds')
        draft.open(config())
        self.assertEqual(draft.options, [30, 60, 120, 300, 600, 1200, 0])
        self.assertEqual(draft.expected, {'tv_idle_seconds': 30})
        for seconds in TV_IDLE_DELAYS:
            validate(config() | {'tv_idle_seconds': seconds}, 'test')
        for bad in (True, '30', 31, -1, 1201, None):
            with self.assertRaises(ValueError):
                validate(config() | {'tv_idle_seconds': bad}, 'test')

    def test_countdown_resets_on_activity_setting_or_new_session_and_expires_once(self):
        timer, session = IdleCountdown(), object()
        self.assertEqual(timer.tick(100, session, 30, 90), (None, False))
        self.assertEqual(timer.tick(115, session, 30, 90), (.5, False))
        self.assertEqual(timer.tick(129, session, 30, 129), (None, False))
        self.assertEqual(timer.tick(130, session, 60, 129), (None, False))
        self.assertEqual(timer.tick(189, session, 60, 129)[1], False)
        self.assertEqual(timer.tick(190, session, 60, 129), (None, True))
        self.assertEqual(timer.tick(191, session, 60, 129), (None, False))
        self.assertEqual(timer.tick(192, object(), 60, 129), (None, False))

    def test_bar_is_hidden_for_ten_seconds_after_each_press(self):
        timer, session = IdleCountdown(), object()
        timer.tick(0, session, 30, 0)
        self.assertEqual(timer.tick(9.99, session, 30, 0), (None, False))
        self.assertAlmostEqual(timer.tick(10, session, 30, 0)[0], 2/3)
        self.assertEqual(timer.tick(20, session, 30, 20), (None, False))
        self.assertEqual(timer.tick(29.99, session, 30, 20), (None, False))
        self.assertAlmostEqual(timer.tick(30, session, 30, 20)[0], 2/3)
        self.assertEqual(timer.tick(50, session, 30, 20), (None, True))

    def test_consumed_reveal_press_starts_clock_before_hdmi_has_finished_switching(self):
        timer, session = IdleCountdown(), object()
        timer.tick(100, None, 30, 100)
        self.assertEqual(timer.tick(105, session, 30, 100), (None, False))
        self.assertAlmostEqual(timer.tick(110, session, 30, 100)[0], 2/3)
        self.assertEqual(timer.tick(130, session, 30, 100), (None, True))

    def test_every_physical_button_resets_even_when_tv_consumes_it(self):
        from zmala_terminal.common.main import Terminal
        from types import SimpleNamespace
        from unittest.mock import patch
        app = SimpleNamespace(key_release_jobs={}, keys_down=set(), last_key={}, last_button=0,
                              remote_setup_blocked=lambda: False, setup_stage=None, tv_setup_button=lambda button: False,
                              tv_control=Mock(), root=Mock(), messages=Mock(), generation=0,
                              model=SimpleNamespace(state=State.HOME), press=Mock(), pointer_serial=0,
                              cancel_settings_hold=Mock(), volume_control=Mock())
        app.input_activity = lambda: Terminal.input_activity(app)
        for button in ('left', 'right', 'green', 'red', 'pointer'):
            app.last_button = 0
            with patch('zmala_terminal.common.input_control.time.monotonic', return_value=100):
                if button == 'pointer':
                    Terminal.pointer_button(app, True)
                else:
                    Terminal.keypress(app, button)
            self.assertEqual(app.last_button, 100, button)
        app.press.assert_not_called()

    def test_never_and_absent_lease_have_no_countdown(self):
        for session, seconds in ((None, 30), (object(), 0)):
            timer = IdleCountdown()
            self.assertEqual(timer.tick(0, session, seconds, 0), (None, False))
            self.assertEqual(timer.tick(10000, session, seconds, 0), (None, False))

    def app(self):
        app = IdleReturn()
        app.model = TerminalModel()
        app.model.configure(config())
        app.setup_stage, app.setup_busy = None, False
        app.keys_down, app.last_button = set(), 0
        app.settings_draft, app.settings_hold = SettingsDraft(), SettingsHold()
        app.idle_countdown = IdleCountdown()
        app.render, app.draw_tv_idle, app.tv_control = Mock(), Mock(), Mock()
        app.tv_control.browsing_session.return_value = object()
        return app

    def test_calls_setup_writes_and_held_buttons_pause_then_restart(self):
        for state in State:
            if state in (State.HOME, State.CONFIRMING, State.CONFIRM_CALLBACK):
                continue
            app = self.app()
            app.tick_tv_idle(0)
            app.model.state = state
            app.tick_tv_idle(29)
            app.tick_tv_idle(1000)
            app.tv_control.restore_browsing.assert_not_called()
            app.model.state = State.HOME
            app.tick_tv_idle(1001)
            app.draw_tv_idle.assert_called_with(None)
            app.tick_tv_idle(1031)
            app.tv_control.restore_browsing.assert_called_once()
        for attribute, value in (('setup_stage', 'server'), ('setup_busy', True), ('keys_down', {'red'})):
            app = self.app()
            app.tick_tv_idle(0)
            setattr(app, attribute, value)
            app.tick_tv_idle(100)
            app.tv_control.restore_browsing.assert_not_called()
        app = self.app()
        app.settings_draft.busy = True
        app.tick_tv_idle(0)
        app.tick_tv_idle(100)
        app.tv_control.restore_browsing.assert_not_called()

    def test_expiry_discards_draft_and_confirmation_without_saving_or_resetting(self):
        for state, setup in ((State.CONFIRMING, None), (State.CONFIRM_CALLBACK, None), (State.HOME, 'reset')):
            app = self.app()
            app.settings_open = True
            app.settings_draft.open(app.model.config)
            app.model.state, app.setup_stage = state, setup
            before = dict(app.model.config)
            app.tick_tv_idle(0)
            app.tick_tv_idle(30)
            self.assertFalse(app.settings_open)
            self.assertEqual(app.model.state, State.HOME)
            self.assertIsNone(app.setup_stage)
            self.assertEqual(app.model.config, before)
            app.tv_control.restore_browsing.assert_called_once()


if __name__ == '__main__':
    unittest.main()
