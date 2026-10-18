"""Read-only BlueZ diagnostics, kept off the Tk/media iteration thread."""
import os
from pathlib import Path
import re
import subprocess
import threading
import time


def battery_percentage(info):
    match = re.search(r'^\s*Battery Percentage: (?:0x([0-9a-fA-F]+)(?: \(\d+\))?|(\d+))\s*$', info, re.M)
    if not match:
        return None
    value = int(match[1], 16) if match[1] else int(match[2])
    return value if 0 <= value <= 100 else None


# @llr TLLR019
def charger_connected(report):
    """Presenter+ 0x39/0x03 status: measured 0x20 on power, 0x00 off power.

    This identifies an attached charger, including a full battery, not current
    flowing into the battery. Unknown firmware/report shapes stay unknown.
    """
    if len(report) in (7, 8) and report[:2] == b'\x39\x03' and report[2] in (0, 0x20) and not any(report[3:]):
        return bool(report[2] & 0x20)
    return None


def remote_charger_connected():
    """Read current status off the UI thread, including when already docked.

    GETINPUTREPORT is read-only and does not consume the app's button events.
    Unsupported kernels/devices and disconnections return unknown.
    """
    try:
        import fcntl
        matches = []
        for device in Path('/sys/class/hidraw').glob('hidraw*'):
            identity = (device / 'device/uevent').read_text().splitlines()
            if ('HID_NAME=Microsoft Presenter+' in identity and
                    'HID_ID=0005:0000045E:00000851' in identity):
                matches.append(device.name)
        if len(matches) != 1:
            return None
        fd = os.open('/dev/' + matches[0], os.O_RDONLY | os.O_NONBLOCK)
        try:
            report = bytearray([0x39] + [0xff] * 7)
            # Linux HIDIOCGINPUT(8), _IOC(READ|WRITE, 'H', 0x0a, 8).
            result = fcntl.ioctl(fd, (3 << 30) | (8 << 16) | (ord('H') << 8) | 0x0a, report, True)
            return charger_connected(report[:result]) if result in (7, 8) else None
        finally:
            os.close(fd)
    except (ImportError, OSError):
        return None


def bluetooth_snapshot(run=None):
    """Absence is not evidence of power-off, battery failure or broken hardware."""
    def command(*args):
        if run:
            return run(*args)
        return subprocess.run(['bluetoothctl', *args], capture_output=True, text=True,
                              timeout=3, check=True, env=dict(os.environ, LC_ALL='C')).stdout

    def flag(output, name):
        match = re.search(r'^\s*' + name + r': (yes|no)\s*$', output, re.M)
        return match[1] == 'yes' if match else None

    try:
        adapter = command('show')
        powered = flag(adapter, 'Powered')
        if powered is False or 'No default controller available' in adapter:
            return 'bluetooth_unavailable', None
        if powered is None:
            return 'unknown', None
        listing = command('devices')
        if listing.strip() and not any(line.startswith('Device ') for line in listing.splitlines()):
            return 'unknown', None
        addresses = re.findall(r'^Device ([0-9A-Fa-f:]{17}) Microsoft Presenter\+\s*$', listing, re.M)
        states = []
        battery = None
        for address in addresses[:4]:
            info = command('info', address)
            paired, connected = flag(info, 'Paired'), flag(info, 'Connected')
            if paired is None or connected is None:
                states.append('unknown')
            elif flag(info, 'Blocked') is True:
                states.append('blocked')
            elif connected:
                states.append('input_unavailable')
                if battery is None:
                    battery = battery_percentage(info)
            else:
                states.append('disconnected' if paired else 'unpaired')
        # Any usable pairing takes precedence over other cached remotes.
        return next((state for state in ('input_unavailable', 'disconnected', 'unknown', 'blocked')
                     if state in states), 'unpaired'), battery
    except (OSError, subprocess.SubprocessError):
        return 'unknown', None


def bluetooth_state(run=None):
    return bluetooth_snapshot(run)[0]


class RemoteHealth:
    def __init__(self):
        self.snapshot = ('unknown', None, None, 0.)
        self.stopped = threading.Event()
        threading.Thread(target=self.watch, name='remote-health', daemon=True).start()

    def watch(self):
        while not self.stopped.is_set():
            state, battery = bluetooth_snapshot()
            charger = remote_charger_connected() if state == 'input_unavailable' else None
            self.snapshot = (state, battery, charger, time.monotonic())
            self.stopped.wait(5)

    # @llr TLLR018
    @property
    def state(self):
        return self.snapshot[0]

    @property
    def battery(self):
        _, battery, _, updated = self.snapshot
        return battery if time.monotonic() - updated < 20 else None

    @property
    def charger_connected(self):
        _, _, charger, updated = self.snapshot
        return charger if time.monotonic() - updated < 20 else None

    def close(self):
        self.stopped.set()
