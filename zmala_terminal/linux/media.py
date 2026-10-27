"""C20 MJPEG/audio and Pi H.264 encoding; Windows keeps its SDK media path.

Device identity, rather than ALSA/V4L2 index, lets startup find a reconnected
C20 without a server edit. Native media policy lives here; SIP stays shared.
"""
import ctypes as C
import logging
from zmala_terminal.common.native_runtime import ROOT
from zmala_terminal.common.media_errors import MediaNotReady


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


# @llr LLR-TERM-POWER-010
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
        raise MediaNotReady('Nuroum C20 unavailable: ' + ', '.join(missing))
    return {kind: names[0] for kind, names in selected.items()}


def apply_speaker_volume(self):
    from zmala_terminal.linux.c20_volume import configure
    configure(self.config.get('c20_speaker_volume', 50))
    # C20's hardware 0% is -28 dB, not silence. Mute call playback too.
    self.sync_speaker_mute()


def sync_speaker_mute(self):
    from zmala_terminal.linux.c20_volume import status
    from zmala_terminal.linux.sound_levels import gain_db
    desired, _, _ = status()
    # @llr LLR-TERM-AUDIO-010
    # Only the core owner touches this native call gain; other sounds bypass it.
    if desired is not None and getattr(self, '_speaker_percent', None) != desired:
        self.core_set_playback_gain_db(self.core, gain_db(desired))
        self._speaker_percent = desired


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


# @llr LLR-TERM-POWER-010
def bind_call_audio(engine):
    """Restore both future calls and an incoming call created while USB was off."""
    devices = engine.core_get_extended_audio_devices(engine.core)
    owned, selected = [], {}
    node = devices
    try:
        while node:
            device = node.contents.data
            owned.append(device)
            node = node.contents.next
        for device in owned:
            name = engine.audio_device_get_id(device) or b''
            capabilities = engine.audio_device_get_capabilities(device)
            if b'Nuroum C20' in name:
                for direction, capability in (('input', 1), ('output', 2)):
                    if capabilities & capability:
                        selected.setdefault(direction, device)
        if len(selected) != 2:
            raise MediaNotReady('Nuroum C20 audio is still waking')
        for direction, device in selected.items():
            getattr(engine, 'core_set_default_' + direction + '_audio_device')(engine.core, device)
            targets = [('core_get_default_', engine.core)]
            if engine.call:
                getattr(engine, 'call_set_' + direction + '_audio_device')(engine.call, device)
                targets.append(('call_get_', engine.call))
            for prefix, target in targets:
                effective = getattr(engine, prefix + direction + '_audio_device')(target)
                name = engine.audio_device_get_id(effective) if effective else None
                if name != engine.audio_device_get_id(device):
                    raise MediaNotReady('Nuroum C20 ' + direction + ' route is not ready')
            if engine.call:
                logging.info('C20 call %s route: %s', direction, name.decode(errors='replace'))
    finally:
        # The list owns one reference per entry; getters above return borrowed pointers.
        for device in owned:
            engine.audio_device_unref(device)
        engine.bctbx.bctbx_list_free(devices)


def received_frame(engine, params):
    # Debian OpenH264 reports decoded FPS but cannot re-arm frame callbacks.
    return engine.call_params_get_received_framerate(params) > 0


def poll_video(engine, now):
    pass
