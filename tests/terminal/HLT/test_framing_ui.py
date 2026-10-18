# @test T-HLT-028
# @requirements HLR-TERM-VIDEO-002
# @environment display
# @plan Enable automatic framing through the real configuration controller and run its real detector worker/policy alongside Tk. Feed controlled detector boxes through a native ABI mailbox fixture, including two stable samples, a newcomer, an inference failure and a result delayed across disable. Navigate while detection is blocked.
# @pass Framing keeps the full view until stable, never exceeds 2x, widens for a newcomer and fails wide. Disable invalidates pending results and slow inference does not block navigation. Detector accuracy, native crop pixels and Pi throughput require separate model/native/hardware runs.

import copy
import ctypes as C
import os
import queue
import sys
import threading
import unittest
from unittest.mock import Mock, patch

from tests.support.terminal.ui_fixture import terminal_fixture, pump
from zmala_terminal.linux.auto_framing import AutoFraming, WIDE


@unittest.skipUnless(sys.platform == 'linux' and os.environ.get('DISPLAY'), 'Linux Tk display required')
class FramingUITests(unittest.TestCase):
    def test_framing_worker_configuration_and_ui_concurrency(self):
        frames, targets, enables = queue.Queue(), [], []
        current = {}
        gate, entered = threading.Event(), threading.Event()
        gate.set()
        threads = []

        def take(buffer, width, height):
            try:
                token, boxes = frames.get_nowait()
            except queue.Empty:
                return 0
            current['boxes'] = boxes
            C.cast(width, C.POINTER(C.c_int))[0] = 2
            C.cast(height, C.POINTER(C.c_int))[0] = 2
            buffer[:12] = bytes([40, 80, 120])*4
            return token

        def detect(rgb, width, height):
            self.assertEqual((width, height, rgb), (2, 2, bytes([40, 80, 120])*4))
            threads.append(threading.get_ident())
            entered.set()
            if not gate.wait(3):
                raise TimeoutError('fixture detector gate')
            if isinstance(current['boxes'], Exception):
                raise current['boxes']
            return current['boxes']

        plugin = Mock()
        plugin.zmala_framing_take.side_effect = take
        plugin.zmala_framing_enable.side_effect = enables.append
        plugin.zmala_framing_target.side_effect = lambda token, *target: targets.append((token, target))
        detector = Mock(detect=detect)
        with terminal_fixture() as (app, directory), \
                patch('zmala_terminal.linux.auto_framing.PersonDetector', return_value=detector):
            framing = AutoFraming(plugin, directory)
            app.engine.auto_framing = framing

            def configure(enabled):
                config = copy.deepcopy(app.model.config)
                config.update(auto_framing=enabled, configuration_version=config['configuration_version']+1)
                app.apply_config(config)

            def frame(sequence, boxes):
                token = 1 << 32 | sequence
                frames.put((token, boxes))
                framing.changed.set()
                return token

            try:
                configure(True)
                frame(1, [(.4, .3, .6, .6)])
                pump(app, lambda: len(targets) == 1)
                self.assertEqual(targets[-1][1], WIDE)
                frame(2, [(.4, .3, .6, .6)])
                pump(app, lambda: len(targets) == 2)
                self.assertEqual(targets[-1][1][2], .5)
                frame(3, [(.05, .2, .3, .7), (.7, .2, .95, .7)])
                pump(app, lambda: len(targets) == 3)
                self.assertEqual(targets[-1][1], WIDE)
                self.assertTrue(all(.5 <= target[2] <= 1 for _, target in targets))

                entered.clear(); gate.clear()
                frame(4, [(.4, .3, .6, .6)])
                pump(app, entered.is_set)
                before = app.model.index
                app.keypress('right'); app.keyrelease('right')
                self.assertNotEqual(app.model.index, before)
                configure(False)
                gate.set()
                pump(app, lambda: not framing.enabled)
                # Queue another session after disable; it must not reuse the old crop.
                configure(True)
                with self.assertLogs(level='ERROR'):
                    token = frame(5, RuntimeError('fixture inference failure'))
                    pump(app, lambda: targets and targets[-1][0] == token)
                self.assertEqual(targets[-1][1], WIDE)
                self.assertEqual(framing.status, 'unavailable')
                self.assertNotIn(1 << 32 | 4, [value for value, _ in targets])
                self.assertEqual(enables, [1, 0, 1])
                self.assertTrue(all(thread != threading.get_ident() for thread in threads))
            finally:
                gate.set()
                framing.close()
                self.assertFalse(framing.thread.is_alive())
                self.assertEqual(enables[-1], 0)


if __name__ == '__main__':
    unittest.main()
