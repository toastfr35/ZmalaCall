# @test T-LLT-041
# @requirements LLR-TERM-CONFIG-024, LLR-TERM-REMOTE-016, LLR-TERM-AUDIO-006, LLR-TERM-AUDIO-007, LLR-TERM-AUDIO-008
# @environment portable
# @plan Feed signed motion around deadband and limits while holding/releasing middle; assert relative volume increments, throttled mixer writes, overlay lifetime, default changes retry after failed writes and reapplication after USB wake. Reject invalid API levels before spawning workers; ignore pointer input before mixer state is known.
# @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

"""Held-pointer volume has bounded motion, throttled writes and no call actions."""
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from zmala_terminal.common.volume_control import VolumeControl, VolumeGesture
from zmala_terminal.common import volume_control
from zmala_terminal.common.theme import GREEN, RED
from zmala_terminal.linux import c20_volume as c20_volume


class VolumeTests(unittest.TestCase):
    def test_overlay_geometry_status_and_shutdown_flush(self):
        root=Mock(); canvas=Mock(); control=VolumeControl(root,lambda:True,Mock())
        with patch.object(volume_control.tk,'Canvas',return_value=canvas) as create,patch.object(volume_control.tk.Misc,'lift') as lift,patch.object(c20_volume,'status',return_value=(50,50,False)) as status,patch.object(c20_volume,'request') as request:
            control.draw(); create.assert_called_once(); lift.assert_called_with(canvas)
            self.assertEqual(canvas.create_text.call_args.kwargs['text'],'50%'); self.assertEqual(canvas.create_text.call_args.kwargs['fill'],GREEN)
            self.assertEqual(canvas.create_rectangle.call_args.args,(33,157,51,249))
            control.gesture.percent=0; canvas.reset_mock(); control.draw(); canvas.create_arc.assert_not_called(); self.assertEqual(canvas.create_line.call_count,2)
            status.return_value=(50,None,True); control.draw(); self.assertEqual(canvas.create_text.call_args.kwargs['text'],'!'); self.assertEqual(canvas.create_text.call_args.kwargs['fill'],RED)
            control.timer='pending'; control.sent=50; control.gesture.percent=54; control.close()
            root.after_cancel.assert_called_once_with('pending'); request.assert_called_once_with(54); canvas.destroy.assert_called_once()
            control.pointer(True); control.motion(-100); control.refresh(); self.assertEqual(control.gesture.percent,54)

    def test_motion_sign_jitter_release_and_limits(self):
        gesture = VolumeGesture(50)
        gesture.move(-640)
        self.assertEqual(gesture.percent, 50)
        gesture.hold(True)
        for _ in range(100):
            gesture.move(5); gesture.move(-5)
        self.assertEqual(gesture.percent, 50)
        gesture.move(-128)
        self.assertEqual(gesture.percent, 54)
        gesture.move(64)
        self.assertEqual(gesture.percent, 52)
        gesture.move(-64000)
        self.assertEqual(gesture.percent, 100)
        gesture.move(64)
        self.assertEqual(gesture.percent, 98)
        gesture.move(64000)
        self.assertEqual(gesture.percent, 0)
        gesture.move(-64)
        self.assertEqual(gesture.percent, 2)
        gesture.move(-63)
        gesture.hold(False); gesture.hold(True); gesture.move(-1)
        self.assertEqual(gesture.percent, 2, 'A new hold must not retain old motion')

    def test_overlay_throttles_writes_flushes_release_and_hides(self):
        root = Mock()
        control = VolumeControl(root, lambda: True, Mock())
        control.draw = Mock()
        control.canvas = Mock()
        with patch('zmala_terminal.common.volume_control.time.monotonic', return_value=10) as clock, \
                patch.object(c20_volume, 'status', return_value=(80, 80, False)), \
                patch.object(c20_volume, 'request') as request:
            control.pointer(True)
            request.assert_not_called()
            control.motion(64*5); control.refresh()
            request.assert_called_once_with(70)
            clock.return_value = 10.05
            control.motion(64*5); control.refresh()
            request.assert_called_once_with(70)
            control.pointer(False)
            control.motion(64000)
            clock.return_value = 10.2
            control.refresh()
            self.assertEqual(request.call_args.args, (60,))
            clock.return_value = 12.1
            control.refresh()
            control.canvas.place_forget.assert_called_once()
            self.assertIsNone(control.timer)

    def test_disabled_gesture_does_not_change_volume_or_show_overlay(self):
        control = VolumeControl(Mock(), lambda: False, Mock())
        with patch.object(c20_volume, 'request') as request:
            control.pointer(True); control.motion(-6400); control.pointer(False)
            request.assert_not_called()
            self.assertIsNone(control.canvas)
            self.assertIsNone(control.timer)

    def test_local_level_survives_engine_reconfiguration_but_changed_default_wins(self):
        with patch.multiple(c20_volume, _desired=None, _applied=None, _worker=None,
                            _configured=None, _failed=False), patch.object(c20_volume, 'apply', return_value=True):
            def settle():
                worker = c20_volume._worker
                if worker:
                    worker.join(2)
                    self.assertFalse(worker.is_alive())
            c20_volume.configure(80); settle()
            c20_volume.request(35); settle()
            c20_volume.configure(80); settle()
            self.assertEqual(c20_volume.status(), (35, 35, False))
            c20_volume.configure(60); settle()
            self.assertEqual(c20_volume.status(), (60, 60, False))

    def test_failed_write_is_visible_and_can_retry_previous_applied_level(self):
        with patch.multiple(c20_volume, _desired=80, _applied=80, _worker=None,
                            _configured=80, _failed=False), patch.object(c20_volume, 'apply', side_effect=[False, True]):
            c20_volume.request(70)
            worker = c20_volume._worker
            if worker:
                worker.join(2)
            self.assertEqual(c20_volume.status(), (70, 80, True))
            c20_volume.request(80)
            worker = c20_volume._worker
            if worker:
                worker.join(2)
            self.assertEqual(c20_volume.status(), (80, 80, False))

    def test_usb_wake_reapplies_level_and_unknown_volume_does_not_start_worker(self):
        with patch.multiple(c20_volume, _desired=36, _applied=36, _worker=None), \
                patch.object(c20_volume, 'request') as request:
            c20_volume.reapply()
            self.assertEqual(c20_volume.status()[:2], (36, None))
            request.assert_called_once_with(36)
            request.reset_mock()
            c20_volume._desired = None
            c20_volume.reapply()
            request.assert_not_called()
        with patch.object(c20_volume.threading, 'Thread') as worker:
            for value in (-1, 101, 2.5, True, '50', None):
                for action in (c20_volume.configure, c20_volume.request):
                    with self.subTest(value=value, action=action.__name__), self.assertRaises(ValueError):
                        action(value)
            worker.assert_not_called()
        activity = Mock()
        control = VolumeControl(Mock(), lambda: True, activity)
        with patch.object(c20_volume, 'status', return_value=(None, None, False)):
            control.pointer(True)
        activity.assert_not_called()
        self.assertFalse(control.gesture.held)
        self.assertIsNone(control.timer)
        self.assertIsNone(control.canvas)
