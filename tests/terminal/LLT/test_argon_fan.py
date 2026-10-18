# @test T-LLT-004
# @requirements LLR-TERM-POWER-011
# @environment portable
# @plan Inject temperatures, call state and I2C writes; assert the 65 C threshold, bus 1/address 0x1a, short-write cleanup, bounded failure logging/recovery and crash-stop entrypoint. Verify the worker stops outside calls and never emits power-control bytes.
# @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

"""Call-only fan policy and narrowly bounded Argon commands."""
from pathlib import Path
import runpy
import sys
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from zmala_terminal.linux import argon_fan as fan


class ArgonFanTests(unittest.TestCase):
    def test_off_outside_calls_and_speed_increases_during_hot_calls(self):
        for degrees in (None, 30, 60, 65, 90):
            self.assertEqual(fan.fan_speed(False, degrees), 0)
        self.assertEqual(fan.fan_speed(True, 40), 55)
        self.assertEqual(fan.fan_speed(True, 64.999), 55)
        self.assertEqual(fan.fan_speed(True, 65), 100)
        self.assertEqual(fan.fan_speed(True, 70), 100)

    def test_enablement_requires_linux_and_explicit_install_flag(self):
        for platform, flag, expected in [('linux', '1', True), ('linux', '0', False), ('win32', '1', False)]:
            with patch.object(fan.sys, 'platform', platform), patch.dict(fan.os.environ, ZMALA_ARGON_ONE_FAN=flag):
                self.assertEqual(fan.enabled(), expected)

    def test_temperature_converts_millidegrees_and_tolerates_missing_sensor(self):
        with patch.object(fan.Path, 'read_text', return_value='65000'):
            self.assertEqual(fan.temperature(), 65)
        for error in (OSError('missing'), ValueError('invalid')):
            with patch.object(fan.Path, 'read_text', side_effect=error):
                self.assertIsNone(fan.temperature())

    def test_power_control_bytes_are_never_accepted(self):
        for value in (-1, 101, 253, 254, 255, True, 55.0):
            with self.assertRaises(ValueError):
                fan.write_speed(value)

    def test_write_one_byte_only_to_argon_and_always_close_descriptor(self):
        ioctl = Mock()
        with patch.dict(sys.modules, fcntl=Mock(ioctl=ioctl)), \
                patch.object(fan.os, 'open', return_value=7) as opened, \
                patch.object(fan.os, 'write', return_value=1) as write, patch.object(fan.os, 'close') as close:
            fan.write_speed(55)
            opened.assert_called_once_with('/dev/i2c-1', fan.os.O_RDWR | getattr(fan.os, 'O_CLOEXEC', 0))
            ioctl.assert_called_once_with(7, 0x0703, 0x1a)
            write.assert_called_once_with(7, b'7')
            close.assert_called_once_with(7)
            write.side_effect = OSError('disconnected')
            with self.assertRaises(OSError):
                fan.write_speed(0)
            self.assertEqual(close.call_count, 2)
            write.side_effect = None
            write.return_value = 0
            with self.assertRaisesRegex(OSError, 'Incomplete'):
                fan.write_speed(55)
            self.assertEqual(close.call_count, 3)

    def test_worker_retries_failure_without_log_flood_and_reports_failed_stop(self):
        for final_error in (None, OSError('stop failed')):
            controller = fan.ArgonFan.__new__(fan.ArgonFan)
            controller.active = True; controller.stopped = False
            controller.changed = Mock()
            iterations = []
            def wait(_):
                iterations.append(True)
                controller.stopped = len(iterations) == 3
            controller.changed.wait.side_effect = wait
            with patch.object(fan, 'temperature', return_value=30), \
                    patch.object(fan, 'write_speed', side_effect=[OSError(), OSError(), None, final_error]) as write, \
                    patch.object(fan.logging, 'warning') as warning:
                controller.run()
            self.assertEqual([call.args[0] for call in write.call_args_list], [55, 55, 55, 0])
            self.assertEqual(warning.call_count, 2 if final_error else 1)

    def test_crash_stop_entrypoint_only_writes_zero_duty(self):
        with patch.object(fan.sys, 'platform', 'linux'), patch.dict(fan.os.environ, ZMALA_ARGON_ONE_FAN='1'), \
                patch.dict(sys.modules, fcntl=Mock()), patch.object(fan.os, 'open', return_value=7), \
                patch.object(fan.os, 'write', return_value=1) as write, patch.object(fan.os, 'close'):
            runpy.run_path(fan.__file__, run_name='__main__')
        write.assert_called_once_with(7, b'\x00')

    def test_worker_stops_fan_when_call_ends_and_on_shutdown(self):
        writes, changed = [], threading.Event()
        def write(value):
            writes.append(value)
            changed.set()
        with patch.object(fan, 'enabled', return_value=True), patch.object(fan, 'write_speed', side_effect=write), \
                patch.object(fan, 'temperature', return_value=40):
            controller = fan.ArgonFan()
            try:
                self.assertTrue(changed.wait(1))
                changed.clear()
                controller.update(True)
                self.assertTrue(changed.wait(1))
                changed.clear()
                controller.update(False)
                self.assertTrue(changed.wait(1))
            finally:
                controller.close()
            self.assertEqual(writes, [0, 55, 0, 0])
            self.assertFalse(controller.worker.is_alive())

    def test_normal_install_does_not_touch_i2c(self):
        with patch.object(fan, 'enabled', return_value=False), patch.object(fan, 'write_speed') as write:
            controller = fan.ArgonFan()
            controller.update(True)
            controller.close()
            write.assert_not_called()


if __name__ == '__main__':
    unittest.main()
