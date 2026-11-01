"""Keep received H.264 bytes intact before handing them to OpenH264."""
import ctypes as C
import math
from zmala_terminal.common.native_runtime import ROOT


def configure(resources, dll, core, fps, framing):
    path = ROOT.parent / 'build_tools/runtime/zmala-h264-decoder.dll'
    if not path.is_file():
        raise RuntimeError('H.264 decoder adapter is missing; run build_tools/build-h264-decoder.py')
    resources.video_plugin = C.CDLL(str(path))
    factory = dll.linphone_core_get_ms_factory
    factory.argtypes, factory.restype = [C.c_void_p], C.c_void_p
    register = resources.video_plugin.zmala_h264_decoder_register
    register.argtypes, register.restype = [C.c_void_p], C.c_int
    if register(factory(core)):
        raise RuntimeError('Could not initialize the Windows H.264 decoder')


def apply_speaker_volume(self):
    percent = self.config.get('c20_speaker_volume', 50)
    self.core_set_playback_gain_db(self.core, 20*math.log10(percent/100) if percent else -120)


def sync_speaker_mute(self, previous=None):
    return None


def refresh_usb_devices(self):
    return None


CODECS = {'VP8', 'H264'}
DISPLAY_FILTER = b'MSOGL'


def select_settings(engine, requested):
    return requested


def filter_devices(devices):
    return devices


def received_frame(engine, params):
    return False  # The SDK's decoded-frame callback is authoritative.


def poll_video(engine, now, next_probe=0):
    if engine.call and engine.call_get_state(engine.call) == 8 and now >= next_probe:
        # Re-arm on the UI thread, never recursively inside the native callback.
        engine.call_request_notify_next_video_frame_decoded(engine.call)
        return now + 1
    return next_probe
