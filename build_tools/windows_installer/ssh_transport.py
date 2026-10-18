"""Pinned SSH transport and durable installation-job monitoring shared by both installers."""
import base64
import hashlib
from pathlib import Path
import time

import paramiko


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


def verify_payload(archive):
    archive = Path(archive)
    expected = archive.with_name(archive.name + '.sha256').read_text().split()[0]
    actual = hashlib.sha256(archive.read_bytes()).hexdigest()
    if actual != expected:
        raise InstallError('The bundled installation package is damaged. Obtain a fresh installer.')
    return actual


class SSHDeployment:
    """Subclasses provide account credentials and product-specific deployment steps."""
    user = password = ""

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
            client.connect(self.wired_address or self.host, username=self.user, password=self.password, timeout=10,
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
            data = self.password + '\n' + data
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
