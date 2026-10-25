"""Server deployment uses the terminal installer's SSH pinning and job monitor."""
import ipaddress
import json
import re
from pathlib import Path
import shlex
import sys
import tarfile
import tempfile
import time
import uuid

from build_tools.windows_installer.ssh_transport import SSHDeployment, InstallError, verify_payload


def validate_target(info, storage=True):
    if not info['model'].startswith(('Raspberry Pi 3 Model B', 'Raspberry Pi 4 Model B')):
        raise InstallError('Expected Raspberry Pi 3 or 4 Model B: ' + info['model'])
    if (info['architecture'] != 'arm64' or info['machine'] != 'aarch64'
            or not info.get('pi_image', '').startswith('Raspberry Pi reference')
            or info['os'].get('ID') not in ('debian', 'raspbian')
            or info['os'].get('VERSION_CODENAME') != 'trixie'):
        raise InstallError('Use Raspberry Pi OS Lite 64-bit, Debian Trixie.')
    if info['hostname'] != 'zmalaserver' or not info['boot_mounted']:
        raise InstallError('Expected hostname zmalaserver and mounted /boot/firmware.')
    try:
        wired = ipaddress.ip_address(info['ssh_address']) in {ipaddress.ip_address(x) for x in info['ethernet_addresses']}
    except ValueError:
        wired = False
    if not wired or not info['ethernet_up']:
        raise InstallError('Connect through physical Ethernet before installing.')
    if storage and info['free_var'] < 1024**3:
        raise InstallError('At least 1 GiB of free storage is required.')


def migration_archive(directory, destination):
    """Explicit state allowlist: never bundle logs, old backups or source credentials."""
    root = Path(directory).resolve()
    state = json.loads((root / 'server.json').read_text(encoding='utf-8'))
    if not isinstance(state.get('users'), dict) or not isinstance(state.get('profiles'), dict):
        raise InstallError('The selected directory does not contain valid server data.')
    files = [root / name for name in ('server.json', 'admin-password.json', 'callbacks.json', 'console-jobs.json')]
    files += list(root.glob('*-avatar.png'))
    files += list((root / 'photos').glob('*'))
    for identity in state.get('ringtones', {}):
        if not re.fullmatch(r'[a-f0-9]{64}', identity):
            raise InstallError('Invalid ringtone identity in migration data.')
        sound = root / 'ringtones' / (identity + '.wav')
        if not sound.is_file():
            raise InstallError('A referenced ringtone file is missing.')
        files.append(sound)
    with tarfile.open(destination, 'w:gz') as archive:
        for path in files:
            if not path.exists():
                continue
            if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
                raise InstallError('Unexpected link or directory in migration data.')
            if path.stat().st_size > 32*1024*1024:
                raise InstallError('Migration file exceeds the supported size.')
            archive.add(path, arcname=path.relative_to(root).as_posix(), recursive=False)


class Deployment(SSHDeployment):
    user = password = 'zmalaserver'

    def probe(self):
        path = (Path(sys._MEIPASS) / 'remote_probe.py' if getattr(sys, 'frozen', False)
                else Path(__file__).parents[1] / 'windows_installer/remote_probe.py')
        script = path.read_text().replace("Path('/opt/zmalacall/current')", "Path('/opt/zmalacall-server/current')")
        return json.loads(self.command('python3 -', script))

    def check(self):
        self.emit('Checking SSH, operating system and wired connection...\n')
        self.connect()
        self.info = self.probe()
        if self.info['ethernet_up'] and self.info['ssh_address'] not in self.info['ethernet_addresses']:
            # mDNS can prefer Wi-Fi on a dual-connected Pi. Pin the same SSH
            # identity and move to its observed Ethernet address before writes.
            candidates = [x for x in self.info['ethernet_addresses'] if ipaddress.ip_address(x).version == 4]
            if candidates:
                self.wired_address = candidates[0]
                self.connect()
                self.info = self.probe()
        validate_target(self.info)
        self.wired_address = self.info['ssh_address']
        self.command('true', sudo=True)
        self.emit('Checks passed. SSH identity: ' + self.key + '\n')
        return self.info

    def install(self, archive, data_dir=None):
        if self.info is None:
            raise InstallError('Check the Pi before installing.')
        self.connect()
        validate_target(self.probe())
        digest = verify_payload(archive)
        token = uuid.uuid4().hex[:12]
        remote = '/home/zmalaserver/zmala-server-install-' + token
        unit = 'zmalacall-server-install-' + token
        self.command('mkdir -m 700 ' + shlex.quote(remote))
        self.emit('Uploading the server package...\n')
        with tempfile.TemporaryDirectory() as temporary:
            migration = Path(temporary) / 'migration.tar.gz'
            if data_dir:
                migration_archive(data_dir, migration)
            with self.client.open_sftp() as sftp:
                sftp.put(str(archive), remote + '/server.tar.gz')
                if data_dir:
                    sftp.put(str(migration), remote + '/migration.tar.gz')
                    sftp.chmod(remote + '/migration.tar.gz', 0o600)
                with sftp.open(remote + '/progress.log', 'w'):
                    pass
                sftp.chmod(remote + '/progress.log', 0o600)
        self.command('python3 -', f'''import hashlib, pathlib, tarfile
p = pathlib.Path({remote!r})
assert hashlib.sha256((p/'server.tar.gz').read_bytes()).hexdigest() == {digest!r}, 'Upload checksum mismatch'
with tarfile.open(p/'server.tar.gz') as archive: archive.extractall(p, filter='data')
''', timeout=120)
        args = ['systemd-run', '--no-block', '--unit='+unit, '--property=Type=oneshot',
                '--property=RemainAfterExit=yes', '--property=StandardOutput=append:'+remote+'/progress.log',
                '--property=StandardError=inherit', '/bin/sh', remote+'/install.sh']
        if data_dir:
            args += ['--data-archive', remote+'/migration.tar.gz']
        self.emit('Installing dependencies, server, Ethernet-only SSH and RAM logging/swap.\n')
        self.command(shlex.join(args), sudo=True)
        self.monitor(unit, remote+'/progress.log')
        if data_dir:
            self.command('rm -- '+shlex.quote(remote+'/migration.tar.gz'))
        old_boot = self.probe()['boot_id']
        self.emit('Rebooting and checking automatic startup...\n')
        import paramiko
        try:
            self.command('systemctl reboot --no-block', sudo=True)
        except (EOFError, OSError, paramiko.SSHException):
            pass  # Reboot can close SSH before the command result arrives.
        self.close()
        self.verify_server_reboot(old_boot)
        self.emit('SUCCESS. Server is running. Administration: http://'+self.wired_address+':8080/\n')

    def verify_server_reboot(self, old_boot):
        import paramiko
        deadline = time.monotonic()+300
        stable = None
        previous_pid = None
        while time.monotonic() < deadline:
            time.sleep(3)
            try:
                self.connect()
                if self.probe()['boot_id'] == old_boot:
                    continue
                pid = self.command('systemctl show zmalacall-server -p MainPID --value').strip()
                if pid == '0' or pid != previous_pid:
                    stable = None
                previous_pid = pid
                if pid != '0':
                    if stable is None:
                        stable = time.monotonic()
                    elif time.monotonic()-stable >= 10:
                        self.emit(self.command('python3 /opt/zmalacall-server/current/build_tools/linux/check-server.py'))
                        self.emit(self.command('nft list table inet zmala_ssh', sudo=True))
                        return
            except InstallError:
                raise
            except (OSError, EOFError, paramiko.SSHException):
                stable = None
        raise InstallError('Server did not pass post-reboot checks. Keep Ethernet connected and inspect the log.')
