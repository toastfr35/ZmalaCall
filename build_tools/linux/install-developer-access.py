#!/usr/bin/python3
"""Install isolated developer SSH services; existing call services are untouched."""
import argparse
import json
from pathlib import Path
import pwd
import shutil
import subprocess


def command(*args):
    subprocess.run(args, check=True, timeout=30)


def install(role, user, host):
    pwd.getpwnam(user)
    root = Path(__file__).resolve().parent
    Path('/etc/zmalacall').mkdir(exist_ok=True)
    Path('/usr/local/libexec').mkdir(exist_ok=True)
    helper = Path('/usr/local/libexec/zmala-developer-access')
    shutil.copyfile(root / 'developer-access.py', helper)
    helper.chmod(0o755)
    Path('/etc/zmalacall/developer-access.json').write_text(json.dumps({'role': role, 'host': host}))
    base = '''HostKey /etc/ssh/ssh_host_ed25519_key
PidFile none
UsePAM yes
PermitRootLogin no
PasswordAuthentication yes
KbdInteractiveAuthentication no
PermitEmptyPasswords no
X11Forwarding no
AllowAgentForwarding no
AllowStreamLocalForwarding no
PermitTunnel no
LogLevel ERROR
'''
    def service(name, start, extra=''):
        Path('/etc/systemd/system/' + name + '.service').write_text('''[Unit]
Description=ZmalaCall developer access
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=0
[Service]
Type=simple
RuntimeDirectory=sshd
RuntimeDirectoryPreserve=yes
KillMode=control-group
ExecStart=''' + start + '\n' + extra + '\n[Install]\nWantedBy=multi-user.target\n')
    if role == 'server':
        try:
            pwd.getpwnam('terminal')
            if not Path('/etc/ssh/zmala-developer-server.conf').exists():
                raise RuntimeError('Refusing to repurpose an existing terminal account')
        except KeyError:
            command('useradd', '--system', '--no-create-home', '--shell', '/usr/sbin/nologin', 'terminal')
        config = base + '''Port 2222
ListenAddress 0.0.0.0
ListenAddress ::
AllowUsers terminal
PubkeyAuthentication no
AllowTcpForwarding remote
GatewayPorts no
PermitListen 127.0.0.1:22001
PermitOpen none
MaxSessions 0
ForceCommand /bin/false
'''
        path = '/etc/ssh/zmala-developer-server.conf'
        service('zmalacall-developer', '/usr/sbin/sshd -D -e -f ' + path)
        Path('/etc/ssh/sshd_config.d/00-zmala-no-tunnel-login.conf').write_text('DenyUsers terminal\n')
        actions = 'on, /usr/local/libexec/zmala-developer-access off, /usr/local/libexec/zmala-developer-access status, /usr/local/libexec/zmala-developer-access config'
    else:
        config = base + 'Port 2223\nListenAddress 127.0.0.1\nAllowUsers ' + user + '\nAllowTcpForwarding no\n'
        path = '/etc/ssh/zmala-developer-terminal.conf'
        service('zmalacall-developer-shell', '/usr/sbin/sshd -D -e -f ' + path)
        service('zmalacall-developer-tunnel', '/usr/local/libexec/zmala-developer-access run',
                'Restart=always\nRestartSec=10\nStandardInput=null')
        askpass = Path('/usr/local/libexec/zmala-developer-askpass')
        askpass.write_text('#!/bin/sh\nexec /usr/local/libexec/zmala-developer-access askpass\n')
        askpass.chmod(0o755)
        actions = 'apply, /usr/local/libexec/zmala-developer-access off'
    Path(path).write_text(config)
    Path('/run/sshd').mkdir(exist_ok=True)
    command('/usr/sbin/sshd', '-t', '-f', path)
    sudoers = Path('/etc/sudoers.d/zmalacall-developer')
    sudoers.write_text(user + ' ALL=(root) NOPASSWD: /usr/local/libexec/zmala-developer-access ' + actions + '\n')
    sudoers.chmod(0o440)
    command('visudo', '-cf', str(sudoers))
    if role == 'server':
        guard = Path('/usr/local/libexec/zmala-developer-lan-guard')
        shutil.copyfile(root / 'developer-lan-guard.py', guard)
        guard.chmod(0o755)
        # Validate/apply before exposing the listener. Recompute after address
        # changes and at boot; absent addresses fail closed for ordinary SSH.
        command(str(guard))
        nft = Path('/etc/nftables.conf')
        include = 'include "/etc/nftables.d/zmala-developer-lan.nft"'
        if include not in nft.read_text():
            with nft.open('a') as stream:
                stream.write('\n' + include + '\n')
        Path('/etc/systemd/system/zmalacall-developer-lan.service').write_text(
            '[Unit]\nAfter=network-online.target nftables.service\nWants=network-online.target\n'
            '[Service]\nType=oneshot\nExecStart=' + str(guard) + '\n'
            '[Install]\nWantedBy=multi-user.target\n')
        dispatcher = Path('/etc/NetworkManager/dispatcher.d/90-zmala-developer-lan')
        dispatcher.parent.mkdir(parents=True, exist_ok=True)
        dispatcher.write_text('#!/bin/sh\ncase "$2" in up|down|dhcp4-change|dhcp6-change) '
                              'exec /usr/local/libexec/zmala-developer-lan-guard;; esac\n')
        dispatcher.chmod(0o755)
        command('/usr/sbin/sshd', '-t')
        command('systemctl', 'reload', 'ssh.service')
    command('systemctl', 'daemon-reload')
    if role == 'server':
        command('systemctl', 'enable', 'zmalacall-developer-lan.service')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('role', choices=['server', 'terminal'])
    parser.add_argument('--user', required=True)
    parser.add_argument('--host', default='')
    args = parser.parse_args()
    install(args.role, args.user, args.host)
