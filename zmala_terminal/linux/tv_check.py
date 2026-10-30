"""Installation-only CEC operations. All waits and network I/O run off Tk."""
import hashlib
import ipaddress
import json
from pathlib import Path
import socket
import subprocess
import time
import urllib.request

from zmala_terminal.linux.cec_device import connector
from zmala_terminal.linux.tv_plugins.samsung.driver import connect, save_config


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class CheckTransport:
    def __init__(self, tv):
        self.tv = tv
        self.tv.pause_for_setup()
        self.address = None
        self.trial_key = None
        self.tv._network_enabled = False

    def probe(self, cancel):
        # Wait for any cancelled normal worker before dropping its TV lease.
        with self.tv._lock:
            self.tv._previous = self.tv._browse_previous = self.tv._restore_pending = None
            self.tv._changed = False
            self.tv._ready.set()
        self.tv._refresh_device()
        if not self.tv.command or not Path(self.tv.device).exists():
            return None
        with self.tv._lock:
            self.address = self.tv._physical_address()
        if not self.address:
            return None
        edid = b''
        mapping = connector(self.tv.device)
        if mapping:
            card, identifier = mapping
            for output in Path('/sys/class/drm').glob(f'card{card}-HDMI-A-*'):
                if int((output / 'connector_id').read_text()) == identifier:
                    edid = (output / 'edid').read_bytes()
                    break
        return {'address': self.address, 'display': hashlib.sha256(edid).hexdigest() if edid else None}

    def resume_network(self, enabled):
        self.tv._network_enabled = bool(enabled)
        if enabled:
            try:
                config = json.loads(self.tv._driver_config_file.read_text(encoding='utf-8'))
                if config.get('terminal_source', {}).get('address') != self.address:
                    self.trial_key = 'KEY_HDMI'
            except (OSError, ValueError, AttributeError):
                self.tv._network_enabled = False

    def run(self, cancel, *args):
        if cancel.is_set():
            raise InterruptedError()
        return self.tv._run(*args)

    def prepare(self, cancel):
        if self.run(cancel, '--physical-address').strip().lower() != self.address:
            raise RuntimeError('HDMI route changed during check')
        if self.run(cancel, '--logical-address').strip() not in ('4', '8', '11'):
            self.run(cancel, '--playback', '--cec-version-1.4', '--osd-name', 'ZmalaCall')

    # @llr LLR-TERM-TV-020
    def power(self, cancel):
        with self.tv._lock:
            self.prepare(cancel)
            failed = False
            try:
                try:
                    self.run(cancel, '--to', '0', '--standby')
                    deadline = time.monotonic() + 8
                    while time.monotonic() < deadline and not cancel.is_set():
                        reply = self.run(cancel, '--to', '0', '--give-device-power-status')
                        if 'pwr-state: standby (' in reply:
                            break
                        cancel.wait(.5)
                except (OSError, RuntimeError, subprocess.SubprocessError):
                    failed = True
                if cancel.wait(3):
                    return False
            finally:
                # Standby can succeed despite a lost acknowledgement. A single
                # failed wake must not prevent later wake attempts while active.
                woke = False
                for delay in (0, 2, 3, 3):
                    if cancel.wait(delay):
                        break
                    try:
                        self.run(cancel, '--to', '0', '--image-view-on')
                        self.run(cancel, '--active-source', 'phys-addr=' + self.address)
                        woke = True
                    except (OSError, RuntimeError, subprocess.SubprocessError):
                        pass
            if failed or not woke:
                raise RuntimeError('TV command acknowledgement incomplete')
        return True

    def select_terminal(self, cancel):
        error = None
        try:
            self.run(cancel, '--active-source', 'phys-addr=' + self.address)
        except (OSError, RuntimeError, subprocess.SubprocessError) as caught:
            error = caught
        trial = {'address': self.address, 'key': self.trial_key} if self.trial_key else None
        network = self.tv._driver_call('set_current_input', self.address,
                                       is_current=lambda: not cancel.is_set(), trial_source=trial)
        if error and not network:
            raise error

    # @llr LLR-TERM-TV-022
    def source(self, cancel):
        # Do not announce our source while waiting for the user to change it.
        deadline = time.monotonic() + 30
        previous = None
        while time.monotonic() < deadline and not cancel.is_set():
            previous = self.tv._previous_source()
            if previous and previous != self.address:
                break
            cancel.wait(.2)
        else:
            return False
        with self.tv._lock:
            self.prepare(cancel)
            try:
                self.select_terminal(cancel)
                if cancel.wait(3):
                    return False
                self.run(cancel, '--to', '0', '--inactive-source', 'phys-addr=' + self.address)
                if previous == '0.0.0.0':
                    self.tv._driver_call('set_current_input', '0.0.0.0',
                                         is_current=lambda: not cancel.is_set())
                else:
                    self.run(cancel, '--set-stream-path', 'phys-addr=' + previous)
                    self.run(cancel, '--active-source', 'phys-addr=' + previous)
                if cancel.wait(3):
                    return False
            finally:
                if not cancel.is_set():
                    self.select_terminal(cancel)
        return True

    def discover(self, cancel):
        """Discover candidates only; the user explicitly chooses which TV to pair."""
        hosts = set()
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(.3)
            sock.sendto(b'M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: "ssdp:discover"\r\nMX: 2\r\nST: ssdp:all\r\n\r\n', ('239.255.255.250', 1900))
            deadline = time.monotonic() + 4
            while time.monotonic() < deadline and not cancel.is_set():
                try:
                    packet, address = sock.recvfrom(8192)
                    if b'samsung' in packet.lower() and len(hosts) < 12:
                        hosts.add(str(ipaddress.ip_address(address[0])))
                except socket.timeout:
                    pass
        result = []
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        for host in sorted(hosts):
            if cancel.is_set():
                break
            try:
                # Never follow an advertised URL or redirects onto another host.
                request = urllib.request.Request(f'http://{host}:8001/api/v2/')
                with opener.open(request, timeout=1) as response:
                    if response.geturl() != request.full_url:
                        continue
                    device = json.loads(response.read(65536)).get('device', {})
                if isinstance(device.get('modelName'), str):
                    result.append({'host': host, 'name': str(device.get('name') or device['modelName'])[:80]})
            except (OSError, ValueError, TypeError, AttributeError):
                pass
        return result

    def pair(self, cancel, host):
        remote, config = connect(host, timeout=25)
        try:
            if not cancel.is_set():
                # Permission alone does not establish a working HDMI command.
                save_config(self.tv._driver_config_file, config)
                self.trial_key = 'KEY_HDMI'
                self.tv._network_enabled = True
        finally:
            remote.close(timeout=0)
        return True

    def confirm_source(self):
        if self.trial_key:
            path = self.tv._driver_config_file
            value = json.loads(path.read_text(encoding='utf-8'))
            value['terminal_source'] = {'address': self.address, 'key': self.trial_key}
            save_config(path, value)
