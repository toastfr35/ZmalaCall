"""Run the window manager and shared terminal under systemd supervision.

The app runs as the configured unprivileged user. systemd owns the entire
session cgroup, so stop/restart also cleans up camera and command workers.
"""
import os
from pathlib import Path
import signal
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]


def wait_for_display():
    # Xorg's socket appears before initialization is complete. Wait for an
    # authenticated connection rather than a fixed startup delay.
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            result = subprocess.run(['xdpyinfo'], stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL, timeout=5)
            if result.returncode == 0:
                return
        except subprocess.TimeoutExpired:
            # Cold boot on a Pi 3 can accept the socket before Xorg answers.
            pass
        time.sleep(.5)
    raise RuntimeError('Physical X11 display did not become ready')


def display_outputs(query, mode):
    """Select only connected outputs advertising the requested mode."""
    output, supported = None, []
    for line in query.splitlines():
        match = re.match(r'^(\S+) connected\b', line)
        if match:
            output = match[1]
        elif line and not line[0].isspace():
            output = None
        elif output and line.split() and line.split()[0] == mode:
            supported.append(output)
    return supported


def configure_display():
    mode = os.environ.get('ZMALA_DISPLAY_MODE', '1280x720')
    if mode == 'auto':
        return
    query = subprocess.run(['xrandr', '--query'], capture_output=True, text=True, timeout=5, check=True)
    for output in display_outputs(query.stdout, mode):
        # xrandr chooses the closest advertised refresh rate to 60 Hz.
        subprocess.run(['xrandr', '--output', output, '--mode', mode, '--rate', '60'],
                       check=True, timeout=10)


def main():
    wait_for_display()
    configure_display()
    subprocess.run(['xset', 's', 'off'], check=True)
    subprocess.run(['xset', '-dpms'], check=True)
    manager = subprocess.Popen(['openbox'])
    child = None

    def stop(signum, frame):
        if child and child.poll() is None:
            child.terminate()

    signal.signal(signal.SIGTERM, stop)
    try:
        child = subprocess.Popen([sys.executable, str(ROOT / 'build_tools/linux/launcher.py'),
            'run', '--profile', 'terminal', '--fullscreen', '--wifi-mode',
            os.environ.get('ZMALA_WIFI_MODE', 'connect')], cwd=ROOT)
        return child.wait()
    finally:
        manager.terminate()
        try:
            manager.wait(timeout=5)
        except subprocess.TimeoutExpired:
            manager.kill()
            manager.wait()


if __name__ == '__main__':
    sys.exit(main())
