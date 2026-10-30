"""Opt-in shared USB power; blocking hub work never runs on the media/UI thread."""
import logging
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import wave
from zmala_terminal.linux.sound_levels import ToneLevels, playback_environment

IDLE_SECONDS = 300
HELPER = '/usr/local/libexec/zmala-usb-power'


# @llr LLR-TERM-POWER-013, LLR-TERM-POWER-014
def should_power_off(now, last_use, active, battery):
    return (not active and type(battery) is int and 25 <= battery <= 100
            and now - last_use >= IDLE_SECONDS)


def media_present():
    """Require both V4L2 and ALSA after re-enumeration, not just a USB descriptor."""
    try:
        video = any('1-1.' in str(p.resolve()) and
                    'nuroum c20' in (p / 'name').read_text().lower()
                    for p in Path('/sys/class/video4linux').glob('video*'))
        audio = any(p.read_text().strip() == 'C20' for p in Path('/proc/asound').glob('card*/id'))
        return video and audio
    except OSError:
        return False


class UsbPower:
    # @llr LLR-TERM-POWER-012
    def __init__(self, root):
        self.enabled = sys.platform == 'linux' and os.environ.get('ZMALA_USB_POWER') == '1'
        self.root = root
        self.lock = threading.RLock()
        self.changed = threading.Event()
        self.stopped = False
        self.active, self.battery, self.ringing = True, None, False
        self.updated = self.last_use = time.monotonic()
        self.state = 'starting' if self.enabled else 'unsupported'
        self.powered = None  # Confirmed supply state, independent of camera readiness.
        self.wake_serial = 0
        self.activity_reason = self.last_request_reason = 'startup'
        self.revision = self.refreshed = 0
        self.next_refresh = 0
        self.ringer = None
        self.ringtone_file = self.root / 'common/assets/gentle-chime.wav'
        self.ringtone_volume = 50
        self.tone_levels = ToneLevels()
        self.preview_file, self.preview_state = None, ''
        self.preview_serial, self.preview_started = 0, None
        self.playback_key = None
        self.next_ring = 0
        self.worker = None
        if self.enabled:
            self.worker = threading.Thread(target=self.run, name='usb-power', daemon=True)
            self.worker.start()

    @property
    def ready(self):
        with self.lock:
            return not self.enabled or self.state == 'on' and self.revision == self.refreshed

    # @llr LLR-TERM-POWER-017
    @property
    def power_state(self):
        with self.lock:
            return self.powered

    def update(self, active, battery, ringing=False, *, reason='terminal activity'):
        if not self.enabled:
            with self.lock:
                self.ringing = ringing
                if ringing and self.worker is None and sys.platform == 'linux':
                    self.worker = threading.Thread(target=self.preview_worker, name='ringtone-player', daemon=True)
                    self.worker.start()
            self.changed.set()
            return
        now = time.monotonic()
        with self.lock:
            changed = (active, battery, ringing) != (self.active, self.battery, self.ringing)
            was_active = self.active
            self.active, self.battery, self.ringing, self.updated = active, battery, ringing, now
            if active:
                self.activity_reason = reason
            if active or was_active:
                self.last_use = now
        if changed:
            self.changed.set()

    # @llr LLR-TERM-POWER-013, LLR-TERM-POWER-014
    def require(self, urgent=False, *, reason='media preparation'):
        """Record activity and wake the worker; never perform USB I/O on the caller."""
        if self.enabled:
            with self.lock:
                self.last_use = time.monotonic()
                self.active = True
                self.activity_reason = self.last_request_reason = reason
                if urgent:
                    self.wake_serial += 1
            self.changed.set()
        return self.ready

    def stop_ringing(self):
        with self.lock:
            self.ringing = False
            self.preview_file, self.preview_state = None, ''
            self.stop_playback()

    def stop_playback(self):
        with self.lock:
            if self.ringer and self.ringer.poll() is None:
                self.ringer.terminate()
                try:
                    self.ringer.wait(timeout=.3)
                except subprocess.TimeoutExpired:
                    self.ringer.kill()
            self.ringer = None
            self.playback_key = None

    # @llr LLR-TERM-AUDIO-009
    def set_ringtone(self, file, percent=50):
        with self.lock:
            self.ringtone_file = Path(file)
            self.ringtone_volume = percent

    def preview_tone(self, file):
        with self.lock:
            if self.ringing or self.stopped:
                return
            self.preview_file, self.preview_state = Path(file), 'waiting'
            self.preview_serial += 1
            self.preview_started = None
            if not self.enabled and self.worker is None and sys.platform == 'linux':
                self.worker = threading.Thread(target=self.preview_worker, name='ringtone-preview', daemon=True)
                self.worker.start()
        self.require(reason='ringtone preview')
        self.changed.set()

    # @llr LLR-TERM-AUDIO-009
    def preview_worker(self):
        """Preview also works when the host disables USB power switching."""
        while not self.stopped:
            self.changed.clear()
            self.play_tone(time.monotonic())
            with self.lock:
                if self.preview_file is None and not self.ringing:
                    self.worker = None
                    return
            self.changed.wait(.2)
        self.stop_playback()

    def stop_preview(self):
        with self.lock:
            self.preview_file, self.preview_state = None, ''
        self.changed.set()

    @property
    def ringtone_preview_status(self):
        with self.lock:
            return self.preview_state

    @property
    def playback_active(self):
        with self.lock:
            return self.ringer is not None and self.ringer.poll() is None

    # @llr LLR-TERM-AUDIO-009
    def play_tone(self, now):
        """One worker owns playback; incoming calls supersede bounded previews."""
        with self.lock:
            if self.ringing:
                self.preview_file, self.preview_state = None, ''
            preview = self.preview_file is not None
            requested = self.ringing or preview
            eligible = requested and self.ready
            if eligible:
                from zmala_terminal.linux.c20_volume import status
                desired, applied, failed = status()
                # Call mute must not mute ringing. Hardware gain is fixed at 100%.
                eligible = applied is not None and not failed and self.ringtone_volume > 0
                if preview and self.ringtone_volume == 0:
                    self.preview_state = 'muted'
            if not eligible:
                self.stop_playback()
                return
            key = (('preview', self.preview_serial) if preview else ('ring', self.ringtone_file)) + (self.ringtone_volume,)
            if self.playback_key != key:
                self.stop_playback()
                self.playback_key, self.next_ring = key, 0
            if preview and self.preview_started is not None and (
                    now-self.preview_started >= 10 or self.ringer and self.ringer.poll() is not None):
                result = self.ringer.poll() if self.ringer else 0
                self.stop_playback()
                self.preview_file = None
                self.preview_state = 'error' if result not in (None, 0) else ''
                return
            if now >= self.next_ring and (not self.ringer or self.ringer.poll() is not None):
                try:
                    file = self.tone_levels.prepare(self.preview_file if preview else self.ringtone_file,
                                                   self.ringtone_volume)
                    self.ringer = subprocess.Popen(['/usr/bin/aplay', '-q', '-D', 'default:C20', str(file)],
                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        env=playback_environment())
                except (OSError, ValueError, EOFError, wave.Error):
                    logging.exception('Could not start ringtone playback')
                    if preview:
                        self.preview_file, self.preview_state = None, 'error'
                self.next_ring = now + 3
                if preview and self.ringer:
                    self.preview_started, self.preview_state = now, 'playing'

    # @llr LLR-TERM-POWER-015
    def refresh(self, engine):
        """Run native device-list refresh only on the thread owning the core."""
        if not self.enabled:
            return
        with self.lock:
            if self.state != 'on' or self.refreshed == self.revision:
                return
            if time.monotonic() < self.next_refresh:
                return
            if engine:
                try:
                    refreshed = engine.refresh_usb_devices()
                except (RuntimeError, OSError) as error:
                    # Sysfs appears before udev/SDK enumeration has settled.
                    # Keep pumping SIP/UI events while waiting for the devices.
                    logging.info('Waiting for C20 device refresh: %s', error)
                    self.next_refresh = time.monotonic() + 1
                    return
                if refreshed is False:
                    return
            self.refreshed = self.revision

    # @llr LLR-TERM-POWER-016
    def power_reason(self, now):
        """Explain the existing policy without altering its power decision."""
        if now - self.updated > 10:
            return 'UI heartbeat stale (over 10 seconds); keep charger powered'
        if self.active:
            return self.activity_reason
        if type(self.battery) is not int or not 0 <= self.battery <= 100:
            return 'remote battery unknown; keep charger powered'
        if self.battery < 25:
            return 'remote battery below 25%; keep charger powered'
        if now - self.last_use < IDLE_SECONDS:
            return 'activity within five-minute idle timeout'
        return 'idle timeout reached; remote battery sufficient'

    def command(self, action):
        try:
            result = subprocess.run(['sudo', '-n', HELPER, action], check=True,
                       capture_output=True, timeout=30, text=True)
        except subprocess.CalledProcessError as error:
            # The helper can restore power after a failed off; don't hide that
            # explanation inside captured stderr.
            logging.warning('C10/C20 USB helper: %s', (error.stderr or '').strip())
            raise
        if result.stderr:
            logging.info('C10/C20 USB helper: %s', result.stderr.strip())

    # @llr LLR-TERM-POWER-016
    def run(self):
        next_attempt = 0
        next_status = 0
        handled_wake = 0
        try:
            while not self.stopped:
                self.changed.clear()
                now = time.monotonic()
                with self.lock:
                    if handled_wake != self.wake_serial:
                        handled_wake = self.wake_serial
                        next_attempt = 0  # New user/call activity bypasses a failed attempt's backoff.
                    # A stalled UI or stale battery must never leave the charger off.
                    active = self.active or now - self.updated > 10
                    off = should_power_off(now, self.last_use, active, self.battery)
                    desired = 'off' if off else 'on'
                    state = self.state
                    reason = self.power_reason(now)
                    context = (self.battery, now-self.last_use, now-self.updated, self.last_request_reason)
                    if now >= next_status:
                        folder = os.environ.get('ZMALA_RUNTIME_DIR')
                        if folder:
                            try:
                                path = Path(folder) / 'usb-power.json'
                                temporary = path.with_suffix('.tmp')
                                temporary.write_text(json.dumps({'state': state, 'powered': self.powered, 'battery': self.battery,
                                    'active': active, 'idle_seconds': round(now-self.last_use, 1)}))
                                temporary.replace(path)
                            except OSError:
                                pass  # Diagnostics must not interfere with power recovery.
                        next_status = now + 5
                if desired != state and now >= next_attempt:
                    with self.lock:
                        # A call may request wake after this worker's snapshot.
                        # Claim the transition under the same lock as require().
                        if desired == 'off' and not should_power_off(time.monotonic(), self.last_use,
                                self.active or time.monotonic() - self.updated > 10, self.battery):
                            continue
                        if state == 'starting':
                            reason = 'startup: ' + reason
                        elif state == 'error':
                            reason = 'retry after failed transition: ' + reason
                        logging.info('C10/C20 USB power %s requested: reason=%s; previous=%s; '
                                     'battery=%r; idle=%.1fs; update_age=%.1fs; last_request=%s',
                                     desired, reason, state, *context)
                        self.state = 'switching'
                        self.powered = None
                    try:
                        self.stop_playback()
                        self.command(desired)
                        with self.lock:
                            self.powered = desired == 'on'
                        if desired == 'on':
                            deadline = time.monotonic() + 15
                            while not self.stopped and not media_present() and time.monotonic() < deadline:
                                time.sleep(.2)
                            if not media_present():
                                raise RuntimeError('C20 did not return after USB wake')
                        with self.lock:
                            self.state = desired
                            if desired == 'on':
                                self.revision += 1
                        logging.info('C10/C20 USB power %s completed: reason=%s', desired, reason)
                    except Exception as error:
                        logging.warning('C10/C20 USB power %s failed: reason=%s; error=%s', desired, reason, error)
                        # A failed off attempt restores power in the helper. Refresh
                        # device lists even after a rollback may have re-enumerated it.
                        with self.lock:
                            # Device presence cannot prove both hubs are powered.
                            # Keep wake retryable even if rollback left the C20 visible.
                            self.state = 'error'
                            self.revision += 1
                        next_attempt = time.monotonic() + 10
                    continue
                self.play_tone(now)
                self.changed.wait(.2)
        finally:
            self.stop_ringing()
            try:
                logging.info('C10/C20 USB power on requested: reason=worker shutdown; restore charger power')
                self.command('on')
                logging.info('C10/C20 USB power on completed: reason=worker shutdown')
            except Exception:
                logging.exception('Could not restore USB power; systemd cleanup will retry')

    def close(self):
        self.stopped = True
        self.changed.set()
        self.stop_ringing()
        self.tone_levels.close()
