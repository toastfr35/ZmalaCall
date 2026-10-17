"""Read-only service, listener and low-write validation after server reboot."""
import json
from pathlib import Path
import subprocess
import urllib.request


def command(*args):
    return subprocess.check_output(args, text=True, timeout=15).strip()


def inspect():
    state = json.loads(Path('/var/lib/zmalacall-server/server.json').read_text())
    with urllib.request.urlopen(f"http://127.0.0.1:{state['http_port']}/ready", timeout=5) as response:
        health = json.load(response)
    swaps = [line.split()[0] for line in Path('/proc/swaps').read_text().splitlines()[1:]]
    journal = {}
    for line in command('systemd-analyze', 'cat-config', 'systemd/journald.conf').splitlines():
        if '=' in line and not line.lstrip().startswith(('#', ';')):
            k, v = line.split('=', 1)
            journal[k.strip()] = v.strip()
    tcp = command('ss', '-H', '-ltn')
    udp = command('ss', '-H', '-lun')
    return {
        'healthy': health.get('ok') is True,
        'server_active': command('systemctl', 'is-active', 'zmalacall-server') == 'active',
        'ssh_guard_active': command('systemctl', 'is-active', 'zmalacall-ssh-guard') == 'active',
        'ram_journal': journal.get('Storage') == 'volatile' and journal.get('RuntimeMaxUse') == '64M'
                       and journal.get('ForwardToSyslog') == 'no',
        'ram_only_swap': bool(swaps) and all(p.startswith('/dev/zram') and
            (Path('/sys/block') / Path(p).name / 'backing_dev').read_text().strip() == 'none' for p in swaps),
        'tmpfs': command('findmnt', '-no', 'FSTYPE', '/tmp') == 'tmpfs',
        'noatime': 'noatime' in command('findmnt', '-no', 'OPTIONS', '/').split(','),
        'http_all_interfaces': f"0.0.0.0:{state['http_port']} " in tcp,
        'sip_all_interfaces': f"0.0.0.0:{state['sip_port']} " in udp,
    }


if __name__ == '__main__':
    result = inspect()
    print(json.dumps(result))
    raise SystemExit(0 if all(result.values()) else 1)
