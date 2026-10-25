# @test T-LLT-083
# @requirements LLR-TERM-AUDIO-009, LLR-TERM-CONFIG-021
# @environment portable
# @plan Validate catalog IDs, names, paths, membership and normalized PCM hashes/limits. Exercise cache download, reuse, corruption, retry and reset cancellation with disposable files. Control player time, C20 readiness/volume and process outcomes to assert preview debounce, ten-second cutoff, selection replacement, incoming-call priority, mute and cleanup. Drive the real settings controller and verify cancellation, incoming-call interruption and requested file routing with substituted playback.
# @pass All named assertions pass without playing sound or contacting a live server; actual speaker audibility remains hardware verification.
import hashlib
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import Mock, patch

from zmala_terminal.common.ringtones import DEFAULT_CHOICES, DEFAULT_SOUND, MAX_SOUND, RingtoneCache, valid_sound, validate_catalog
from zmala_terminal.common.local_settings import FIELDS, SettingsDraft
from zmala_terminal.common.model import State
from zmala_terminal.linux.usb_power import UsbPower
from tests.terminal.LLT import test_local_settings


def sound(frames=1600):
    return b'RIFF'+struct.pack('<I',36+frames*2)+b'WAVEfmt '+struct.pack('<IHHIIHH',16,1,1,16000,32000,2,16)+b'data'+struct.pack('<I',frames*2)+b'\x01\x00'*frames


class RingtoneTests(unittest.TestCase):
    def catalog(self, data=None):
        data = data or sound()
        key = hashlib.sha256(data).hexdigest()
        return key, {'ringtone': key, 'ringtones': DEFAULT_CHOICES+[{'id': key, 'name': 'Blackberry', 'url': f'/api/ringtones/{key}.wav'}]}

    def test_catalog_and_pcm_boundaries(self):
        data=sound();key,config=self.catalog(data)
        draft=SettingsDraft();draft.row=FIELDS.index('ringtone');draft.open(config)
        self.assertEqual(draft.options,['nokia',key]);self.assertEqual(draft.expected,{'ringtone':key})
        draft.move(-1);self.assertEqual(draft.change(config),{'ringtone':'nokia'})
        self.assertEqual(validate_catalog({}),DEFAULT_CHOICES)
        self.assertTrue(valid_sound(data,key))
        self.assertTrue(valid_sound(sound(480000),hashlib.sha256(sound(480000)).hexdigest()))
        for corrupt in (b'',data[:-1],b'BAD!'+data[4:],data[:24]+struct.pack('<I',48000)+data[28:],sound(480001)):
            self.assertFalse(valid_sound(corrupt,key))
        self.assertLessEqual(len(sound(480000)),MAX_SOUND)
        self.assertFalse(valid_sound(data,'0'*64))
        for change in ({'ringtone':None},{'ringtone':'../tone'},{'ringtones':[]},
                       {'ringtones':DEFAULT_CHOICES*2},{'ringtones':[{'id':'nokia','name':'\n','url':'/api/ringtones/nokia.wav'}]},
                       {'ringtones':[{'id':'nokia','name':'\u0085','url':'/api/ringtones/nokia.wav'}]},
                       {'ringtones':[{'id':'nokia','name':'Nokia','url':'https://other.test/tone.wav'}]}):
            with self.subTest(change=change),self.assertRaises(ValueError):validate_catalog(config|change)

    def test_cache_reuses_valid_audio_rejects_corruption_and_obeys_reset(self):
        data=sound();key,config=self.catalog(data)
        with tempfile.TemporaryDirectory() as folder:
            request=Mock(return_value=data);cache=RingtoneCache(folder,request)
            with patch('zmala_terminal.common.ringtones.threading.Thread'):
                cache.configure(config);cache.ensure(key)
                self.assertEqual(list(cache.pending),[key]);cache.run()
            file=cache.path(key);self.assertEqual(file.read_bytes(),data)
            self.assertEqual(cache.path('nokia'),DEFAULT_SOUND)
            request.assert_called_once_with(f'/api/ringtones/{key}.wav')
            reused=RingtoneCache(folder,Mock(side_effect=OSError('offline')))
            with patch('zmala_terminal.common.ringtones.threading.Thread'):
                reused.configure(config);reused.run()
            self.assertEqual(reused.path(key),file);reused.request.assert_not_called()
            file.write_bytes(b'bad cache')
            failed=RingtoneCache(folder,Mock(return_value=b'bad network'))
            with patch('zmala_terminal.common.ringtones.threading.Thread'):
                failed.configure(config);failed.run();failed.ensure(key)
            self.assertIsNone(failed.path(key));self.assertTrue(failed.failed(key));self.assertFalse(failed.pending)
            cancelled=RingtoneCache(folder,lambda route: (cancelled.close(),data)[1])
            with patch('zmala_terminal.common.ringtones.threading.Thread'):
                cancelled.configure(config);cancelled.run()
            self.assertEqual(file.read_bytes(),b'bad cache');self.assertIsNone(cancelled.path(key))
            self.assertFalse(list(Path(folder).glob('*.tmp')))

    def player(self):
        with patch.dict('os.environ',{},clear=True):power=UsbPower(Path('.'))
        power.enabled=True;power.state='on';power.revision=power.refreshed=0
        return power

    @patch('zmala_terminal.linux.c20_volume.status',return_value=(50,50,False))
    @patch('zmala_terminal.linux.usb_power.subprocess.Popen')
    def test_bounded_preview_replacement_and_incoming_priority(self,popen,status):
        process=popen.return_value;process.poll.return_value=None
        power=self.player();power.set_ringtone('/cache/saved.wav')
        power.preview_tone('/cache/choice.wav');power.play_tone(100)
        self.assertEqual(popen.call_args.args[0][-1],str(Path('/cache/choice.wav')))
        power.play_tone(109.99);process.terminate.assert_not_called()
        power.play_tone(110);process.terminate.assert_called_once();self.assertIsNone(power.preview_file)
        power.preview_tone('/cache/first.wav');power.play_tone(120)
        power.preview_tone('/cache/second.wav');power.play_tone(121)
        self.assertEqual(popen.call_args.args[0][-1],str(Path('/cache/second.wav')))
        power.ringing=True;power.play_tone(122)
        self.assertEqual(popen.call_args.args[0][-1],str(Path('/cache/saved.wav')));self.assertIsNone(power.preview_file)
        calls=popen.call_count;power.preview_tone('/cache/ignored.wav');power.play_tone(123)
        self.assertEqual(popen.call_count,calls)
        power.stop_ringing();self.assertIsNone(power.ringer);self.assertFalse(power.ringing)

    @patch('zmala_terminal.linux.c20_volume.status')
    @patch('zmala_terminal.linux.usb_power.subprocess.Popen')
    def test_preview_waits_for_readiness_and_volume_and_reports_failure(self,popen,status):
        power=self.player();power.preview_tone('/cache/choice.wav')
        power.state='switching';power.play_tone(1);popen.assert_not_called()
        power.state='on'
        for value in ((50,20,False),(50,50,True),(0,0,False)):
            status.return_value=value;power.play_tone(2);popen.assert_not_called()
        self.assertEqual(power.ringtone_preview_status,'muted')
        status.return_value=(50,50,False);popen.return_value.poll.return_value=None
        power.play_tone(3);self.assertEqual(power.ringtone_preview_status,'playing')
        popen.return_value.poll.return_value=1;power.play_tone(4)
        self.assertEqual(power.ringtone_preview_status,'error')
        power.preview_tone('/cache/choice.wav');popen.side_effect=OSError('missing player');power.play_tone(5)
        self.assertEqual(power.ringtone_preview_status,'error');self.assertIsNone(power.preview_file)

    def test_setting_preview_debounce_cancel_and_call_interruption(self):
        c=test_local_settings.LocalSettingsTests().controller();c.generation=1;c.settings_open=True;c.settings_draft=SettingsDraft()
        c.usb_power=Mock(enabled=True,ringtone_preview_status='playing');c.engine=None
        c.settings_draft.row=FIELDS.index('ringtone');c.settings_draft.open(c.model.config)
        c.tick_ringtone(100);c.tick_ringtone(100.39);c.usb_power.preview_tone.assert_not_called()
        c.tick_ringtone(100.4);c.usb_power.preview_tone.assert_called_once_with(DEFAULT_SOUND)
        c.tick_ringtone(101);self.assertEqual(c.usb_power.preview_tone.call_count,1)
        c.settings_button('red');c.tick_ringtone(102)
        self.assertIsNone(c.ringtone_preview_token);self.assertEqual(c.ringtone_preview_state,'')
        c.settings_draft.open(c.model.config);c.tick_ringtone(103);c.model.state=State.RINGING;c.tick_ringtone(104)
        self.assertIsNone(c.ringtone_preview_token);self.assertEqual(c.usb_power.preview_tone.call_count,1)

    def test_sdk_ringtone_is_reapplied_to_a_recreated_core(self):
        c=test_local_settings.LocalSettingsTests().controller();c.generation=1;c.settings_open=False;c.settings_draft=SettingsDraft()
        c.usb_power=Mock(enabled=False);c.engine=Mock();c.configuration=None
        c.tick_ringtone(1);c.engine.core_set_ring.assert_called_once_with(c.engine.core,str(DEFAULT_SOUND).encode())
        c.engine=Mock();c.tick_ringtone(2);c.engine.core_set_ring.assert_called_once()

    @patch('zmala_terminal.linux.usb_power.sys.platform','linux')
    @patch('zmala_terminal.linux.usb_power.threading.Thread')
    @patch('zmala_terminal.linux.c20_volume.status',return_value=(50,50,False))
    @patch('zmala_terminal.linux.usb_power.subprocess.Popen')
    def test_preview_without_usb_switching_starts_worker_and_stops_on_completion(self,popen,status,thread):
        power=self.player();power.enabled=False
        process=popen.return_value;process.poll.return_value=None
        power.preview_tone(DEFAULT_SOUND)
        thread.assert_called_once();thread.return_value.start.assert_called_once()
        def finish_preview(timeout):
            power.stop_preview()
        power.changed.wait=Mock(side_effect=finish_preview)
        power.preview_worker()
        self.assertIsNone(power.worker);self.assertIsNone(power.ringer)
        process.terminate.assert_called_once()
