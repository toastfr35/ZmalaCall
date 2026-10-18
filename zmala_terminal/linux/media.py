"""C20 MJPEG/audio and Pi H.264 encoding; Windows keeps its SDK media path.

Device identity, rather than ALSA/V4L2 index, lets startup find a reconnected
C20 without a server edit. Native media policy lives here; SIP stays shared.
"""
import ctypes as C
import logging
from zmala_terminal.common.native_runtime import ROOT


def configure(engine):
    path = ROOT / 'linux/media/video/libzmala_video.so'
    if not path.is_file():
        raise RuntimeError('C20 media plugin is missing; run build_tools/linux/build-media.sh')
    # SDK callbacks retain pointers into this library until the core closes.
    engine.video_plugin = C.CDLL(str(path))
    frame_rate = engine.video_plugin.zmala_video_set_framerate
    frame_rate.argtypes, frame_rate.restype = [C.c_int], C.c_int
    if frame_rate(engine.video_settings.fps):
        raise RuntimeError('Could not set C20 video frame rate')
    factory = engine.dll.linphone_core_get_ms_factory
    factory.argtypes, factory.restype = [C.c_void_p], C.c_void_p
    for name in ('zmala_video_register', 'zmala_mjpeg_register', 'zmala_preview_register', 'zmala_framing_register'):
        register = getattr(engine.video_plugin, name)
        register.argtypes, register.restype = [C.c_void_p], C.c_int
        if register(factory(engine.core)):
            raise RuntimeError('Could not initialize C20 media: ' + name)
    reload_devices = engine.dll.linphone_core_reload_video_devices
    reload_devices.argtypes, reload_devices.restype = [C.c_void_p], None
    reload_devices(engine.core)
    from zmala_terminal.linux.auto_framing import AutoFraming
    engine.auto_framing = AutoFraming(engine.video_plugin, ROOT)
    engine.auto_framing.configure(engine.config.get('auto_framing', False))


# @llr LLR-TERM-MEDIA-005
def c20_devices(devices):
    """Exclude unrelated cameras and HDMI/default audio from Linux choices."""
    selected = {'camera': [name for name in devices['camera'] if name.startswith('ZmalaMJPEG:')]}
    for kind in ('microphone', 'speaker'):
        selected[kind] = [name for name in devices[kind] if 'Nuroum C20' in name]
    return selected


def settings(devices):
    selected = c20_devices(devices)
    missing = [kind for kind in ('camera', 'microphone', 'speaker') if not selected[kind]]
    if missing:
        # Never fall back to HDMI audio or a different webcam silently.
        raise RuntimeError('Nuroum C20 unavailable: ' + ', '.join(missing))
    return {kind: names[0] for kind, names in selected.items()}


def apply_speaker_volume(self):
    from zmala_terminal.linux.c20_volume import configure
    configure(self.config.get('c20_speaker_volume', 50))
    # C20's hardware 0% is -28 dB, not silence. Mute call playback too.
    self.sync_speaker_mute()


def sync_speaker_mute(self):
    from zmala_terminal.linux.c20_volume import status
    desired, _, _ = status()
    muted = desired == 0
    if getattr(self, '_speaker_muted', None) != muted:
        self.core_set_playback_gain_db(self.core, -120 if muted else 0)
        self._speaker_muted = muted


def refresh_usb_devices(self):
    if self.call and self.call_get_state(self.call) in (7, 8):
        return False  # Never replace device lists underneath running streams.
    for name in ('linphone_core_reload_sound_devices', 'linphone_core_reload_video_devices'):
        function = getattr(self.dll, name)
        function.argtypes, function.restype = [P], None
        function(self.core)
    self.apply_settings(self.config.get('terminal_settings', {}))
    from zmala_terminal.linux.c20_volume import reapply
    reapply()
    logging.info('C20 devices refreshed after USB wake')


CODECS = {'H264'}
DISPLAY_FILTER = b'ZmalaPreviewOGL'
P = C.c_void_p
filter_devices = c20_devices


def select_settings(engine, requested):
    return settings(engine.devices())


def received_frame(engine, params):
    # Debian OpenH264 reports decoded FPS but cannot re-arm frame callbacks.
    return engine.call_params_get_received_framerate(params) > 0


def poll_video(engine, now):
    pass
