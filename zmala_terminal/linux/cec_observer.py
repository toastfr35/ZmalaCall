"""Remember CEC routing without changing the TV or granting the UI privileges.

Linux monitor mode needs CAP_NET_ADMIN. A separate service has that capability
inside a private network namespace and publishes only routing state in /run.
The cache starts unknown after each observer restart; an unobserved input must
never be guessed from the Pi's own connector address.
"""
import argparse
import json
import os
from pathlib import Path
import re
import selectors
import subprocess
import time

try:
    from .cec_device import select_device
except ImportError:  # systemd executes this file directly.
    from cec_device import select_device

ADDRESS = r'[0-9a-fA-F](?:\.[0-9a-fA-F]){3}'


class RoutingState:
    def __init__(self):
        self.source = None
        self.message = None
        self.off = None
        self.tv_power_report = False

    def consume(self, line):
        """Only confirmed announcements/route changes update the cached input."""
        if line.startswith(('Received ', 'Transmitted ')):
            self.tv_power_report = 'Received from TV ' in line and 'REPORT_POWER_STATUS (0x90)' in line
            if 'STANDBY (0x36)' in line and (' to TV ' in line or ' to all ' in line):
                self.off = True
            elif 'IMAGE_VIEW_ON (0x04)' in line and ' to TV ' in line:
                self.off = False
            self.message = next((name for name in ('INACTIVE_SOURCE', 'ACTIVE_SOURCE', 'ROUTING_CHANGE', 'ROUTING_INFORMATION')
                                 if name + ' (' in line), None)
        elif self.message:
            key = 'new-phys-addr' if self.message == 'ROUTING_CHANGE' else 'phys-addr'
            match = re.search(r'\b' + key + r':\s*(' + ADDRESS + r')', line)
            if match:
                source = match[1].lower()
                if self.message == 'INACTIVE_SOURCE':
                    # Releasing an input does not announce the destination.
                    # Clear the old source rather than claiming the TV still
                    # displays it or guessing which source it returns to.
                    if source == self.source:
                        self.source = None
                elif source != 'f.f.f.f':
                    self.source = source
                self.message = None
        if self.tv_power_report and 'pwr-state: on (' in line:
            self.off = False
        elif self.tv_power_report and 'pwr-state: standby (' in line:
            self.off = True


def observe(device, destination, automatic=False):
    state = RoutingState()
    process = subprocess.Popen(['stdbuf', '-oL', 'cec-ctl', '-s', '-d', device, '--monitor'],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            pending = b''
            next_query = 0
            while process.poll() is None:
                if automatic and select_device(device) != device:
                    return  # Reopen on the connected port with unknown routing state.
                if state.source is None and time.monotonic() >= next_query:
                    # A responsive source can fill the initial unknown state.
                    # Samsung/no-device inputs may stay unknown until an actual
                    # routing announcement; this read-only request never guesses.
                    try:
                        subprocess.run(['cec-ctl', '-s', '-d', device, '--request-active-source'],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
                    except subprocess.TimeoutExpired:
                        pass
                    next_query = time.monotonic() + 20
                for key, _ in selector.select(timeout=1):
                    pending += os.read(key.fd, 65536)
                    lines = pending.split(b'\n')
                    pending = lines.pop()
                    for line in lines:
                        state.consume(line.decode('utf-8', errors='replace'))
                # A heartbeat distinguishes a remembered input from a dead
                # observer. Atomic replacement keeps readers out of partial JSON.
                temporary = destination.with_suffix('.tmp')
                temporary.write_text(json.dumps({'device': device, 'active_source': state.source,
                                                 'off': state.off, 'updated_at': time.time()}), encoding='utf-8')
                os.replace(temporary, destination)
        raise RuntimeError('CEC monitor stopped')
    finally:
        process.terminate()
        process.wait(timeout=5)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device', help='Fixed adapter; default follows the connected HDMI port')
    parser.add_argument('--state', type=Path, default=Path('/run/zmalacall-cec/state.json'))
    args = parser.parse_args()
    while True:
        observe(args.device or select_device(), args.state, automatic=args.device is None)
