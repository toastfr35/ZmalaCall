# @test T-HLT-025
# @requirements HLR-TERM-POWER-008, HLR-TERM-POWER-009
# @environment display
# @plan Run USB and fan worker threads alongside the real Tk terminal. Substitute only privileged USB commands, media enumeration and I2C writes. Age the idle timestamp, vary battery/activity, block wake, reject native refresh and inject helper failure. Drive a button and incoming call through application controllers. Check native refresh thread ownership and fan transitions.
# @pass USB sleeps only after eligible idle time, user/call activity requests wake immediately, and readiness waits for enumeration plus native refresh. Slow/failing hardware work does not block navigation; fan runs during calls and stops afterwards. Physical C20 readiness, hub switching and thermal performance remain hardware acceptance tests.

import os
import sys
import threading
import time
import unittest
from unittest.mock import patch

from tests.support.terminal.ui_fixture import terminal_fixture, pump
from zmala_terminal.common.model import State
from zmala_terminal.linux import usb_power, argon_fan


@unittest.skipUnless(sys.platform == 'linux' and os.environ.get('DISPLAY'), 'Linux Tk display required')
class PeripheralWorkerTests(unittest.TestCase):
    def test_idle_wake_call_and_failed_refresh(self):
        commands = []
        gate, entered = threading.Event(), threading.Event()
        gate.set()
        fail_next = []
        ui_thread = threading.get_ident()

        def helper(_power, action):
            commands.append((action, threading.get_ident()))
            if action == 'on':
                entered.set()
                if not gate.wait(3):
                    raise TimeoutError('test wake gate')
            if fail_next:
                fail_next.pop()
                raise OSError('fixture USB helper failure')

        with terminal_fixture() as (app, directory), \
                patch.dict(os.environ, {'ZMALA_USB_POWER': '1'}), \
                patch.object(usb_power.UsbPower, 'command', helper), \
                patch.object(usb_power, 'media_present', return_value=True), \
                patch('zmala_terminal.linux.c20_volume.status', return_value=(0, 0, False)):
            app.usb_power.close()
            power = app.usb_power = usb_power.UsbPower(directory)

            def idle(battery, seconds=301):
                power.update(False, battery)
                with power.lock:
                    power.last_use = time.monotonic() - seconds
                power.changed.set()

            try:
                pump(app, lambda: power.state == 'on')
                self.assertFalse(power.ready)
                refresh_threads = []
                app.engine.refresh_usb_devices.side_effect = lambda: refresh_threads.append(threading.get_ident()) or False
                power.refresh(app.engine)
                self.assertFalse(power.ready)
                app.engine.refresh_usb_devices.side_effect = lambda: refresh_threads.append(threading.get_ident()) or True
                power.refresh(app.engine)
                self.assertTrue(power.ready)
                for battery, seconds in [(24, 301), (None, 301), (100, 299)]:
                    idle(battery, seconds)
                    deadline = time.monotonic() + .25
                    pump(app, lambda: time.monotonic() >= deadline)
                    self.assertEqual(power.state, 'on')
                idle(25)
                pump(app, lambda: power.state == 'off')
                self.assertIs(power.power_state, False)

                # A slow privileged wake must not hold the UI thread.
                entered.clear(); gate.clear()
                before = app.model.index
                app.keypress('right')
                app.keyrelease('right')
                pump(app, entered.is_set)
                self.assertNotEqual(app.model.index, before)
                self.assertEqual(power.state, 'switching')
                self.assertFalse(power.ready)
                gate.set()
                pump(app, lambda: power.state == 'on')
                self.assertFalse(power.ready)
                power.refresh(app.engine)
                self.assertTrue(power.ready)
                self.assertEqual(set(refresh_threads), {ui_thread})
                self.assertTrue(all(thread != ui_thread for _, thread in commands))

                idle(75)
                pump(app, lambda: power.state == 'off')
                fail_next.append(True)
                app.call_event(123, 1, 'alice', 'family.test')
                pump(app, lambda: power.state == 'error')
                self.assertEqual(app.model.state, State.RINGING)
                self.assertFalse(power.ready)
                # Fresh physical input bypasses the helper's ten-second retry delay.
                app.input_activity()
                pump(app, lambda: power.state == 'on')
                power.refresh(app.engine)
                self.assertTrue(power.ready)
                self.assertEqual(app.model.state, State.RINGING)
            finally:
                gate.set()
                power.close()
                power.worker.join(3)
                self.assertFalse(power.worker.is_alive())
                self.assertEqual(commands[-1][0], 'on', 'Worker teardown must restore supply')

    def test_fan_call_state_and_temperature_without_blocking_ui(self):
        writes = []
        ui_thread = threading.get_ident()
        with terminal_fixture() as (app, _), \
                patch.dict(os.environ, {'ZMALA_ARGON_ONE_FAN': '1'}), \
                patch.object(argon_fan, 'temperature', return_value=40) as temperature, \
                patch.object(argon_fan, 'write_speed', side_effect=lambda speed:
                             writes.append((speed, threading.get_ident()))):
            app.case_fan.close()
            fan = app.case_fan = argon_fan.ArgonFan()
            try:
                pump(app, lambda: bool(writes))
                self.assertEqual(writes[-1][0], 0)
                app.tick()
                app.call_event(10, 1, 'alice', 'family.test')
                app.call_event(10, 8, 'alice', 'family.test')
                pump(app, lambda: writes[-1][0] == 55)
                temperature.return_value = 70
                fan.changed.set()
                pump(app, lambda: writes[-1][0] == 100)
                app.call_event(10, 14, 'alice', 'family.test')
                pump(app, lambda: writes[-1][0] == 0)
                self.assertTrue(all(thread != ui_thread for _, thread in writes))
            finally:
                fan.close()
                fan.worker.join(3)
                self.assertFalse(fan.worker.is_alive())


if __name__ == '__main__':
    unittest.main()
