"""Opt-in Argon ONE Pi 4 fan: active calls only, I2C work outside Tk.

The V2 MCU accepts one duty-cycle byte (0..100) at bus 1, address 0x1a.
Never send its power-mode/shutdown commands. The case must be selected at install.
"""
import logging
import os
from pathlib import Path
import sys
import threading


def enabled():
    return sys.platform == 'linux' and os.environ.get('ZMALA_ARGON_ONE_FAN') == '1'


def fan_speed(active, temperature):
    if not active:
        return 0
    return 100 if temperature is not None and temperature >= 65 else 55


def temperature():
    try:
        return int(Path('/sys/class/thermal/thermal_zone0/temp').read_text()) / 1000
    except (OSError, ValueError):
        return None


def write_speed(speed):
    if type(speed) is not int or not 0 <= speed <= 100:
        raise ValueError('Fan duty cycle must be 0..100')
    import fcntl
    descriptor = os.open('/dev/i2c-1', os.O_RDWR | getattr(os, 'O_CLOEXEC', 0))
    try:
        fcntl.ioctl(descriptor, 0x0703, 0x1a)  # I2C_SLAVE, no force/scan
        if os.write(descriptor, bytes([speed])) != 1:
            raise OSError('Incomplete fan command')
    finally:
        os.close(descriptor)


class ArgonFan:
    def __init__(self):
        self.active = False
        self.stopped = False
        self.changed = threading.Event()
        self.worker = None
        if enabled():
            self.worker = threading.Thread(target=self.run, name='argon-fan', daemon=True)
            self.worker.start()

    def update(self, active):
        active = bool(active)
        if self.worker and active != self.active:
            self.active = active
            self.changed.set()

    def run(self):
        previous, failed = None, False
        try:
            while not self.stopped:
                self.changed.clear()
                speed = fan_speed(self.active, temperature())
                if speed != previous:
                    try:
                        write_speed(speed)
                        previous, failed = speed, False
                        logging.info('Argon fan duty cycle: %s%%', speed)
                    except OSError:
                        if not failed:
                            logging.warning('Argon fan unavailable; check I2C and case connection')
                        failed = True
                self.changed.wait(5)
        finally:
            try:
                write_speed(0)
            except OSError:
                logging.warning('Could not stop Argon fan')

    def close(self):
        self.stopped = True
        self.changed.set()
        if self.worker:
            self.worker.join(timeout=.2)


if __name__ == '__main__' and enabled():
    # systemd also calls this after an app crash, when Python cleanup cannot run.
    write_speed(0)
