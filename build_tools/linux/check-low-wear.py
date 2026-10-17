"""Verify the installed low-write settings after the required reboot."""
import json
from pathlib import Path
import subprocess
import sys


def command(*args):
    return subprocess.check_output(args, text=True, timeout=15).strip()


def journal_options(text):
    options = {}
    section = ''
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(('#', ';')):
            continue
        if line.startswith('['):
            section = line
        elif section == '[Journal]' and '=' in line:
            key, value = line.split('=', 1)
            options[key.strip()] = value.strip()
    return options


def inspect():
    swaps = [line.split()[0] for line in Path('/proc/swaps').read_text().splitlines()[1:]]
    ram_only = bool(swaps) and all(name.startswith('/dev/zram') for name in swaps)
    if ram_only:
        ram_only = all((Path('/sys/block') / Path(name).name / 'backing_dev').read_text().strip() == 'none'
                       for name in swaps)
    journal = journal_options(command('systemd-analyze', 'cat-config', 'systemd/journald.conf'))
    environment = command('systemctl', 'show', 'zmalacall-terminal', '-p', 'Environment', '--value')
    checks = {
        'ram_only_swap': ram_only,
        'ram_journal': journal.get('Storage') == 'volatile',
        'journal_limit_64m': journal.get('RuntimeMaxUse') == '64M',
        'no_syslog_forwarding': journal.get('ForwardToSyslog') == 'no',
        'temporary_files_in_ram': command('findmnt', '-no', 'FSTYPE', '/tmp') == 'tmpfs',
        'no_access_time_writes': 'noatime' in command('findmnt', '-no', 'OPTIONS', '/').split(','),
        'terminal_logs_to_journal': 'ZMALA_LOG_STDERR=1' in environment,
        'terminal_runtime_in_ram': 'ZMALA_RUNTIME_DIR=/run/zmalacall' in environment
                                   and Path('/run/zmalacall').is_dir(),
    }
    return checks


if __name__ == '__main__':
    result = inspect()
    print(json.dumps(result))
    sys.exit(0 if all(result.values()) else 1)
