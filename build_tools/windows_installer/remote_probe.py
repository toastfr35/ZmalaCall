"""Read-only target inventory, executed over SSH using the Pi's Python."""
import json
import os
from pathlib import Path
import platform
import shutil
import socket
import subprocess


def read(path):
    try:
        return Path(path).read_text().strip('\x00\n ')
    except OSError:
        return ''


def inventory():
    release = {}
    for line in read('/etc/os-release').splitlines():
        if '=' in line:
            key, value = line.split('=', 1)
            release[key] = value.strip('"')
    addresses = json.loads(subprocess.check_output(['ip', '-j', 'address', 'show', 'dev', 'eth0'], text=True))
    ethernet = [entry['local'] for adapter in addresses for entry in adapter.get('addr_info', [])]
    connection = os.environ.get('SSH_CONNECTION', '').split()
    return {
        'hostname': socket.gethostname(), 'model': read('/proc/device-tree/model'),
        'pi_image': read('/etc/rpi-issue'),
        'os': release, 'machine': platform.machine(),
        'architecture': subprocess.check_output(['dpkg', '--print-architecture'], text=True).strip(),
        'ethernet_up': read('/sys/class/net/eth0/operstate') == 'up',
        'ethernet_addresses': ethernet, 'ssh_address': connection[2] if len(connection) == 4 else '',
        'boot_mounted': os.path.ismount('/boot/firmware'),
        'free_var': shutil.disk_usage('/var').free,
        'free_boot': shutil.disk_usage('/boot/firmware').free,
        'installed': Path('/opt/zmalacall/current').is_dir(),
        'boot_id': read('/proc/sys/kernel/random/boot_id'),
    }


if __name__ == '__main__':
    print(json.dumps(inventory()))
