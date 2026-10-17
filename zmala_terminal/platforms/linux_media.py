"""C20 MJPEG/audio and Pi H.264 encoding; Windows keeps its SDK media path.

Device identity, rather than ALSA/V4L2 index, lets startup find a reconnected
C20 without a server edit. Native media policy lives here; SIP stays shared.
"""
import ctypes as C
from platforms.native_runtime import ROOT


def configure(engine):
    path = ROOT / 'media/video/libzmala_video.so'
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
    from auto_framing import AutoFraming
    engine.auto_framing = AutoFraming(engine.video_plugin, ROOT)
    engine.auto_framing.configure(engine.config.get('auto_framing', False))


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
