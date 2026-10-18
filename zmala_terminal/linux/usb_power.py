"""Opt-in shared USB power; blocking hub work never runs on the media/UI thread."""
import logging
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

IDLE_SECONDS = 300
HELPER = '/usr/local/libexec/zmala-usb-power'


def should_power_off(now, last_use, active, battery):
    return (not active and type(battery) is int and 25 < battery <= 100
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
    def __init__(self, root):
        self.enabled = sys.platform == 'linux' and os.environ.get('ZMALA_USB_POWER') == '1'
        self.root = root
        self.lock = threading.RLock()
        self.changed = threading.Event()
        self.stopped = False
        self.active, self.battery, self.ringing = True, None, False
        self.updated = self.last_use = time.monotonic()
        self.state = 'starting' if self.enabled else 'unsupported'
        self.revision = self.refreshed = 0
        self.next_refresh = 0
        self.ringer = None
        self.next_ring = 0
        self.worker = None
        if self.enabled:
            self.worker = threading.Thread(target=self.run, name='usb-power', daemon=True)
            self.worker.start()

    @property
    def ready(self):
        with self.lock:
            return not self.enabled or self.state == 'on' and self.revision == self.refreshed

    def update(self, active, battery, ringing=False):
        if not self.enabled:
            return
        now = time.monotonic()
        with self.lock:
            changed = (active, battery, ringing) != (self.active, self.battery, self.ringing)
            self.active, self.battery, self.ringing, self.updated = active, battery, ringing, now
            if active:
                self.last_use = now
        if changed:
            self.changed.set()

    def require(self):
        if self.enabled:
            with self.lock:
                self.last_use = time.monotonic()
                self.active = True
            self.changed.set()
        return self.ready

    def stop_ringing(self):
        with self.lock:
            self.ringing = False
            if self.ringer and self.ringer.poll() is None:
                self.ringer.terminate()
                try:
                    self.ringer.wait(timeout=.3)
                except subprocess.TimeoutExpired:
                    self.ringer.kill()
            self.ringer = None

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

    def command(self, action):
        subprocess.run(['sudo', '-n', HELPER, action], check=True,
                       capture_output=True, timeout=30, text=True)

    def run(self):
        next_attempt = 0
        next_status = 0
        try:
            while not self.stopped:
                self.changed.clear()
                now = time.monotonic()
                with self.lock:
                    # A stalled UI or stale battery must never leave the charger off.
                    active = self.active or now - self.updated > 10
                    off = should_power_off(now, self.last_use, active, self.battery)
                    desired = 'off' if off else 'on'
                    state = self.state
                    if now >= next_status:
                        folder = os.environ.get('ZMALA_RUNTIME_DIR')
                        if folder:
                            try:
                                path = Path(folder) / 'usb-power.json'
                                temporary = path.with_suffix('.tmp')
                                temporary.write_text(json.dumps({'state': state, 'battery': self.battery,
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
                        self.state = 'switching'
                    try:
                        self.stop_ringing()
                        self.command(desired)
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
                        logging.info('USB power %s', desired)
                    except Exception as error:
                        logging.warning('USB power %s failed: %s', desired, error)
                        # A failed off attempt restores power in the helper. Refresh
                        # device lists even after a rollback may have re-enumerated it.
                        with self.lock:
                            self.state = 'on' if media_present() else 'error'
                            self.revision += 1
                        next_attempt = time.monotonic() + 10
                    continue
                with self.lock:
                    ring = self.ringing and self.ready
                    if ring:
                        from zmala_terminal.linux.c20_volume import status
                        desired_volume, applied_volume, failed = status()
                        ring = desired_volume is not None and applied_volume == desired_volume and not failed
                        # The C20's 0% mixer floor is not digital silence.
                        ring = ring and desired_volume > 0
                    if ring and now >= self.next_ring and (not self.ringer or self.ringer.poll() is not None):
                        self.ringer = subprocess.Popen(['aplay', '-q', '-D', 'plughw:C20,0',
                            str(self.root / 'common/assets/gentle-chime.wav')],
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        self.next_ring = now + 3
                    elif not ring and self.ringer:
                        self.stop_ringing()
                self.changed.wait(.2)
        finally:
            self.stop_ringing()
            try:
                self.command('on')
            except Exception:
                logging.exception('Could not restore USB power; systemd cleanup will retry')

    def close(self):
        self.stopped = True
        self.changed.set()
        self.stop_ringing()
