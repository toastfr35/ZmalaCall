#!/usr/bin/python3
"""Fixed Pi 4 USB power helper. Installed root-owned; no arbitrary commands/paths."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import stat
import sys

USB = Path('/sys/bus/usb/devices')


# @llr LLR-TERM-MAINT-028
def maintenance_active(path=Path('/run/zmalacall-updater/state.json'), root_uid=0):
    """Cleanup must retain a root maintenance fence even after producer failure."""
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor, 'r', encoding='utf-8') as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != root_uid
                    or info.st_mode & 0o022 or info.st_size > 8192):
                return False
            state = json.loads(stream.read(8193))
        return (state.get('phase') in ('updating', 'checking', 'rollback', 'recovery_failed')
                and isinstance(state.get('nonce'), str)
                and re.fullmatch('[a-f0-9]{32}', state['nonce']) is not None)
    except (OSError, ValueError, TypeError, AttributeError):
        return False


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=12)


def devices():
    found = []
    for path in USB.iterdir():
        if not (path / 'idVendor').exists():
            continue
        identity = tuple((path / name).read_text().strip().lower() for name in ('idVendor', 'idProduct'))
        kind = (path / 'bDeviceClass').read_text().strip()
        if kind != '09':  # The only supported peripheral is the C20; never cut USB storage.
            found.append((path, identity))
    return found


def validate_board():
    if not Path('/proc/device-tree/model').read_bytes().startswith(b'Raspberry Pi 4 Model B'):
        raise RuntimeError('USB power experiment requires Raspberry Pi 4 Model B')
    for hub, identity in [('1-1', ('2109', '3431')), ('usb2', ('1d6b', '0003'))]:
        actual = tuple((USB / hub / name).read_text().strip() for name in ('idVendor', 'idProduct'))
        if actual != identity:
            raise RuntimeError('Unexpected USB hub topology')


def switch(action):
    # -e avoids implicitly switching the companion hub a second time.
    for hub in ('1-1', '2'):
        run('/usr/sbin/uhubctl', '-e', '-l', hub, '-a', action)
        # @llr LLR-TERM-POWER-017
        # A successful process exit alone does not prove port power changed.
        result = run('/usr/sbin/uhubctl', '-e', '-l', hub)
        states = re.findall(r'^\s*Port \d+: [0-9a-fA-F]+ (.*)$', result.stdout, re.MULTILINE)
        expected = 'power' if action == 'on' else 'off'
        if len(states) != 4 or any(expected not in state.split() for state in states):
            raise RuntimeError('USB hub did not confirm power ' + action)


def power(action):
    # @llr LLR-TERM-MAINT-028
    if action == 'restore':
        if os.geteuid() != 0:
            raise PermissionError('Cleanup restoration requires root')
        if maintenance_active():
            return  # No USB enumeration or control transfer during maintenance.
        action = 'on'
    validate_board()
    if action == 'on':
        # @llr LLR-TERM-POWER-016
        switch('on')
        return
    attached = devices()
    if any(identity not in (('0525', 'a4ad'), ('0525', 'a4b0')) for _, identity in attached):
        raise RuntimeError('Other USB peripherals present; leaving power on')
    if len(attached) != 1:
        raise RuntimeError('Expected exactly one C10 or C20 before powering down')
    nodes = list(Path('/dev').glob('video*')) + list(Path('/dev/snd').glob('pcm*'))
    if nodes:
        opened = subprocess.run(['/usr/bin/fuser', *map(str, nodes)], capture_output=True, timeout=5)
        if opened.returncode != 1:  # 0 = open, other errors are not evidence of inactivity.
            raise RuntimeError('Camera or audio still open; leaving USB power on')
    camera = attached[0][0]
    try:
        # Gracefully detach all C20 interfaces before removing the shared supply.
        (camera / 'authorized').write_text('0')
        switch('off')
    except Exception:
        print('USB power-off failed; restoring power', file=sys.stderr, flush=True)
        switch('on')
        if (camera / 'authorized').exists():
            (camera / 'authorized').write_text('1')
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('on', 'off', 'restore'))
    try:
        power(parser.parse_args().action)
    except Exception as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
