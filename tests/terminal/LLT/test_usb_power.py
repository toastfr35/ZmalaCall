# @test T-LLT-037
# @requirements LLR-TERM-POWER-012, LLR-TERM-POWER-013, LLR-TERM-POWER-014, LLR-TERM-POWER-015, LLR-TERM-POWER-016, LLR-TERM-POWER-017
# @environment portable
# @plan Control time, remote battery, hub status, input and call events with mocked USB helpers; assert five-minute inactivity and battery boundaries, immediate wake requests, media readiness gating, bounded retries and truthful power indication. Inject applied-volume status and worker time to verify ringing only after nonzero mixer convergence, atomic power telemetry, ringer termination escalation and unconditional shutdown power restoration.
# @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

"""Boundary, wake-race, stale-input and cancellation tests without powering USB."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from zmala_terminal.linux.usb_power import UsbPower, should_power_off
from zmala_terminal.common.call_control import CallControl
from zmala_terminal.common.model import State
from zmala_terminal.common.engine import Engine
from zmala_terminal.common.input_control import InputControl
from zmala_terminal.common.management import ManagementLoop


class UsbPowerTests(unittest.TestCase):
    def test_power_worker_status_and_ringer_wait_for_applied_nonzero_volume(self):
        import zmala_terminal.linux.usb_power as module
        power = self.controller()
        power.state, power.powered, power.ringing = 'on', True, True
        power.revision = power.refreshed = 2
        power.command = Mock()
        samples = iter([(50, 20, False), (0, 0, False), (40, 40, False), (40, 40, True)])
        clock = [1000]
        snapshots = []
        with tempfile.TemporaryDirectory() as folder, patch.dict('os.environ', {'ZMALA_RUNTIME_DIR': folder}), \
                patch.object(module.time, 'monotonic', side_effect=lambda: clock[0]), \
                patch('zmala_terminal.linux.c20_volume.status', side_effect=lambda: next(samples)), \
                patch.object(module.subprocess, 'Popen') as popen:
            process = popen.return_value
            process.poll.return_value = None
            def wait(_):
                snapshots.append(popen.call_count)
                clock[0] += 5
                if len(snapshots) == 4:
                    power.stopped = True
            power.changed = Mock(wait=Mock(side_effect=wait))
            power.run()
            self.assertEqual(snapshots, [0, 0, 1, 1])
            self.assertIn('plughw:C20,0', popen.call_args.args[0])
            self.assertEqual(process.terminate.call_count, 1)
            import json
            state = json.loads((Path(folder)/'usb-power.json').read_text())
            self.assertEqual((state['state'], state['powered']), ('on', True))
            self.assertFalse((Path(folder)/'usb-power.tmp').exists())
        power.command.assert_called_once_with('on')

    def test_ringer_stop_timeout_kills_and_worker_shutdown_restores_power(self):
        import zmala_terminal.linux.usb_power as module
        power = self.controller()
        process = Mock()
        process.poll.return_value = None
        process.wait.side_effect = module.subprocess.TimeoutExpired('aplay', .3)
        power.ringer = process
        power.close()
        process.terminate.assert_called_once()
        process.kill.assert_called_once()
        self.assertIsNone(power.ringer)
        self.assertTrue(power.changed.is_set())
        with patch.object(power, 'command', side_effect=OSError('hub gone')) as command, \
                patch.object(module.logging, 'exception') as logged:
            power.run()
        command.assert_called_once_with('on')
        logged.assert_called_once()
        with patch.object(module.subprocess, 'run') as run:
            power.command('on')
        self.assertEqual(run.call_args.args[0], ['sudo', '-n', module.HELPER, 'on'])
        self.assertEqual(run.call_args.kwargs['timeout'], 30)

    def test_media_reenumeration_requires_c20_video_and_alsa_and_handles_disconnect(self):
        import zmala_terminal.linux.usb_power as module
        video = Mock()
        video.resolve.return_value = '/sys/devices/usb1/1-1.2/video4linux/video0'
        video.__truediv__ = Mock(return_value=SimpleNamespace(read_text=lambda: 'Nuroum C20'))
        audio = Mock()
        audio.read_text.return_value = 'C20\n'
        with patch.object(module, 'Path') as path:
            path.side_effect = lambda name: SimpleNamespace(glob=lambda pattern: [video] if 'video' in name else [audio])
            self.assertTrue(module.media_present())
            audio.read_text.return_value = 'HDMI'
            self.assertFalse(module.media_present())
            audio.read_text.side_effect = OSError('gone')
            self.assertFalse(module.media_present())
        with patch.object(module.sys, 'platform', 'linux'), patch.dict('os.environ', {'ZMALA_USB_POWER': '1'}), \
                patch.object(module.threading, 'Thread') as thread:
            enabled = module.UsbPower(Path('.'))
        self.assertEqual(enabled.state, 'starting')
        thread.return_value.start.assert_called_once()

    def test_exact_idle_and_battery_boundaries(self):
        self.assertFalse(should_power_off(299.9, 0, False, 100))
        self.assertTrue(should_power_off(300, 0, False, 25))
        for battery in (None, 24, 0, True, 101, '100'):
            self.assertFalse(should_power_off(900, 0, False, battery))
        self.assertFalse(should_power_off(900, 0, True, 100))

    def controller(self):
        with patch.dict('os.environ', {}, clear=True):
            power = UsbPower(Path('.'))
        power.enabled = True
        return power

    def test_every_press_wakes_before_setup_can_consume_it(self):
        app = InputControl()
        app.usb_power = self.controller()
        app.remote_setup_blocked = lambda: True
        app.setup_stage = 'remote'
        for action in (lambda: app.keypress('red'), lambda: app.pointer_button(True), app.volume_activity):
            app.usb_power.active = False
            app.usb_power.changed.clear()
            with patch('time.monotonic', return_value=1000):
                action()
            self.assertEqual(app.usb_power.last_use, 1000)
            self.assertTrue(app.usb_power.changed.is_set())
            self.assertFalse(should_power_off(1299, app.usb_power.last_use, False, 95))

    def test_idle_starts_after_activity_ends(self):
        power = self.controller()
        with patch('time.monotonic', return_value=1000):
            power.update(False, 95)
        self.assertEqual(power.last_use, 1000)
        with patch('time.monotonic', return_value=1100):
            power.update(False, 95)
        self.assertEqual(power.last_use, 1000)

    def test_held_button_inhibits_power_off(self):
        app = ManagementLoop()
        app.usb_power = Mock(enabled=True)
        app.setup_stage = app.scanner = app.engine = None
        app.model = Mock(state=State.HOME)
        app.settings_open = False
        app.keys_down = {'red'}
        app.presenter_input = Mock(battery=95)
        app.tick_usb()
        app.usb_power.update.assert_called_once_with(True, 95, False)

    def test_incoming_call_wakes_before_tv_work(self):
        app = CallControl()
        app.setup_stage = None
        app.model, app.engine, app.root = Mock(), Mock(), Mock()
        app.render = Mock()
        app.usb_power = self.controller()
        app.tv_control = Mock()
        def check_woken():
            self.assertEqual(app.usb_power.wake_serial, 1)
            self.assertTrue(app.usb_power.changed.is_set())
        app.tv_control.wake.side_effect = check_woken
        app.call_event(123, 1, 'term1', 'example.test')
        app.tv_control.wake.assert_called_once()

    def test_button_during_failed_off_restores_without_backoff(self):
        power = self.controller()
        power.active, power.battery = False, 95
        power.last_use, power.updated = 0, 1000
        power.state = 'on'
        actions = []
        def command(action):
            actions.append(action)
            if action == 'off':
                power.require(urgent=True)
                raise RuntimeError('off interrupted')
            power.stopped = True
        power.command = command
        with patch('time.monotonic', return_value=1000), patch('zmala_terminal.linux.usb_power.media_present', return_value=True):
            power.run()
        self.assertEqual(actions[:2], ['off', 'on'])
        self.assertTrue(power.power_state)

    def test_confirmed_supply_is_independent_of_missing_camera(self):
        power = self.controller()
        power.state = 'off'
        def command(action):
            power.stopped = True
        power.command = command
        with patch('zmala_terminal.linux.usb_power.media_present', return_value=False):
            power.run()
        self.assertTrue(power.power_state)
        self.assertFalse(power.ready)

    def test_wake_is_not_ready_until_native_devices_refreshed(self):
        power = self.controller()
        power.state, power.revision = 'on', 1
        self.assertFalse(power.require())
        engine = Mock()
        power.refresh(engine)
        engine.refresh_usb_devices.assert_called_once()
        self.assertTrue(power.ready)

    def test_off_transition_cannot_be_treated_as_ready(self):
        power = self.controller()
        power.state = 'switching'
        self.assertFalse(power.require())
        self.assertTrue(power.active)

    def test_running_media_defers_refresh(self):
        power = self.controller()
        power.state, power.revision = 'on', 1
        engine = Mock()
        engine.refresh_usb_devices.return_value = False
        power.refresh(engine)
        self.assertFalse(power.ready)

    def test_udev_settling_does_not_break_ui_tick_or_spin(self):
        power = self.controller()
        power.state, power.revision = 'on', 1
        engine = Mock()
        engine.refresh_usb_devices.side_effect = [RuntimeError('C20 unavailable'), None]
        with patch('zmala_terminal.linux.usb_power.time.monotonic', return_value=10):
            power.refresh(engine)
            power.refresh(engine)
        self.assertFalse(power.ready)
        engine.refresh_usb_devices.assert_called_once()
        with patch('zmala_terminal.linux.usb_power.time.monotonic', return_value=11):
            power.refresh(engine)
        self.assertTrue(power.ready)

    def test_stalled_ui_restores_power(self):
        power = self.controller()
        power.active, power.battery = False, 100
        power.updated = power.last_use = 0
        power.state = 'off'
        actions = []
        def command(action):
            actions.append(action)
            power.stopped = True
        power.command = command
        with patch('zmala_terminal.linux.usb_power.media_present', return_value=True):
            power.run()
        self.assertTrue(actions)
        self.assertEqual(set(actions), {'on'})

    def test_cancelled_answer_does_not_run_after_wake(self):
        app = CallControl()
        app.engine, app.root, app.model = Mock(), Mock(), Mock()
        app.usb_media_ready, app.action = Mock(return_value=False), Mock()
        app.engine.call = 123
        app.generation = 5
        app.closed = False
        app.model.state = State.CONNECTING
        app.usb_media_ready.return_value = False
        CallControl.action(app, 'answer')
        callback = app.root.after.call_args.args[1]
        app.model.state = State.HOME
        callback()
        app.engine.answer.assert_not_called()
        app.action.assert_not_called()

    def test_disabled_on_desktop(self):
        with patch.dict('os.environ', {}, clear=True):
            power = UsbPower(Path('.'))
        self.assertFalse(power.enabled)
        self.assertTrue(power.require())

    def test_zero_volume_mutes_and_remote_increase_unmutes(self):
        engine = Engine.__new__(Engine)
        engine.core = 123
        engine.core_set_playback_gain_db = Mock()
        with patch('zmala_terminal.common.engine.WINDOWS', False), patch('zmala_terminal.linux.c20_volume.status',
                side_effect=[(0, 0, False), (0, 0, False), (2, 2, False)]):
            for _ in range(3):
                engine.sync_speaker_mute()
        self.assertEqual([call.args for call in engine.core_set_playback_gain_db.call_args_list],
                         [(123, -120), (123, 0)])


class HelperSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[3] / 'build_tools/linux/usb-power.py'
        spec = importlib.util.spec_from_file_location('usb_helper', path)
        cls.helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.helper)

    def test_helper_inventory_checks_board_hub_topology_and_excludes_usb_hubs(self):
        h = self.helper
        with tempfile.TemporaryDirectory() as directory, patch.object(h, 'USB', Path(directory)), \
                patch.object(h.Path, 'read_bytes', return_value=b'Raspberry Pi 4 Model B Rev 1.5'):
            root = Path(directory)
            for name, vendor, product, kind in [('1-1','2109','3431','09'), ('usb2','1d6b','0003','09'), ('1-1.2','0525','a4ad','ef')]:
                device = root/name; device.mkdir()
                for field, value in [('idVendor',vendor),('idProduct',product),('bDeviceClass',kind)]:
                    (device/field).write_text(value)
            (root/'interface').mkdir()
            h.validate_board()
            self.assertEqual(h.devices(), [(root/'1-1.2', ('0525','a4ad'))])
            (root/'usb2/idProduct').write_text('other')
            with self.assertRaisesRegex(RuntimeError, 'topology'):
                h.validate_board()
        with patch.object(h.Path, 'read_bytes', return_value=b'Raspberry Pi 3 Model B'):
            with self.assertRaisesRegex(RuntimeError, 'Pi 4'):
                h.validate_board()
        with patch.object(h.subprocess, 'run', return_value='ok') as run:
            self.assertEqual(h.run('unit-command'), 'ok')
            run.assert_called_once_with(('unit-command',), check=True, capture_output=True, text=True, timeout=12)

    def test_helper_on_needs_no_camera_and_off_requires_exactly_one_idle_camera(self):
        h = self.helper
        with patch.object(h, 'validate_board'), patch.object(h, 'devices', return_value=[]), patch.object(h, 'switch') as switch:
            h.power('on'); switch.assert_called_once_with('on')
            with self.assertRaisesRegex(RuntimeError, 'exactly one'):
                h.power('off')
        with tempfile.TemporaryDirectory() as directory, patch.object(h, 'validate_board'), \
                patch.object(h.Path, 'glob', return_value=[Path('/dev/video0')]), \
                patch.object(h.subprocess, 'run', return_value=Mock(returncode=1)) as opened, patch.object(h, 'switch') as switch:
            camera = Path(directory); (camera/'authorized').write_text('1')
            def check_off(action):
                self.assertEqual(action, 'off')
                self.assertEqual((camera/'authorized').read_text(), '0')
            switch.side_effect = check_off
            with patch.object(h, 'devices', return_value=[(camera, ('0525','a4ad'))]):
                h.power('off')
            switch.assert_called_once_with('off')
            self.assertEqual(opened.call_args.kwargs['timeout'], 5)

    def test_successful_command_with_unchanged_ports_is_rejected(self):
        output = '\n'.join(f'  Port {i}: 0000 off' for i in range(1, 5))
        with patch.object(self.helper, 'run', return_value=Mock(stdout=output)):
            with self.assertRaisesRegex(RuntimeError, 'did not confirm'):
                self.helper.switch('on')

    def test_both_hubs_confirm_power(self):
        for action, state in [('on', '0507 power highspeed enable connect'), ('off', '0080 off')]:
            output = '\n'.join(f'  Port {i}: {state}' for i in range(1, 5))
            with patch.object(self.helper, 'run', return_value=Mock(stdout=output)) as run:
                self.helper.switch(action)
                self.assertEqual(run.call_count, 4)

    def test_unknown_peripheral_blocks_shared_power_off(self):
        h = self.helper
        with patch.object(h, 'validate_board'), patch.object(h, 'devices', return_value=[(Path('/fake'), ('1234','5678'))]), patch.object(h, 'switch') as switch:
            with self.assertRaisesRegex(RuntimeError, 'Other USB'):
                h.power('off')
            switch.assert_not_called()

    def test_failed_power_off_restores_supply_and_authorization(self):
        h = self.helper
        with tempfile.TemporaryDirectory() as tmp:
            camera = Path(tmp)
            (camera / 'authorized').write_text('1')
            with patch.object(h, 'validate_board'), patch.object(h, 'devices', return_value=[(camera, ('0525','a4ad'))]), patch.object(h.Path, 'glob', return_value=[]), patch.object(h, 'switch', side_effect=[OSError('hub'), None]) as switch:
                with self.assertRaises(OSError):
                    h.power('off')
                self.assertEqual([c.args[0] for c in switch.call_args_list], ['off', 'on'])
                self.assertEqual((camera / 'authorized').read_text(), '1')

    def test_open_media_blocks_power_off(self):
        h = self.helper
        with patch.object(h, 'validate_board'), patch.object(h, 'devices', return_value=[(Path('/fake'), ('0525','a4ad'))]), patch.object(h.Path, 'glob', return_value=[Path('/dev/video0')]), patch.object(h.subprocess, 'run', return_value=Mock(returncode=0)), patch.object(h, 'switch') as switch:
            with self.assertRaisesRegex(RuntimeError, 'still open'):
                h.power('off')
            switch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
