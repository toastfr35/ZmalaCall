# @test T-LLT-079
# @requirements LLR-TERM-AUDIO-003
# @environment portable
# @plan Record the environment at SDK loading and reject a missing audio policy. On Linux, load the real ALSA configuration and expand the C10 and C20 PCM with two supplied card IDs without opening hardware. Inspect asymmetric routing, plug conversion, hardware device, rates, channels and format for both directions. Confirm the distribution sysdefault definition remains present. No SDK, USB device or audio stream is opened.
# @pass Policy precedes SDK loading; missing policy fails explicitly. Real ALSA expansion selects 16 kHz capture and 48 kHz playback, stereo S16_LE on the supplied card rather than a dsnoop buffer. A skipped native parser test is not a hardware or parser pass.
import ctypes as C
import ctypes.util
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from zmala_terminal.linux import native_runtime

POLICY = Path(native_runtime.__file__).parent / 'media/audio/c20-alsa.conf'


class C20PcmTests(unittest.TestCase):
    def test_policy_is_selected_before_sdk_loading(self):
        with patch.dict(os.environ, {'ALSA_CONFIG_PATH': '/obsolete/config'}), \
                patch.object(native_runtime, 'library',
                             side_effect=lambda name: (name, os.environ['ALSA_CONFIG_PATH'])):
            self.assertEqual(native_runtime.load_linphone(None), ('linphone', str(POLICY)))

    def test_missing_policy_does_not_silently_use_generic_audio(self):
        with patch.object(native_runtime.Path, 'is_file', return_value=False), \
                patch.object(native_runtime, 'library') as load:
            with self.assertRaisesRegex(RuntimeError, 'C20 audio policy is missing'):
                native_runtime.load_linphone(None)
            load.assert_not_called()

    @unittest.skipUnless(sys.platform.startswith('linux'), 'Real ALSA parser requires Linux')
    def test_real_alsa_expansion_uses_each_hardware_rate_and_current_card(self):
        # Private configuration tree: do not update libasound's global cache.
        library = ctypes.util.find_library('asound')
        if not library:
            self.skipTest('libasound is not installed')
        alsa = C.CDLL(library)
        pointer = C.c_void_p
        signatures = {
            'snd_config_top': [C.POINTER(pointer)],
            'snd_input_stdio_open': [C.POINTER(pointer), C.c_char_p, C.c_char_p],
            'snd_config_load': [pointer, pointer],
            'snd_input_close': [pointer],
            'snd_config_delete': [pointer],
            'snd_config_search': [pointer, C.c_char_p, C.POINTER(pointer)],
            'snd_config_expand': [pointer, pointer, C.c_char_p, pointer, C.POINTER(pointer)],
            'snd_config_get_string': [pointer, C.POINTER(C.c_char_p)],
            'snd_config_get_integer': [pointer, C.POINTER(C.c_long)],
        }
        for name, arguments in signatures.items():
            function = getattr(alsa, name)
            function.argtypes, function.restype = arguments, C.c_int
        tree, source = pointer(), pointer()
        self.assertEqual(alsa.snd_config_top(C.byref(tree)), 0)
        try:
            self.assertEqual(alsa.snd_input_stdio_open(C.byref(source), os.fsencode(POLICY), b'r'), 0)
            try:
                self.assertEqual(alsa.snd_config_load(tree, source), 0)
            finally:
                alsa.snd_input_close(source)

            def node(root, path):
                found = pointer()
                self.assertEqual(alsa.snd_config_search(root, path.encode(), C.byref(found)), 0, path)
                return found

            def value(root, path, integer=False):
                result = C.c_long() if integer else C.c_char_p()
                getter = alsa.snd_config_get_integer if integer else alsa.snd_config_get_string
                self.assertEqual(getter(node(root, path), C.byref(result)), 0, path)
                return result.value if integer else result.value.decode()

            node(tree, 'pcm.sysdefault')
            for card in ('C20', 'C10', '7'):
                definition = node(tree, 'cards.USB-Audio.Nuroum ' + ('C10' if card == 'C10' else 'C20') + '.pcm.default')
                expanded = pointer()
                self.assertGreaterEqual(alsa.snd_config_expand(definition, tree, ('CARD='+card).encode(),
                                                              None, C.byref(expanded)), 0)
                try:
                    self.assertEqual(value(expanded, 'type'), 'asym')
                    for direction, rate in (('capture', 16000), ('playback', 48000)):
                        with self.subTest(card=card, direction=direction):
                            base = direction + '.pcm'
                            self.assertEqual(value(expanded, base+'.type'), 'plug')
                            self.assertEqual(value(expanded, base+'.slave.pcm.type'), 'hw')
                            self.assertEqual(value(expanded, base+'.slave.pcm.card'), card)
                            self.assertEqual(value(expanded, base+'.slave.pcm.device', True), 0)
                            self.assertEqual(value(expanded, base+'.slave.rate', True), rate)
                            self.assertEqual(value(expanded, base+'.slave.channels', True), 2)
                            self.assertEqual(value(expanded, base+'.slave.format'), 'S16_LE')
                finally:
                    alsa.snd_config_delete(expanded)
        finally:
            alsa.snd_config_delete(tree)


if __name__ == '__main__':
    unittest.main()
