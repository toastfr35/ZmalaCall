# @test T-LLT-004
# @requirements LLR-TERM-POWER-002
# @environment portable
# @plan Inject temperatures, call state and I2C writes; assert the fan stops outside calls, follows thermal bands during calls and never emits power-control bytes.
# @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

"""Call-only fan policy and narrowly bounded Argon commands."""
from pathlib import Path
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
        self.assertEqual(fan.fan_speed(True, 70), 100)

    def test_power_control_bytes_are_never_accepted(self):
        for value in (-1, 101, 253, 254, 255, True, 55.0):
            with self.assertRaises(ValueError):
                fan.write_speed(value)

    def test_write_one_byte_only_to_argon_and_always_close_descriptor(self):
        ioctl = Mock()
        with patch.dict(sys.modules, fcntl=Mock(ioctl=ioctl)), \
                patch.object(fan.os, 'open', return_value=7), \
                patch.object(fan.os, 'write', return_value=1) as write, patch.object(fan.os, 'close') as close:
            fan.write_speed(55)
            ioctl.assert_called_once_with(7, 0x0703, 0x1a)
            write.assert_called_once_with(7, b'7')
            close.assert_called_once_with(7)
            write.side_effect = OSError('disconnected')
            with self.assertRaises(OSError):
                fan.write_speed(0)
            self.assertEqual(close.call_count, 2)

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
