# @test T-HLT-023
# @requirements HLR-TERM-REMOTE-011, HLR-TERM-REMOTE-012, HLR-TERM-NAV-002, HLR-TERM-AUDIO-002
# @environment display
# @plan Feed measured Presenter reports through OS pipes registered with real Tk file handlers. Exercise the real input controller, confirmation model and volume overlay/mixer worker. Check duplicate down suppression, cancellation, disconnected input, charging/battery state and relative volume. Replace only device discovery, Bluetooth status and the external mixer process. Check that all mixer commands address C20 playback only.
# @pass One held press cannot confirm a call; red cancels; only held-pointer motion changes volume and the overlay disappears after release. Disconnect releases held buttons and exposes missing input. These scenarios do not qualify radio pairing, physical battery telemetry or acoustic output.

import os
import sys
import threading
import tkinter as tk
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from tests.support.terminal.ui_fixture import terminal_fixture, pump
from zmala_terminal.common.input_control import InputControl
from zmala_terminal.common.model import State
from zmala_terminal.linux import c20_volume
from zmala_terminal.linux.presenter_input import PresenterInput


@unittest.skipUnless(sys.platform == 'linux' and os.environ.get('DISPLAY'), 'Linux Tk display required')
class RemoteUITests(unittest.TestCase):
    def test_hid_confirmation_volume_and_disconnect(self):
        commands = []
        main_thread = threading.get_ident()

        def mixer(command, **kwargs):
            commands.append((command, threading.get_ident()))

        health = SimpleNamespace(battery=77, charger_connected=True, state='disconnected', close=lambda: None)
        with terminal_fixture() as (app, _), \
                patch.object(PresenterInput, 'discover'), \
                patch('zmala_terminal.linux.presenter_input.RemoteHealth', return_value=health), \
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
                os.write(writers[0], bytes.fromhex(value))
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
                self.assertEqual(app.callback_requests, [])

                c20_volume.request(50)
                pump(app, lambda: c20_volume.status()[1] == 50 and c20_volume._worker is None)
                report('03000000c0ff00000000')  # Motion without middle held.
                self.assertEqual(c20_volume.status()[0], 50)
                report('043d010000000000')
                report('03000000c0ff00000000')  # -64 -> +2%.
                pump(app, lambda: c20_volume.status()[1] == 52 and c20_volume._worker is None)
                self.assertTrue(app.volume_control.canvas.winfo_ismapped())
                self.assertIn('52%', [app.volume_control.canvas.itemcget(i, 'text')
                              for i in app.volume_control.canvas.find_all()
                              if app.volume_control.canvas.type(i) == 'text'])
                report('043d000000000000')
                report('03000000c0ff00000000')
                self.assertEqual(app.volume_control.gesture.percent, 52)
                pump(app, lambda: not app.volume_control.canvas.winfo_ismapped(), timeout=3)
                self.assertTrue(commands)
                for command, thread in commands:
                    self.assertEqual(command[:6], ['amixer', '-q', '-c', 'C20', 'sset', 'PCM'])
                    self.assertEqual(len(command), 7)
                    self.assertNotEqual(thread, main_thread)

                # A disappearing raw device releases both the gesture and held keys.
                report('043d010000000000')
                report('043f010000000000')
                os.close(writers.pop(0))
                pump(app, lambda: not presenter.raw_fds)
                self.assertFalse(app.volume_control.gesture.held)
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
