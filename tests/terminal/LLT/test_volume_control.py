# @test T-LLT-041
# @requirements LLR-TERM-CONFIG-024, LLR-TERM-REMOTE-016, LLR-TERM-AUDIO-006, LLR-TERM-AUDIO-007, LLR-TERM-AUDIO-008
# @environment portable
# @plan Toggle the dedicated volume page with distinct middle presses; adjust left/right on the five-percent grid and test bounds, duplicate presses, disabled/unknown state, throttled writes and final flush. Check horizontal full-page/compact in-call feedback, mixer failure, context preemption and unchanged microphone routing. Exercise default retries and USB wake separately; change a saved default while an unsent volume click is pending and verify it cannot overwrite that default.
# @pass Named assertions pass; skips and visual/hardware checks are recorded separately.

"""Dedicated volume page and bounded C20 playback writes."""
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from zmala_terminal.common.volume_control import VolumeControl, VolumeLevel
from zmala_terminal.common import volume_control
from zmala_terminal.common.theme import GREEN, RED
from zmala_terminal.linux import c20_volume


class VolumeTests(unittest.TestCase):
    def test_steps_bounds_and_existing_between_step_level(self):
        for start, button, expected in [(50,'right',55),(50,'left',45),
                                        (53,'right',55),(53,'left',50),
                                        (0,'left',0),(100,'right',100)]:
            level=VolumeLevel(start); level.adjust(button)
            self.assertEqual(level.percent,expected)
            level.adjust('red'); self.assertEqual(level.percent,expected)

    def test_toggle_duplicates_release_and_no_timeout(self):
        control=VolumeControl(Mock(),lambda:True,Mock()); control.draw=Mock()
        with patch.object(c20_volume,'status',return_value=(50,50,False)), patch.object(c20_volume,'request') as request:
            control.pointer(True); self.assertTrue(control.active)
            control.pointer(True); self.assertTrue(control.active)
            control.pointer(False); self.assertTrue(control.active)
            control.button('right'); self.assertEqual(control.level.percent,55)
            control.pointer(True); self.assertFalse(control.active)
            request.assert_called_once_with(55)
            control.pointer(False); control.pointer(True)
            self.assertTrue(control.active)
            with patch.object(volume_control.time,'monotonic',return_value=1000000):control.refresh()
            self.assertTrue(control.active)
            control.close(); self.assertFalse(control.active)
            control.pointer(False); control.pointer(True); self.assertFalse(control.active)

    def test_write_throttle_and_dismiss_flush(self):
        control=VolumeControl(Mock(),lambda:True,Mock());control.draw=Mock()
        with patch.object(volume_control.time,'monotonic',return_value=10) as clock, patch.object(c20_volume,'status',return_value=(80,80,False)), patch.object(c20_volume,'request') as request:
            control.pointer(True); request.assert_not_called()
            control.button('left'); control.refresh(); request.assert_called_once_with(75)
            clock.return_value=10.05
            control.button('left'); control.refresh(); request.assert_called_once_with(75)
            control.dismiss();self.assertEqual(request.call_args.args,(70,))
            control.button('right');self.assertEqual(control.level.percent,70)

    def test_context_change_and_disabled_state_preempt_page(self):
        context=Mock(return_value='home'); enabled=Mock(return_value=True)
        control=VolumeControl(Mock(),enabled,Mock(),context);control.draw=Mock()
        with patch.object(c20_volume,'status',return_value=(50,50,False)):
            control.pointer(True);context.return_value='ringing';control.refresh()
            self.assertFalse(control.active)
            control.pointer(False);enabled.return_value=False;control.pointer(True)
            self.assertFalse(control.active)
            enabled.return_value=True;control.pointer(False);control.pointer(True)
            enabled.return_value=False;control.refresh();self.assertFalse(control.active)

    def test_horizontal_full_page_feedback_failure_and_close(self):
        root=Mock();root.winfo_width.return_value=1280;root.winfo_height.return_value=720
        canvas=Mock();control=VolumeControl(root,lambda:True,Mock())
        with patch.object(volume_control.tk,'Canvas',return_value=canvas),patch.object(volume_control.tk.Misc,'lift'),patch.object(c20_volume,'status',return_value=(50,50,False)) as status:
            control.draw();canvas.place.assert_called_with(x=0,y=0,relx=.5,rely=.68,anchor='center',width=900,height=160,relwidth=0,relheight=0)
            canvas.configure.assert_called_with(bg='#000000')
            self.assertEqual(canvas.create_text.call_args.kwargs['text'],'50%')
            self.assertEqual(canvas.create_text.call_args.kwargs['fill'],GREEN)
            track=canvas.create_rectangle.call_args_list[0].args
            self.assertGreater(track[2]-track[0],track[3]-track[1])
            status.return_value=(50,None,True);control.draw()
            self.assertEqual(canvas.create_text.call_args.kwargs['text'],'!')
            self.assertEqual(canvas.create_text.call_args.kwargs['fill'],RED)
            control.close();canvas.destroy.assert_called_once()

    def test_in_call_overlay_keeps_video_area_uncovered_and_restores_full_page(self):
        root=Mock();root.winfo_width.return_value=1280;root.winfo_height.return_value=720
        in_call=Mock(return_value=True);canvas=Mock()
        control=VolumeControl(root,lambda:True,Mock(),in_call=in_call)
        with patch.object(volume_control.tk,'Canvas',return_value=canvas),patch.object(volume_control.tk.Misc,'lift') as lift,patch.object(c20_volume,'status',return_value=(50,50,False)):
            control.draw();placement=canvas.place.call_args.kwargs
            self.assertLess(placement['width'],1280)
            self.assertLess(placement['height'],720/3)
            self.assertEqual((placement['relwidth'],placement['relheight']),(0,0))
            self.assertEqual(placement['anchor'],'center');lift.assert_called_with(canvas)
            in_call.return_value=False;control.draw()
            placement=canvas.place.call_args.kwargs
            self.assertEqual((placement['relwidth'],placement['relheight']),(0,0))
            self.assertEqual(placement['anchor'],'center')
            self.assertLess(placement['width'],1280)
            self.assertLess(placement['height'],720/3)

    def test_changed_default_supersedes_pending_click_even_if_current_value_is_unchanged(self):
        with patch.multiple(c20_volume, _desired=None, _applied=None, _worker=None,
                            _configured=None, _default_revision=0, _failed=False), patch.object(c20_volume, 'apply', return_value=True):
            def settle():
                worker=c20_volume._worker
                if worker:worker.join(2);self.assertFalse(worker.is_alive())
            c20_volume.configure(80);settle()
            c20_volume.request(50);settle()
            control=VolumeControl(Mock(),lambda:True,Mock());control.draw=Mock()
            control.pointer(True);control.button('right')
            self.assertEqual(control.level.percent,55)
            c20_volume.configure(50);settle()  # New saved default, same hardware value.
            control.dismiss();settle()
            self.assertEqual(c20_volume.status(),(50,50,False))
            self.assertEqual(control.level.percent,50)
            control.pointer(False);control.pointer(True);control.button('right');control.dismiss();settle()
            self.assertEqual(c20_volume.status(),(55,55,False),'A later deliberate click still works')

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
        self.assertFalse(control.active)
        self.assertIsNone(control.timer)
        self.assertIsNone(control.canvas)
