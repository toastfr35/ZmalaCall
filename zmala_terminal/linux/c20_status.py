"""Read USB presence for first-run setup without opening the camera."""
import os
from pathlib import Path
import sys
import time


# @llr LLR-TERM-POWER-010, LLR-TERM-SETUP-022
def c20_connected(devices=Path('/sys/bus/usb/devices')):
    try:
        entries = list(devices.iterdir())
    except OSError:
        return None
    for device in entries:
        try:
            vendor = (device / 'idVendor').read_text().strip().lower()
            product = (device / 'idProduct').read_text().strip().lower()
            name = (device / 'product').read_text().strip().casefold()
            if (vendor, product) == ('0525', 'a4ad') and 'nuroum c20' in name:
                return True
        except OSError:
            continue  # USB interfaces and devices disappearing during enumeration.
    return False


class C20Status:
    def __init__(self):
        self.enabled = sys.platform == 'linux' and os.environ.get('ZMALA_C20_SETUP') == '1'
        self.next_read = 0
        self.connected = None

    def read(self):
        if not self.enabled:
            return None  # Desktop terminals can use other webcams.
        now = time.monotonic()
        if now >= self.next_read:
            self.next_read = now + .5
            self.connected = c20_connected()
        return self.connected
