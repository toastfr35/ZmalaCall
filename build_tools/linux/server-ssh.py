#!/usr/bin/python3
"""Root-owned, fixed-action control of wired SSH; web/SIP firewall rules untouched."""
import argparse
import fcntl
import json
from pathlib import Path
import subprocess


def run(*args, check=True):
    return subprocess.run(args, check=check, capture_output=True, text=True, timeout=30)


def status():
    return {'supported': True, 'enabled': run('systemctl', 'is-enabled', 'ssh.service', check=False).returncode == 0,
            'active': run('systemctl', 'is-active', 'ssh.service', check=False).returncode == 0,
            'interface': 'eth0'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['status', 'on', 'off'])
    action = parser.parse_args().action
    if action != 'status':
        if Path('/etc/zmalacall/ssh-interface').read_text().strip() != 'eth0':
            raise RuntimeError('Expected wired SSH guard on eth0')
        if action == 'on':
            run('systemctl', 'start', 'nftables', 'zmalacall-ssh-guard')
            run('/usr/bin/python3', '/usr/local/libexec/zmala-ssh-guard.py')
            run('systemctl', 'enable', '--now', 'ssh.service')
        else:
            with open('/run/lock/zmalacall-server-install.lock', 'a') as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise RuntimeError('Keep SSH enabled until installation finishes') from None
                # Keep the lock until SSH is disabled: installation cannot race us.
                # Disable socket activation too, or it could bring sshd back.
                socket = run('systemctl', 'show', 'ssh.socket', '-p', 'LoadState', '--value').stdout.strip()
                if socket != 'not-found':
                    run('systemctl', 'disable', '--now', 'ssh.socket')
                run('systemctl', 'disable', '--now', 'ssh.service')
    print(json.dumps(status()))


if __name__ == '__main__':
    main()
