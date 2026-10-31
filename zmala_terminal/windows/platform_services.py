"""Desktop substitutes for Pi-only power and television services.

Windows call ringing stays in the native call engine. These objects deliberately
perform no USB, CEC, I2C or background-thread work; they preserve the disabled
Pi adapters' externally visible behaviour used by the shared controllers.
"""
from pathlib import Path


class DesktopFan:
    def update(self, active):
        pass

    def close(self):
        pass


class DesktopTelevision:
    supports_setup = False
    power_enabled = True
    source_enabled = True

    def handle_button(self, on_visible, preserve_restore=False):
        return False  # The desktop already shows the UI; do not consume the press.

    def wake(self, restore=True, initial=None, ringing=None):
        pass

    def cancel(self, defer=False):
        pass

    def pause_for_setup(self):
        pass

    def browsing_session(self):
        return None

    def restore_browsing(self, session):
        pass

    def ready(self, now):
        return True

    def close(self):
        pass


class DesktopPower:
    enabled = False
    ready = True
    power_state = None
    state = 'unsupported'
    playback_active = False

    def __init__(self, root):
        self.ringing = False
        self.stopped = False
        self.ringtone_file = Path(root) / 'common/assets/gentle-chime.wav'
        self.ringtone_volume = 50
        self.ringtone_preview_status = ''

    def require(self, urgent=False):
        return True

    def refresh(self, engine):
        pass

    def update(self, active, battery, ringing=False):
        self.ringing = ringing

    def set_ringtone(self, file, percent=50):
        self.ringtone_file = Path(file)
        self.ringtone_volume = percent

    def preview_tone(self, file):
        # Desktop previews were not played by the disabled Linux adapter either.
        if not self.ringing and not self.stopped:
            self.ringtone_preview_status = 'waiting'

    def stop_preview(self):
        self.ringtone_preview_status = ''

    def stop_ringing(self):
        self.ringing = False
        self.stop_preview()

    def close(self):
        self.stopped = True
        self.stop_ringing()
