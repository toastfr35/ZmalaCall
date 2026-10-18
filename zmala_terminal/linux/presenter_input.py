"""Linux Presenter+ call buttons; normal navigation remains keyboard input.

BlueZ creates the input devices after pairing. Discover them again after a
reconnect and read only this remote, never the system keyboard or C20 buttons.
Tk file handlers dispatch on its UI thread without a polling worker.
"""
import logging
import os
from pathlib import Path
import struct
import tkinter as tk
from zmala_terminal.linux.remote_health import RemoteHealth

EVENT = struct.Struct('llHHi')
EV_KEY, BTN_0 = 1, 256


def navigation_events(data):
    """Read only Presenter evdev arrows/page keys, never the system keyboard."""
    for offset in range(0, len(data)-EVENT.size+1, EVENT.size):
        _, _, kind, code, value = EVENT.unpack_from(data, offset)
        button = {104: 'left', 105: 'left', 106: 'right', 109: 'right'}.get(code)
        if kind == EV_KEY and button and value in (0, 1):
            yield button, bool(value)


def teams_events(data):
    """Translate measured Teams press/release events, ignoring auto-repeat."""
    for offset in range(0, len(data)-EVENT.size+1, EVENT.size):
        _, _, kind, code, value = EVENT.unpack_from(data, offset)
        if kind == EV_KEY and code == BTN_0 and value in (0, 1):
            yield bool(value)


def button_report(data):
    """Accept measured Teams (04/3e) and Mute (04/3f) vendor reports.

    Teams is not always exposed as BTN_0. Prefer the raw
    reports for both buttons; pointer_report handles the separate volume gesture.
    """
    if len(data) == 8 and data[0] == 4 and data[1] in (0x3e, 0x3f) and data[2] in (0, 1):
        return ('red' if data[1] == 0x3e else 'green', bool(data[2]))
    return None


def pointer_report(data):
    """Measured Pointer hold (04/3d) and signed relative mouse Y (03)."""
    if len(data) == 8 and data[:2] == b'\x04\x3d' and data[2] in (0, 1):
        return 'held', bool(data[2])
    if len(data) == 10 and data[0] == 3:
        return 'motion', struct.unpack_from('<h', data, 4)[0]
    return None


class PresenterInput:
    def __init__(self, root, press, release, pointer=None, motion=None, observe=None):
        self.root, self.press, self.release = root, press, release
        self.pointer, self.motion = pointer, motion
        self.observe = observe
        self.pointer_fd = None
        self.devices = {}
        self.raw_fds = set()
        self.timer = None
        self.closed = False
        self.supported = os.name == 'posix' and hasattr(root, 'createfilehandler')
        self.health = RemoteHealth() if self.supported else None
        if self.supported:
            self.discover()

    @property
    def connected(self):
        """Input-device availability; None where this reader cannot monitor it."""
        return bool(self.devices) if self.supported else None

    @property
    def battery(self):
        return self.health.battery if self.connected and self.health else None

    @property
    def charger_connected(self):
        return self.health.charger_connected if self.connected and self.health else None

    @property
    def status(self):
        if not self.supported:
            return None
        if self.devices:
            return 'connected' if self.raw_fds and len(self.devices) > len(self.raw_fds) else 'input_unavailable'
        return self.health.state

    def discover(self):
        if self.closed:
            return
        for path, fd in list(self.devices.items()):
            if not Path(path).exists():
                self.remove(fd)
        for raw, folder, pattern in [(False, '/sys/class/input', 'event*'),
                                     (True, '/sys/class/hidraw', 'hidraw*')]:
            for device in Path(folder).glob(pattern):
                self.open_device(device, raw)
        self.timer = self.root.after(3000, self.discover)

    def open_device(self, device, raw):
        path = ('/dev/' if raw else '/dev/input/')+device.name
        if path in self.devices:
            return
        try:
            if raw:
                identity = (device/'device/uevent').read_text().splitlines()
                if ('HID_NAME=Microsoft Presenter+' not in identity or
                        'HID_ID=0005:0000045E:00000851' not in identity):
                    return
            elif not (device/'device/name').read_text().startswith('Microsoft Presenter+'):
                return
            fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
            try:
                self.root.createfilehandler(fd, tk.READABLE, self.read)
            except Exception:
                os.close(fd)
                raise
            self.devices[path] = fd
            if raw:
                self.raw_fds.add(fd)
        except OSError:
            pass  # Permission may be pending, or the device disconnected.

    def read(self, fd, _mask):
        try:
            data = os.read(fd, EVENT.size*64)
            if not data:
                self.remove(fd)
                return
            if fd in self.raw_fds:
                pointer = pointer_report(data)
                if pointer:
                    kind, value = pointer
                    if kind == 'held' and self.observe and self.observe('pointer', value):
                        return
                    if kind == 'held' and ((value and self.pointer_fd is None)
                                           or (not value and self.pointer_fd == fd)):
                        self.pointer_fd = fd if value else None
                        if self.pointer:
                            self.pointer(value)
                    elif kind == 'motion' and self.pointer_fd == fd and self.motion:
                        self.motion(value)
                event = button_report(data)
                events = [] if event is None else [event]
            else:
                if self.observe:
                    for button, pressed in navigation_events(data):
                        self.observe(button, pressed)
                # One physical press may also produce BTN_0. Only use this
                # fallback when raw HID access is unavailable.
                events = [] if self.raw_fds else [('red', pressed) for pressed in teams_events(data)]
            for button, pressed in events:
                if self.observe and self.observe(button, pressed):
                    continue
                logging.debug('Presenter %s %s', button, 'pressed' if pressed else 'released')
                (self.press if pressed else self.release)(button)
        except BlockingIOError:
            pass
        except OSError:
            self.remove(fd)
        except Exception:
            logging.exception('Presenter button handler failed')

    def remove(self, fd):
        if self.pointer_fd == fd:
            self.pointer_fd = None
            if self.pointer:
                self.pointer(False)
        self.root.deletefilehandler(fd)
        os.close(fd)
        self.raw_fds.discard(fd)
        self.devices = {path: value for path, value in self.devices.items() if value != fd}
        for button in ('green', 'red'):
            self.release(button)

    def close(self):
        self.closed = True
        if self.health:
            self.health.close()
        if self.timer is not None:
            self.root.after_cancel(self.timer)
        for fd in list(self.devices.values()):
            self.remove(fd)
