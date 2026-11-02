# @test T-HLT-023
# @requirements HLR-TERM-REMOTE-011, HLR-TERM-REMOTE-012, HLR-TERM-NAV-002, HLR-TERM-AUDIO-002
# @environment display
# @plan Feed measured Presenter reports through OS pipes registered with real Tk file handlers. Exercise the real input controller, confirmation model and volume overlay/mixer worker. Space deliberate confirmation clicks beyond the 80 ms debounce; keep duplicate held reports immediate. Check duplicate down suppression, cancellation, disconnected input, charging/battery state and a compact horizontal volume overlay in 5-percent steps. Send three released carousel presses in each direction during animation, verify every selection and the settled center, then confirm the final target without dialing. Keep keyboard releases queued until after later arrows; verify distinct event timestamps count clicks and equal timestamps suppress autorepeat. Also render video beneath the overlay during a simulated established call, assert most video remains uncovered, block physical call actions, preserve programmatic cancellation and expired outgoing-call deadlines and preempt it on incoming ringing. Replace remote-device discovery, ALSA card discovery, Bluetooth status, button audio and the external mixer process. Check that all mixer commands address C20 playback only.
# @pass Three distinct arrows move three slots despite queued releases, while held/autorepeated downs add no movement. One held press cannot confirm a call; red cancels; middle toggles the volume overlay, arrows change only volume, movement is ignored and the overlay closes on red or the next middle click. Disconnect releases held buttons and exposes missing input. These scenarios do not qualify radio pairing, physical battery telemetry or acoustic output.

import os
import sys
import threading
import time
import tkinter as tk
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from tests.support.terminal.ui_fixture import terminal_fixture, pump
from zmala_terminal.common.input_control import InputControl
from zmala_terminal.common.model import State
from zmala_terminal.linux import c20_volume
from zmala_terminal.linux.presenter_input import PresenterInput, button_report


@unittest.skipUnless(sys.platform == 'linux' and os.environ.get('DISPLAY'), 'Linux Tk display required')
class RemoteUITests(unittest.TestCase):
    def test_fast_keyboard_arrows_before_idle_releases(self):
        with terminal_fixture() as (app, _):
            for button,direction in (('right',1),('left',-1)):
                before=app.model.index
                for n in range(3):
                    app.keypress(button,1000+n*40)
                    app.queue_keyrelease(button,1020+n*40)
                    self.assertEqual(app.model.index,(before+(n+1)*direction)%len(app.model.contacts))
                app.keypress(button,1100)  # Same as the last release: autorepeat.
                self.assertEqual(app.model.index,(before+3*direction)%len(app.model.contacts))
                app.keyrelease(button)
            app.engine.dial.assert_not_called()

    def test_rapid_carousel_navigation_and_confirmation(self):
        with terminal_fixture() as (app, _):
            settings = app.model.config.copy()
            sample = settings['contacts'][0]
            settings['contacts'] = [sample | {'id': str(i), 'name': f'Person {i}'} for i in range(5)]
            app.model.configure(settings)
            for button, direction in (('right', 1), ('left', -1)):
                before = app.model.index
                for n in range(3):
                    app.keypress(button)
                    app.keypress(button)  # Held down still counts only once.
                    app.keyrelease(button)
                    self.assertEqual(app.model.index, (before+(n+1)*direction)%5)
                self.assertIsNotNone(app.carousel_motion)
            selected = app.model.selected
            motion = app.carousel_motion
            center = next(person for person, slot in motion.frames(motion.started+motion.duration) if slot == 0)
            self.assertEqual(center['id'], selected['id'])
            app.press('green')
            pump(app)
            self.assertEqual(app.model.state, State.CONFIRMING)
            self.assertEqual(app.model.contact['id'], selected['id'])
            self.assertIsNone(app.carousel_motion)
            app.engine.dial.assert_not_called()

    def test_hid_confirmation_volume_and_disconnect(self):
        commands = []
        main_thread = threading.get_ident()

        def mixer(command, **kwargs):
            commands.append((command, threading.get_ident()))

        health = SimpleNamespace(battery=77, charger_connected=True, state='disconnected', close=lambda: None)
        with terminal_fixture() as (app, _), \
                patch('zmala_terminal.linux.action_sounds.ActionSounds'), \
                patch.object(PresenterInput, 'discover'), \
                patch('zmala_terminal.linux.presenter_input.RemoteHealth', return_value=health), \
                patch.object(c20_volume, 'audio_card', return_value='C20'), \
                patch.object(c20_volume.subprocess, 'run', side_effect=mixer):
            app.volume_control.close()
            InputControl.bind_inputs(app)
            presenter = app.presenter_input
            readers, writers = [], []
            for raw in (True, False):
                reader, writer = os.pipe()
                readers.append(reader); writers.append(writer)
                os.set_blocking(reader, False)
                presenter.devices[f'fixture-{reader}'] = reader
                if raw:
                    presenter.raw_fds.add(reader)
                app.root.createfilehandler(reader, tk.READABLE, presenter.read)

            def report(value):
                data = bytes.fromhex(value)
                button = button_report(data)
                if button and button[1] and button[0] not in app.keys_down:
                    # Fast CI must not turn a deliberate later click into bounce.
                    pump(app, lambda: time.monotonic()-app.last_key.get(button[0],0) > .08)
                os.write(writers[0], data)
                # One report per read, as on the hidraw device.
                pump(app, lambda: True)

            try:
                self.assertEqual(presenter.status, 'connected')
                self.assertEqual(presenter.battery, 77)
                self.assertTrue(presenter.charger_connected)
                health.charger_connected = False
                self.assertFalse(presenter.charger_connected)
                report('043f010000000000')
                self.assertEqual(app.model.state, State.CONFIRMING)
                report('043f010000000000')
                self.assertEqual(app.model.state, State.CONFIRMING)
                app.engine.dial.assert_not_called()
                report('043f000000000000')
                report('043e010000000000')
                self.assertEqual(app.model.state, State.HOME)
                report('043e000000000000')
                app.model.selected['online'] = False
                app.last_key.clear()
                report('043f010000000000')
                self.assertEqual(app.model.state, State.CONFIRM_CALLBACK)
                report('043f000000000000')
                app.last_key.clear()
                report('043e010000000000')
                report('043e000000000000')
                self.assertEqual(app.model.state, State.HOME)
                self.assertEqual(app.callbacks.requests, [])

                c20_volume.request(50)
                pump(app, lambda: c20_volume.status()[1] == 50 and c20_volume._worker is None)
                report('03000000c0ff00000000')
                self.assertEqual(c20_volume.status()[0], 50)
                selected=app.model.selected['id']
                report('043d010000000000')
                report('043d010000000000')  # Repeated down must not close it.
                report('043d000000000000')
                self.assertTrue(app.volume_control.active)
                report('03000000c0ff00000000')  # Movement is ignored.
                self.assertEqual(app.volume_control.level.percent,50)
                app.keypress('right');app.keypress('right')
                self.assertEqual(app.volume_control.level.percent,55)
                app.keyrelease('right')
                pump(app, lambda: c20_volume.status()[1] == 55 and c20_volume._worker is None)
                self.assertEqual(app.model.selected['id'],selected)
                self.assertEqual(app.model.state,State.HOME)
                self.assertTrue(app.volume_control.canvas.winfo_ismapped())
                self.assertEqual(app.volume_control.canvas.itemcget('volume-level','text'),'55%')
                track=app.volume_control.canvas.coords('volume-track')
                self.assertGreater(track[2]-track[0],track[3]-track[1])
                report('043e010000000000');report('043e000000000000')
                self.assertIsNone(app.settings_hold.started)
                self.assertFalse(app.volume_control.active)
                self.assertFalse(app.volume_control.canvas.winfo_ismapped())
                self.assertTrue(commands)
                for command, thread in commands:
                    self.assertEqual(command[:6], ['amixer', '-q', '-c', 'C20', 'sset', 'PCM'])
                    self.assertEqual(len(command), 7)
                    self.assertNotEqual(thread, main_thread)

                # The page also preserves an established call and yields to ringing.
                app.model.state=State.IN_CALL
                app.model.contact=app.model.selected
                app.render();app.root.update_idletasks()
                app.engine.hangup.reset_mock()
                report('043d010000000000');report('043d000000000000')
                self.assertTrue(app.video.winfo_ismapped())
                overlay=app.volume_control.canvas
                self.assertLess(overlay.winfo_height(),app.video.winfo_height()/3)
                self.assertLess(overlay.winfo_width(),app.root.winfo_width())
                self.assertGreater(overlay.winfo_y(),app.video.winfo_rooty()-app.root.winfo_rooty())
                app.keypress('left');app.keyrelease('left')
                report('043f010000000000');report('043f000000000000')
                report('043e010000000000');report('043e000000000000')
                self.assertEqual(app.model.state,State.IN_CALL)
                app.engine.hangup.assert_not_called()
                # A logical timeout/revocation remains effective despite the overlay.
                app.press('red')
                self.assertNotEqual(app.model.state,State.IN_CALL)
                app.engine.end.assert_called()
                pump(app,lambda:not app.volume_control.active)
                report('043d010000000000');report('043d000000000000')
                app.model.state=State.RINGING
                app.model.contact=app.model.selected
                pump(app,lambda:not app.volume_control.active)
                self.assertFalse(app.volume_control.canvas.winfo_ismapped())
                self.assertEqual(app.model.state,State.RINGING)
                app.model.ended()
                # An expired outgoing call must still end with volume open.
                app.model.state=State.CALLING;app.model.contact=app.model.selected
                app.model.outgoing_attempt=True;app.engine.call=99
                report('043d010000000000');report('043d000000000000')
                self.assertTrue(app.volume_control.active)
                app.outgoing_deadline=0.1
                app.update_timers(time.monotonic())
                self.assertEqual(app.model.state,State.CONFIRM_CALLBACK)
                pump(app,lambda:not app.volume_control.active)
                app.press('red')
                self.assertEqual(app.model.state,State.HOME)

                # A disappearing raw device releases held buttons.
                report('043d010000000000')
                report('043f010000000000')
                os.close(writers.pop(0))
                pump(app, lambda: not presenter.raw_fds)
                self.assertFalse(app.volume_control.pressed)
                self.assertNotIn('green', app.keys_down)
                self.assertEqual(presenter.status, 'input_unavailable')
                os.close(writers.pop())
                pump(app, lambda: not presenter.connected)
                self.assertEqual(presenter.status, 'disconnected')
                self.assertIsNone(presenter.battery)
                self.assertIsNone(presenter.charger_connected)
            finally:
                for writer in writers:
                    os.close(writer)
                presenter.close()
                # Keep the process substitution until the real mixer worker has exited.
                pump(app, lambda: c20_volume._worker is None)


if __name__ == '__main__':
    unittest.main()
