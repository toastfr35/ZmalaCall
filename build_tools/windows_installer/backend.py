"""SSH deployment for the standalone Windows terminal installer."""
import base64
import hashlib
import ipaddress
import json
from pathlib import Path
import shlex
import time
import uuid

import paramiko

USER = PASSWORD = 'zmala'
SERVICES = ('zmalacall-terminal', 'zmalacall-display', 'zmalacall-pairing',
            'zmalacall-compositor', 'zmalacall-cec', 'ssh', 'zmalacall-ssh-guard',
            'nftables', 'bluetooth', 'NetworkManager')


class InstallError(Exception):
    pass


def fingerprint(key):
    return 'SHA256:' + base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip('=')


class TargetKeyPolicy(paramiko.MissingHostKeyPolicy):
    """First check shows the key for confirmation; subsequent connections pin it."""
    def __init__(self, expected):
        self.expected = expected

    def missing_host_key(self, client, hostname, key):
        if self.expected is not None and fingerprint(key) != self.expected:
            raise InstallError('The Pi SSH identity changed. Installation stopped. Check the target again.')


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


def verify_payload(archive):
    archive = Path(archive)
    expected = archive.with_name(archive.name + '.sha256').read_text().split()[0]
    actual = hashlib.sha256(archive.read_bytes()).hexdigest()
    if actual != expected:
        raise InstallError('The bundled installation package is damaged. Obtain a fresh installer.')
    return actual


class Deployment:
    def __init__(self, host, emit=lambda message: None):
        self.host = host.strip()
        if not self.host or any(c.isspace() for c in self.host):
            raise InstallError('Enter the Pi hostname or Ethernet IP address.')
        self.emit = emit
        self.client = None
        self.key = None
        self.info = None
        self.wired_address = None

    def close(self):
        if self.client:
            self.client.close()
            self.client = None

    def connect(self):
        self.close()
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(TargetKeyPolicy(self.key))
        try:
            client.connect(self.wired_address or self.host, username=USER, password=PASSWORD, timeout=10,
                           auth_timeout=10, banner_timeout=10, look_for_keys=False, allow_agent=False)
        except Exception:
            client.close()
            raise
        self.key = fingerprint(client.get_transport().get_remote_server_key())
        client.get_transport().set_keepalive(10)
        self.client = client

    def command(self, command, data='', sudo=False, timeout=30):
        if sudo:
            command = 'sudo -S -k -p "" ' + command
            data = PASSWORD + '\n' + data
        channel = self.client.get_transport().open_session(timeout=10)
        channel.set_combine_stderr(True)
        chunks = []
        try:
            channel.exec_command(command)
            if data:
                channel.sendall(data.encode())
            channel.shutdown_write()
            deadline = time.monotonic() + timeout
            while True:
                if channel.recv_ready():
                    chunks.append(channel.recv(65536))
                elif channel.exit_status_ready():
                    break
                elif time.monotonic() > deadline:
                    raise InstallError('Timed out waiting for the Pi to finish a command.')
                else:
                    time.sleep(.05)
            output = b''.join(chunks).decode('utf-8', errors='replace')
            status = channel.recv_exit_status()
            if status != 0:
                raise InstallError(f'Pi command failed (exit {status}):\n{output[-6000:]}')
            return output
        finally:
            channel.close()

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

    def reconnect(self, deadline):
        while time.monotonic() < deadline:
            try:
                self.connect()
                return
            except InstallError:
                raise
            except (OSError, EOFError, paramiko.SSHException):
                time.sleep(3)
        raise InstallError('The Pi did not reconnect. Keep it powered and connected to Ethernet. '
                           'An installation already started on the Pi continues independently.')

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

    def monitor(self, unit, path):
        offset = 0
        deadline = time.monotonic() + 3600
        while time.monotonic() < deadline:
            try:
                with self.client.open_sftp() as sftp, sftp.open(path, 'rb') as log:
                    log.seek(offset)
                    data = log.read(512 * 1024)
                    offset += len(data)
                    if data:
                        self.emit(data.decode('utf-8', errors='replace'))
                state = self.command('systemctl show ' + unit
                                     + ' -p ActiveState -p SubState -p ExecMainStatus -p Result')
            except (EOFError, OSError, paramiko.SSHException):
                self.emit('Connection interrupted; reconnecting to the same Pi...\n')
                self.reconnect(min(deadline, time.monotonic() + 120))
                continue
            props = dict(line.split('=', 1) for line in state.splitlines() if '=' in line)
            if props.get('ActiveState') == 'active' and props.get('SubState') == 'exited':
                if props.get('ExecMainStatus') != '0' or props.get('Result') != 'success':
                    raise InstallError('The Pi installer reported a failure. See the installation log.')
                # Drain any last output written between the read and service completion.
                with self.client.open_sftp() as sftp, sftp.open(path, 'rb') as log:
                    log.seek(offset)
                    self.emit(log.read().decode('utf-8', errors='replace'))
                return
            if props.get('ActiveState') in ('failed', 'inactive'):
                with self.client.open_sftp() as sftp, sftp.open(path, 'rb') as log:
                    log.seek(offset)
                    self.emit(log.read().decode('utf-8', errors='replace'))
                raise InstallError('Installation failed on the Pi. Output: ' + path
                                   + '\nDetailed logs: /var/log/zmalacall-install/.\n' + state)
            time.sleep(2)
        raise InstallError('Installation has exceeded one hour. It may still be running on the Pi. '
                           'See ' + path + ' before retrying.')

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
