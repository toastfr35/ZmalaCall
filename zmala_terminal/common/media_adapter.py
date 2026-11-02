"""Own native plugin lifetime and platform media bookkeeping.

The engine supplies native operations on its owner thread. This adapter owns
plugin/framing references; shutdown stops framing before the core and retains the
plugin until the core has released every native filter callback.
"""


class MediaAdapter:
    def __init__(self, backend):
        self.backend = backend
        self.video_plugin = None
        self.auto_framing = None
        self.speaker_percent = None
        self.next_video_probe = 0

    # @llr LLR-TERM-START-005, LLR-TERM-AUDIO-004
    def configure(self, dll, core, fps, framing):
        self.backend.configure(self, dll, core, fps, framing)

    def configure_framing(self, enabled):
        if self.auto_framing:
            self.auto_framing.configure(enabled)

    @property
    def framing_status(self):
        return self.auto_framing.status if self.auto_framing else 'unsupported'

    def apply_volume(self, native):
        self.backend.apply_speaker_volume(native)

    def refresh(self, native):
        return self.backend.refresh_usb_devices(native)

    def sync_volume(self, native):
        self.speaker_percent = self.backend.sync_speaker_mute(native, self.speaker_percent)

    def poll_video(self, native, now):
        self.next_video_probe = self.backend.poll_video(native, now, self.next_video_probe)

    def codec_stats(self):
        return self.backend.codec_stats(self)

    # @llr LLR-TERM-START-005
    def stop(self):
        if self.auto_framing:
            self.auto_framing.close()
            self.auto_framing = None

    def release(self):
        """Call only after native core unref; failed teardown retains the plugin."""
        self.video_plugin = None
