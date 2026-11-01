# @test T-LLT-090
# @requirements LLR-TERM-AUDIO-010
# @environment portable
# @plan Feed real 8 kHz PCM with the SDK streaming header to the engine ringback
# selection. Assert zero/intermediate/full levels, current configuration and legacy
# fallback, reuse, active-call deferral, Windows separation and shutdown ordering.
# Reject wrong format/oversized input; verify the generated WAV has a finite header.
# @pass The SDK gets independently scaled PCM before invitation, without playback-gain
# writes; zero is silent, active files survive calls and cleanup follows core shutdown.
from zmala_terminal.common.media_adapter import MediaAdapter
from zmala_terminal.common.engine import media_backend
import array
import io
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import Mock, patch
import wave
from zmala_terminal.common import engine
from zmala_terminal.linux.sound_levels import ToneLevels


def ringback_wav():
    stream = io.BytesIO()
    with wave.open(stream, 'wb') as out:
        out.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
        out.writeframes(array.array('h', [-16000, 0, 16000]*64).tobytes())
    data = bytearray(stream.getvalue())
    struct.pack_into('<I', data, 40, 0x7ffff000)  # Bundled SDK streaming declaration.
    return bytes(data)


def samples(path):
    with wave.open(str(path)) as source:
        assert source.getframerate() == 8000
        assert source.getnframes() == 192
        return array.array('h', source.readframes(192))


class RingbackVolumeTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(); self.addCleanup(directory.cleanup)
        self.sdk = Path(directory.name)
        self.source = self.sdk/'share/sounds/linphone/ringback.wav'
        self.source.parent.mkdir(parents=True); self.source.write_bytes(ringback_wav())
        for item in (patch.object(engine, 'SDK', self.sdk), patch.object(engine, 'WINDOWS', False)):
            item.start(); self.addCleanup(item.stop)
        self.e = engine.Engine.__new__(engine.Engine); self.e.media = MediaAdapter(media_backend())
        self.e.config = {'ringtone_volume': 30, 'c20_speaker_volume': 100}
        self.e.call = None; self.e.core = 1; self.e.ringback_levels = None
        self.e.core_set_ringback = Mock(); self.e.core_set_playback_gain_db = Mock()
        self.addCleanup(lambda: self.e.ringback_levels and self.e.ringback_levels.close())

    def prepare(self):
        self.e.apply_ringback_volume()
        return Path(self.e.core_set_ringback.call_args.args[1].decode())

    def test_saved_level_silence_reuse_and_legacy_fallback(self):
        first = self.prepare(); at30 = max(samples(first))
        self.assertEqual(self.prepare(), first)
        self.e.config['c20_speaker_volume'] = 0
        self.assertEqual(self.prepare(), first)
        self.e.config['ringtone_volume'] = 100
        full = self.prepare(); self.assertFalse(first.exists())
        self.assertEqual(max(samples(full)), 16000); self.assertLess(at30, 16000)
        self.e.config['ringtone_volume'] = 0
        silent = self.prepare(); self.assertFalse(any(samples(silent)))
        del self.e.config['ringtone_volume']; self.e.config['c20_speaker_volume'] = 30
        self.assertEqual(max(samples(self.prepare())), at30)
        self.e.core_set_playback_gain_db.assert_not_called()

    def test_active_call_keeps_file_and_shutdown_releases_after_sdk(self):
        first = self.prepare(); self.e.config['ringtone_volume'] = 0; self.e.call = 123
        self.e.core_set_ringback.reset_mock(); self.e.apply_ringback_volume()
        self.e.core_set_ringback.assert_not_called(); self.assertTrue(first.exists())
        self.e.end = Mock(); self.e.hold_call = Mock(); self.e.core_stop = Mock()
        self.e.core_unref = Mock(side_effect=lambda core: self.assertTrue(first.exists()))
        self.e.close(); self.assertFalse(first.exists()); self.e.close()

    def test_dial_sets_tone_before_invite_and_windows_keeps_host_policy(self):
        self.e.prepare_call_media = Mock()
        self.e.address_new = Mock(return_value=1); self.e.core_create_call_params = Mock(return_value=2)
        for name in ('configure_call_audio', 'call_params_enable_video', 'call_params_set_media_encryption',
                     'call_params_unref', 'address_unref', 'hold_call'):
            setattr(self.e, name, Mock())
        def invite(*args):
            self.assertTrue(self.e.core_set_ringback.called)
            self.assertTrue(self.e.ringback_levels.path.exists())
            return 3
        self.e.core_invite_address_with_params = Mock(side_effect=invite)
        self.e.dial('sip:test@local')
        self.e.core_set_ringback.reset_mock()
        with patch.object(engine, 'WINDOWS', True): self.e.apply_ringback_volume()
        self.e.core_set_ringback.assert_not_called()

    def test_oversized_or_wrong_rate_is_rejected_without_replacing_good_tone(self):
        good = self.prepare()
        for data in (b'not a WAV', ringback_wav() + bytes(8000*2*31)):
            self.source.write_bytes(data)
            with self.assertRaises((ValueError, wave.Error, EOFError)): self.prepare()
            self.assertTrue(good.exists())
        self.source.write_bytes(ringback_wav())
        strict = ToneLevels()
        with self.assertRaises(ValueError): strict.prepare(self.source, 50)
