# @test T-LLT-084
# @requirements LLR-TERM-AUDIO-010, LLR-TERM-AUDIO-009
# @environment portable
# @plan Scale known PCM at zero/intermediate/full levels and inspect exact silence, identity,
# independent gain, bounds and temporary-file cleanup. Inspect the unchanged left/right tap
# and the ordered rising green/low red double tap. Drive feedback enable/warmup, bursts,
# stale events, bounded audio-before-animation handoff, suppression and cancellation with controlled clocks and subprocess boundaries.
# Feed a complete synthesized cue through actual worker framing, bound nonblocking short writes
# and pipe timeouts, and verify termination escalation and no backlog. Warm every integer
# level in memory, prove pause/resume reuses it without synthesis, and cancel during startup.
# No physical audio is used.
# @pass PCM and lifecycle assertions pass; one warm player is used, inactive/busy/old requests
# do not replay, call/preview input remains quiet and audio helpers exclude the SIP preloader.
import array
import io
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
import wave
from zmala_terminal.linux.sound_levels import gain_db,scale_wav,click_pcm,ToneLevels,playback_environment
from zmala_terminal.linux.action_sounds import ActionSounds,FRAME,PERIOD,click_bank
from zmala_terminal.linux import media


def fixture_wav():
    output=io.BytesIO()
    with wave.open(output,'wb') as target:
        target.setparams((1,2,16000,0,'NONE','not compressed'))
        target.writeframes(array.array('h',[-16000,0,16000]*64).tobytes())
    return output.getvalue()


class SoundLevelsTests(unittest.TestCase):
    def pcm(self,data):
        with wave.open(io.BytesIO(data),'rb') as source:
            return array.array('h',source.readframes(source.getnframes()))

    def test_audio_helpers_keep_alsa_policy_without_loading_sip_dependencies(self):
        with patch.dict('os.environ',{'LD_PRELOAD':'/private/turn-fix.so','ALSA_CONFIG_PATH':'/policy'},clear=True):
            self.assertEqual(playback_environment(),{'ALSA_CONFIG_PATH':'/policy'})
            import os
            self.assertIn('LD_PRELOAD',os.environ)

    def test_exact_silence_identity_and_independent_gains(self):
        full=fixture_wav()
        self.assertEqual(scale_wav(full,100),full)
        self.assertTrue(all(v==0 for v in self.pcm(scale_wav(full,0))))
        self.assertLess(max(self.pcm(scale_wav(full,20))),max(self.pcm(scale_wav(full,50))))
        self.assertEqual(len(click_pcm(20)),48000*4*20//1000)
        left=array.array('h',click_pcm(100))[::2]
        self.assertEqual(sum(a<=0<b for a,b in zip(left,left[1:])),8)
        self.assertTrue(any(click_pcm(20)));self.assertFalse(any(click_pcm(0)))
        self.assertEqual(click_pcm(100,'left'),click_pcm(100,'right'))
        self.assertEqual(click_pcm(100,'left'),click_pcm(100,'pointer'))
        green=array.array('h',click_pcm(100,'green'))[::2]
        self.assertEqual(len(green),1920);self.assertEqual(green[:960],left)
        tail=green[960:]
        self.assertEqual(sum(a<=0<b for a,b in zip(tail,tail[1:])),12)
        red=array.array('h',click_pcm(100,'red'))[::2]
        self.assertEqual(len(red),3360)
        self.assertEqual(red[:960],red[-960:])
        self.assertFalse(any(red[960:-960]))
        self.assertEqual(sum(a<=0<b for a,b in zip(red[:960],red[1:960])),5)
        for button in ('green','red'):self.assertFalse(any(click_pcm(0,button)))
        with self.assertRaises(ValueError):click_pcm(50,'unknown')
        engine=Mock(core=1)
        with patch('zmala_terminal.linux.c20_volume.status',return_value=(0,0,False)):
            media.sync_speaker_mute(engine)
        engine.core_set_playback_gain_db.assert_called_once_with(1,-120)
        self.assertEqual(gain_db(50),-14)
        for invalid in (True,-1,101,50.5,'50',None):
            with self.assertRaises(ValueError):gain_db(invalid)
            with self.assertRaises(ValueError):click_pcm(invalid)

    def test_scaled_tone_files_are_reused_replaced_and_removed(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source.wav';source.write_bytes(fixture_wav())
            levels=ToneLevels();one=levels.prepare(source,50)
            self.assertEqual(levels.prepare(source,50),one)
            two=levels.prepare(source,20)
            self.assertFalse(one.exists());self.assertTrue(two.exists())
            self.assertLess(max(self.pcm(two.read_bytes())),max(self.pcm(source.read_bytes())))
            levels.close();self.assertFalse(two.exists())

    def test_warm_player_has_no_busy_or_cold_backlog(self):
        sound=ActionSounds()
        with patch('zmala_terminal.linux.action_sounds.threading.Thread') as thread, \
                patch('zmala_terminal.linux.action_sounds.time.monotonic',return_value=10):
            sound.set_enabled(True);sound.set_enabled(True);thread.assert_called_once()
            sound.play(20);self.assertIsNone(sound.pending)
            sound.warmed=True;sound.play(20);sound.play(50)
            self.assertEqual(sound.pending[:3],(20,10,'left'))
            sound.play(0);self.assertIsNone(sound.pending)
            sound.sounding=True;sound.play(50);self.assertIsNone(sound.pending)
            sound.close();self.assertFalse(sound.enabled);self.assertTrue(sound.stop.is_set())
            sound.play(50);self.assertIsNone(sound.pending)

    def test_actual_worker_frames_complete_cue_and_discards_old_requests(self):
        bank=click_bank()
        for button,age in [('left',0),('green',0),('red',0),('left',1)]:
            expected=click_pcm(20,button) if age==0 else bytes(48000*4*20//1000)
            count=len(expected)//FRAME
            ready=Mock();sound=ActionSounds();sound.pending=(20,10-age,button,ready)
            frames=[]
            def write(player,data):
                frames.append(data)
                if len(frames)==count:sound.stop.set()
                return True
            with patch('zmala_terminal.linux.action_sounds.subprocess.Popen') as popen, \
                    patch('zmala_terminal.linux.action_sounds.click_pcm',side_effect=AssertionError('synthesis on hot path')), \
                    patch('zmala_terminal.linux.action_sounds.os.set_blocking'), \
                    patch('zmala_terminal.linux.action_sounds.time.monotonic',return_value=10), \
                    patch.object(sound,'_write',side_effect=write),patch.object(sound.stop,'wait'):
                sound.run()
                self.assertEqual(b''.join(frames),expected)
                self.assertEqual(ready.set.call_count,1 if age==0 else 0)
                self.assertIn('raw',popen.call_args.args[0]);self.assertIn('default:C20',popen.call_args.args[0])
                self.assertIn('--buffer-time=5000',popen.call_args.args[0])
                self.assertIn('--period-time=2500',popen.call_args.args[0])
                self.assertEqual(PERIOD,.0025)
                self.assertEqual(popen.call_args.kwargs['pipesize'],4096)
                self.assertIsNone(sound.worker);self.assertIsNone(sound.pending)
                self.assertEqual(sound.retry_at,0)
                popen.return_value.stdin.close.assert_called_once()
        self.assertIs(click_bank(),bank)

    def test_entire_feedback_bank_is_bounded_and_built_once(self):
        import sys
        click_bank.cache_clear()
        try:
            bank=click_bank()
            self.assertEqual(len(bank),300)
            for percent in range(1,101):
                for button in ('left','green','red'):
                    frames=bank[percent,button]
                    self.assertTrue(all(len(frame)==FRAME for frame in frames))
                    self.assertEqual(b''.join(frames),click_pcm(percent,button))
            size=sys.getsizeof(bank)+sum(sys.getsizeof(k)+sys.getsizeof(v)
                +sum(sys.getsizeof(frame) for frame in v) for k,v in bank.items())
            self.assertLess(size,4*1024*1024)
            with patch('zmala_terminal.linux.action_sounds.click_pcm',side_effect=AssertionError('rebuilt')):
                self.assertIs(click_bank(),bank)
        finally:click_bank.cache_clear()

    def test_cancel_during_bank_preparation_never_opens_alsa(self):
        sound=ActionSounds()
        def prepare():
            sound.stop.set()
            return {}
        with patch('zmala_terminal.linux.action_sounds.click_bank',side_effect=prepare), \
                patch('zmala_terminal.linux.action_sounds.subprocess.Popen') as popen:
            sound.run()
            popen.assert_not_called()
            self.assertIsNone(sound.worker)

    def test_cancel_joins_a_starting_player_within_the_existing_stop_budget(self):
        sound=ActionSounds();sound.worker=Mock()
        with patch('zmala_terminal.linux.action_sounds.time.monotonic',side_effect=[10,10.05]), \
                patch.object(sound,'_stop_player'):
            sound.cancel()
            self.assertTrue(sound.stop.is_set())
            self.assertAlmostEqual(sound.worker.join.call_args.kwargs['timeout'],.15)

    def test_handoff_yields_before_animation_with_a_bounded_head_start(self):
        sound=ActionSounds();sound.enabled=sound.warmed=True
        ready=Mock()
        with patch('zmala_terminal.linux.action_sounds.threading.Event',return_value=ready), \
                patch.object(sound.stop,'wait') as head_start:
            ready.wait.return_value=True
            sound.play(20,'green')
            ready.wait.assert_called_once_with(.02)
            head_start.assert_called_once_with(.02)
            self.assertIs(sound.pending[3],ready)
            sound.pending=None;ready.reset_mock();head_start.reset_mock()
            ready.wait.return_value=False
            sound.play(20,'red')
            ready.wait.assert_called_once_with(.02)
            head_start.assert_not_called()

    def test_short_writes_timeout_and_player_termination_are_bounded(self):
        sound=ActionSounds();player=Mock();player.stdin.fileno.return_value=9
        with patch('zmala_terminal.linux.action_sounds.time.monotonic',return_value=10), \
                patch('zmala_terminal.linux.action_sounds.select.select',return_value=([],[9],[])), \
                patch('zmala_terminal.linux.action_sounds.os.write',side_effect=[2,2]) as write:
            self.assertTrue(sound._write(player,b'abcd'))
            self.assertEqual(bytes(write.call_args_list[1].args[1]),b'cd')
        with patch('zmala_terminal.linux.action_sounds.time.monotonic',side_effect=[10,10.3]):
            self.assertFalse(sound._write(player,b'abcd'))
        player.wait.side_effect=[subprocess.TimeoutExpired('aplay',.1),0]
        ActionSounds._stop_player(player);player.kill.assert_called_once()

    def test_clicks_are_suppressed_for_calls_and_ringtone_previews(self):
        from zmala_terminal.common.input_control import InputControl
        from zmala_terminal.common.model import State
        app=SimpleNamespace(action_sounds=Mock(),engine=SimpleNamespace(call=None),settings_open=False,
            settings_draft=SimpleNamespace(editing=False),model=SimpleNamespace(state=State.HOME,config={}),
            usb_power=SimpleNamespace(ready=True,ringing=False,ringtone_preview_status=''))
        InputControl.button_feedback(app);app.action_sounds.play.assert_called_once_with(20,'left')
        app.action_sounds.play.reset_mock()
        for button in ('left','right','green','red','pointer'):
            InputControl.button_feedback(app,button)
            app.action_sounds.play.assert_called_with(20,button)
        for state in (State.CONFIRMING,State.CONFIRM_CALLBACK):
            app.model.state=state
            InputControl.button_feedback(app,'red')
            app.action_sounds.play.assert_called_with(20,'red')
        app.action_sounds.play.reset_mock()
        for state in (State.CALLING,State.CONNECTING,State.RINGING,State.IN_CALL):
            app.model.state=state;InputControl.button_feedback(app)
        app.model.state=State.HOME
        for preview in ('waiting','playing'):
            app.usb_power.ringtone_preview_status=preview;InputControl.button_feedback(app)
        app.usb_power.ringtone_preview_status='';app.usb_power.ringing=True
        InputControl.button_feedback(app)
        app.usb_power.ringing=False;app.settings_open=True
        for key in ('ringtone','ringtone_volume'):
            app.settings_draft=SimpleNamespace(editing=True,key=key);InputControl.button_feedback(app)
        app.action_sounds.play.assert_not_called()

    def test_feedback_releases_c20_before_core_creation_and_stays_off_while_unconfigured(self):
        from zmala_terminal.common.configuration_control import ConfigurationControl
        from zmala_terminal.common.settings_control import SettingsControl
        from zmala_terminal.common.local_settings import SettingsDraft
        from zmala_terminal.common.model import State
        order=[];feedback=Mock();feedback.cancel.side_effect=lambda:order.append('released')
        engine=Mock(call=None,registered=False)
        def create(config):
            self.assertEqual(order,['released']);order.append('core');return engine
        app=SimpleNamespace(engine=None,action_sounds=feedback,make_engine=create,current_settings={},
            usb_power=Mock(enabled=False,ready=True,ringing=False,ringtone_preview_status='',playback_active=False),
            settings_open=False,settings_draft=SettingsDraft(),model=SimpleNamespace(state=State.HOME,config={}),
            setup_stage=None,generation=1,render=Mock())
        SettingsControl.tick_ringtone(app,1)
        feedback.set_enabled.assert_called_with(False)
        ConfigurationControl.configure_engine(app,{'sip':{}},None,'normal')
        self.assertEqual(order,['released','core'])
        SettingsControl.tick_ringtone(app,2)
        feedback.set_enabled.assert_called_with(True) # Offline SIP alone does not prevent button feedback.
