"""SSH deployment for the standalone Windows terminal installer."""
import ipaddress
import json
from pathlib import Path
import shlex
import time
import uuid

import paramiko

# Support both the package import and PyInstaller's standalone entrypoint.
if __package__:
    from .ssh_transport import SSHDeployment, InstallError, verify_payload, fingerprint as fingerprint, TargetKeyPolicy as TargetKeyPolicy
else:
    from ssh_transport import SSHDeployment, InstallError, verify_payload, fingerprint as fingerprint, TargetKeyPolicy as TargetKeyPolicy

USER = PASSWORD = 'zmala'
SERVICES = ('zmalacall-terminal', 'zmalacall-display', 'zmalacall-pairing',
            'zmalacall-compositor', 'zmalacall-cec', 'ssh', 'zmalacall-ssh-guard',
            'nftables', 'bluetooth', 'NetworkManager')


def validate_target(info, storage=True):
    if not info['model'].startswith('Raspberry Pi 4 Model B'):
        raise InstallError('Expected a Raspberry Pi 4 Model B; found ' + info['model'])
    release = info['os']
    if (info['architecture'] != 'arm64' or info['machine'] != 'aarch64'
            or not info.get('pi_image', '').startswith('Raspberry Pi reference')
            or release.get('ID') not in ('debian', 'raspbian')
            or release.get('VERSION_CODENAME') != 'trixie'):
        raise InstallError('Expected Raspberry Pi OS Lite 64-bit, Debian 13 Trixie. Found: '
                           + release.get('PRETTY_NAME', 'unknown OS') + ' / ' + info['architecture'])
    if info['hostname'] != 'zmala':
        raise InstallError('Expected hostname zmala; found ' + info['hostname'])
    if not info['boot_mounted']:
        raise InstallError('The Pi boot partition is not mounted at /boot/firmware.')
    try:
        wired = ipaddress.ip_address(info['ssh_address']) in {
            ipaddress.ip_address(value) for value in info['ethernet_addresses']}
    except ValueError:
        wired = False
    if not info['ethernet_up'] or not wired:
        raise InstallError('SSH must use the Ethernet address. Connect Ethernet and enter its IP address.')
    if storage and (info['free_var'] < 3 * 1024**3 or info['free_boot'] < 128 * 1024**2):
        raise InstallError('Insufficient free space: need 3 GiB on /var and 128 MiB on the boot partition.')


class Deployment(SSHDeployment):
    user = USER
    password = PASSWORD


    def probe(self):
        script = Path(__file__).with_name('remote_probe.py').read_text()
        return json.loads(self.command('python3 -', script))

    def check(self):
        self.emit('Checking SSH connection to ' + self.host + '...\n')
        try:
            self.connect()
        except paramiko.AuthenticationException as error:
            raise InstallError('SSH login failed. The username and password must both be zmala.') from error
        except (OSError, paramiko.SSHException) as error:
            raise InstallError('Cannot connect to the Pi. Check power, Ethernet and SSH; try its Ethernet IP.\n'
                               + str(error)) from error
        self.info = self.probe()
        validate_target(self.info)
        # mDNS may start advertising Wi-Fi after reboot, where SSH is blocked.
        # Keep using the Ethernet endpoint that passed the check.
        self.wired_address = self.info['ssh_address']
        self.command('true', sudo=True)
        self.emit('SSH, administrator access, Pi model, OS, Ethernet and storage checks passed.\n')
        self.emit('Target SSH fingerprint: ' + self.key + '\n')
        return self.info


    def install(self, archive, argon=True):
        if self.info is None:
            raise InstallError('Check the Pi before installing.')
        # Recheck the confirmed target immediately before making any changes.
        self.connect()
        fresh = self.probe()
        validate_target(fresh)
        digest = verify_payload(archive)
        token = uuid.uuid4().hex[:12]
        remote = '/home/zmala/zmala-install-' + token
        unit = 'zmalacall-install-' + token
        self.emit('Uploading the bundled terminal package...\n')
        self.command('mkdir -m 700 ' + shlex.quote(remote))
        with self.client.open_sftp() as sftp:
            last_percent = [-10]
            def progress(sent, total):
                percent = int(sent * 100 / max(total, 1))
                if percent >= last_percent[0] + 10:
                    last_percent[0] = percent
                    self.emit(f'Upload {percent}%\n')
            sftp.put(str(archive), remote + '/terminal.tar.gz', callback=progress)
            with sftp.open(remote + '/progress.log', 'w'):
                pass
            sftp.chmod(remote + '/progress.log', 0o600)
        self.emit('Verifying the uploaded package...\n')
        self.command('python3 -', f'''import hashlib, pathlib, tarfile
p = pathlib.Path({remote!r})
assert hashlib.sha256((p / 'terminal.tar.gz').read_bytes()).hexdigest() == {digest!r}, 'Upload checksum mismatch'
with tarfile.open(p / 'terminal.tar.gz') as archive:
    archive.extractall(p, filter='data')
''', timeout=120)
        args = ['systemd-run', '--no-block', '--unit=' + unit, '--property=Type=oneshot',
                '--property=RemainAfterExit=yes', '--property=StandardOutput=append:' + remote + '/progress.log',
                '--property=StandardError=inherit', '/bin/sh', remote + '/install.sh']
        if argon:
            args.append('--argon-one')
        self.emit('Installing on the Pi. This may take several minutes.\n'
                  'The installation will continue if the SSH connection briefly drops.\n')
        self.emit('Pi installation output: ' + remote + '/progress.log\n')
        self.command(shlex.join(args), sudo=True)
        self.monitor(unit, remote + '/progress.log')
        self.emit('Installation passed. Rebooting the Pi automatically...\n')
        old_boot = self.probe()['boot_id']
        try:
            self.command('systemctl reboot --no-block', sudo=True)
        except (EOFError, OSError, paramiko.SSHException):
            pass  # The reboot can close SSH before its reply arrives.
        self.close()
        self.verify_reboot(old_boot)
        self.emit('Installation complete. The terminal is running after reboot.\n'
                  'Continue the camera, remote and QR setup on the TV.\n')


    def verify_reboot(self, old_boot):
        deadline = time.monotonic() + 240
        stable_since = None
        previous_restarts = None
        while time.monotonic() < deadline:
            time.sleep(3)
            try:
                self.connect()
                if self.probe()['boot_id'] == old_boot:
                    continue
                state = self.command('systemctl show ' + ' '.join(SERVICES)
                                     + ' -p Id -p ActiveState -p NRestarts')
                blocks = [dict(line.split('=', 1) for line in block.splitlines() if '=' in line)
                          for block in state.strip().split('\n\n')]
                healthy = len(blocks) == len(SERVICES) and all(b.get('ActiveState') == 'active' for b in blocks)
                restarts = [b.get('NRestarts') for b in blocks]
                if not healthy or restarts != previous_restarts:
                    stable_since = None
                previous_restarts = restarts
                if healthy:
                    if stable_since is None:
                        stable_since = time.monotonic()
                    elif time.monotonic() - stable_since >= 8:
                        self.emit('Checking RAM logging, swap and temporary-file settings...\n')
                        self.command('python3 /opt/zmalacall/current/build_tools/linux/check-low-wear.py')
                        return
            except InstallError:
                raise
            except (OSError, EOFError, paramiko.SSHException, json.JSONDecodeError):
                stable_since = None
        raise InstallError('Installation finished, but the Pi did not pass its post-reboot startup checks. '
                           'Keep Ethernet connected and check the Pi before retrying.')
