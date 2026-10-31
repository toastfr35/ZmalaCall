# @test T-HLT-027
# @requirements HLR-TERM-TV-018
# @environment display
# @plan Run the real Tk input/idle controllers and asynchronous TVControl workers against a stateful CEC transport fixture. Begin on another input and in standby, press a button, use the visible UI and expire the idle countdown. Then answer, decline, cancel and fail incoming calls; verify a fresh countdown, delayed bar and deferred restoration for each outcome. Inspect source/power transitions, first-press consumption and all emitted commands.
# @pass The first hidden-view press reveals the terminal without selecting a contact; idle expiry restores the captured input/power; all call endings keep the terminal visible until that countdown expires, without volume/mute commands. Real worker delays run; TV firmware, Samsung network pairing and physical HDMI switching are not qualified by this fixture.

import json
import os
import sys
import threading
import time
import unittest
from unittest.mock import patch

from tests.support.terminal.ui_fixture import terminal_fixture, pump
from zmala_terminal.common.model import State
from zmala_terminal.linux.tv_control import TVControl


@unittest.skipUnless(sys.platform == 'linux' and os.environ.get('DISPLAY'), 'Linux Tk display required')
class TVRoutingUITests(unittest.TestCase):
    def test_button_idle_and_call_restore_from_input_and_standby(self):
        for standby in (False, True):
            with self.subTest(standby=standby), terminal_fixture() as (app, directory):
                device, state_file = directory/'cec', directory/'cec-state.json'
                device.touch()
                state = {'off': standby, 'active_source': '2.0.0.0'}
                commands = []

                def publish():
                    temporary = state_file.with_suffix('.tmp')
                    temporary.write_text(json.dumps(dict(state, device=str(device), updated_at=time.time())))
                    temporary.replace(state_file)

                def transport(_tv, *arguments):
                    commands.append((arguments, threading.get_ident()))
                    if arguments == ('--physical-address',):
                        return '1.0.0.0'
                    if arguments == ('--logical-address',):
                        return '4'
                    if '--give-device-power-status' in arguments:
                        return 'pwr-state: standby (1)' if state['off'] else 'pwr-state: on (0)'
                    if '--image-view-on' in arguments:
                        state['off'] = False
                    if '--standby' in arguments:
                        state['off'] = True
                    if '--active-source' in arguments or '--set-stream-path' in arguments:
                        state['active_source'] = arguments[-1].split('=')[1]
                    publish()
                    return ''

                publish()
                app.tv_control = TVControl(device=str(device), state_file=state_file)
                app.tv_control.command = 'fixture-cec-ctl'
                tv = app.tv_control
                with patch.object(TVControl, '_run', transport):
                    try:
                        before = app.model.index
                        app.keypress('right'); app.keyrelease('right')
                        pump(app, lambda: tv.browsing_session() is not None and not tv._input_pending, timeout=8)
                        self.assertEqual(app.model.index, before)
                        self.assertEqual(state, {'off': False, 'active_source': '1.0.0.0'})
                        app.keypress('right'); app.keyrelease('right')
                        self.assertNotEqual(app.model.index, before)
                        start = time.monotonic()
                        app.tick_tv_idle(start)
                        self.assertEqual(app.tv_idle_pixels, 0)
                        app.tick_tv_idle(start+11)
                        self.assertGreater(app.tv_idle_pixels, 0)
                        app.input_activity()
                        app.tick_tv_idle(start+12)
                        self.assertEqual(app.tv_idle_pixels, 0, 'Any new input hides/restarts the bar')
                        app.tick_tv_idle(start+43)
                        pump(app, lambda: tv._restore_pending is None, timeout=5)
                        self.assertEqual(state, {'off': standby, 'active_source': '2.0.0.0'})

                        for ending in ('answered', 'declined', 'cancelled', 'failed'):
                            publish()
                            app.call_event(88, 1, 'alice', 'family.test')
                            pump(app, lambda: tv._ready.is_set(), timeout=8)
                            self.assertEqual(app.model.state, State.RINGING)
                            self.assertEqual(state, {'off': False, 'active_source': '1.0.0.0'})
                            if ending == 'answered':
                                app.call_event(88, 8, 'alice', 'family.test')
                                self.assertEqual(app.model.state, State.IN_CALL)
                            elif ending == 'declined':
                                app.action(app.model.button('red'))
                            app.call_event(88, 13 if ending == 'failed' else 14, 'alice', 'family.test')
                            pump(app, lambda: tv._previous is None and tv._ready.is_set(), timeout=5)
                            self.assertEqual(state, {'off': False, 'active_source': '1.0.0.0'}, ending)
                            self.assertIsNotNone(tv.browsing_session())
                            start = time.monotonic()
                            app.tick_tv_idle(start)
                            self.assertEqual(app.tv_idle_pixels, 0)
                            app.tick_tv_idle(start+11)
                            self.assertGreater(app.tv_idle_pixels, 0)
                            self.assertEqual(state, {'off': False, 'active_source': '1.0.0.0'}, ending)
                            app.tick_tv_idle(start+31)
                            pump(app, lambda: tv._restore_pending is None, timeout=5)
                            self.assertEqual(state, {'off': standby, 'active_source': '2.0.0.0'}, ending)
                        self.assertTrue(all(thread != threading.get_ident() for _, thread in commands))
                        flattened = ' '.join(' '.join(args) for args, _ in commands)
                        for forbidden in ('volume', 'mute', 'user-control', 'system-audio'):
                            self.assertNotIn(forbidden, flattened)
                    finally:
                        tv.close()
                        # All transport work must be done before restoring the real driver.
                        with tv._lock:
                            pass


if __name__ == '__main__':
    unittest.main()
