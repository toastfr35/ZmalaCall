"""Optional, paired Samsung remote for TVs that ignore CEC source release.

CEC requests HDMI switching and standby first. An explicitly verified,
connector-bound source key can select HDMI when the broadcast tuner ignores CEC.
This adapter also returns to
the built-in tuner, preserving its last channel, volume and mute. A power-key
fallback is allowed only after a fresh, explicit confirmation that the TV is on.
The token and pinned TLS certificate live in private terminal runtime data.
"""
import base64
import hashlib
import hmac
import ipaddress
import json
import logging
from pathlib import Path
import re
import socket
import ssl
import time
from urllib.parse import urlencode


DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / 'data/tv-remote.json'


def save_config(path, value):
    """Replace credentials atomically, without putting tokens in logs or code."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    try:
        temporary.touch(mode=0o600, exist_ok=True)
        temporary.chmod(0o600)
        temporary.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def connect(host, token=None, fingerprint=None, timeout=8):
    """Pair explicitly, or authenticate the same TLS socket before sending a token.

    Samsung uses a self-signed certificate. A saved SHA-256 pin replaces CA
    verification on subsequent connections; a changed certificate fails closed.
    The first connection is trusted only by the explicit pairing tool.
    """
    import websocket  # Optional until a TV is paired; supplied by Linux installer.

    host = str(ipaddress.ip_address(host))
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    raw = socket.create_connection((host, 8002), timeout=timeout)
    tls = None
    remote = None
    try:
        tls = context.wrap_socket(raw, server_hostname=host)
        actual = hashlib.sha256(tls.getpeercert(binary_form=True)).hexdigest()
        if fingerprint is not None and not hmac.compare_digest(actual, fingerprint):
            raise ValueError('TV certificate changed; pair the TV again')
        query = {'name': base64.b64encode(b'ZmalaCall').decode('ascii')}
        if token:
            query['token'] = token
        address = '[' + host + ']' if ':' in host else host
        url = 'wss://' + address + ':8002/api/v2/channels/samsung.remote.control?' + urlencode(query)
        # Passing the already-verified socket prevents a second TLS connection
        # from sending credentials before its certificate has been checked.
        remote = websocket.create_connection(url, socket=tls, timeout=timeout)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            remote.settimeout(max(.1, deadline - time.monotonic()))
            packet = json.loads(remote.recv())
            event = packet.get('event')
            if event == 'ms.channel.connect':
                token = packet.get('data', {}).get('token') or token
                if not isinstance(token, str) or not token:
                    raise ValueError('TV did not provide an authentication token')
                return remote, {'host': host, 'token': token, 'certificate_sha256': actual}
            if event in ('ms.channel.unauthorized', 'ms.channel.timeOut'):
                raise PermissionError('TV remote permission was not granted')
        raise TimeoutError('TV remote authorization timed out')
    except Exception:
        if remote:
            remote.close(timeout=0)
        elif tls:
            tls.close()
        else:
            raw.close()
        raise


class SamsungTV:
    def __init__(self, config_file=DEFAULT_CONFIG):
        self.config_file = Path(config_file)
        self.enabled = True

    def restore_broadcast(self, is_current):
        """Do not connect for unpaired TVs or send a key after a new call starts."""
        return self._send_key('KEY_TV', is_current)

    def standby_if_on(self, is_current, is_on):
        """Samsung's power key toggles: recheck settled on immediately before sending."""
        return self._send_key('KEY_POWER', is_current, is_on)

    def select_terminal(self, address, is_current):
        """Use a source command verified for this TV and physical HDMI route.

        KEY_HDMI1 is ignored on some Tizen TVs; KEY_HDMI works on the tested TV
        but is not a universal numbered-input selector. Require an explicit
        local binding rather than applying it to every Samsung/HDMI port.
        """
        try:
            config = json.loads(self.config_file.read_text(encoding='utf-8'))
            binding = config.get('terminal_source', {})
            key = binding.get('key')
            if (binding.get('address') != address or
                    not re.fullmatch(r'[1-9a-f](\.[0-9a-f]){3}', address) or
                    key not in ('KEY_HDMI', 'KEY_HDMI1', 'KEY_HDMI2', 'KEY_HDMI3', 'KEY_HDMI4')):
                return False
        except (OSError, ValueError, TypeError, AttributeError):
            return False
        return self._send_key(key, is_current)

    def _send_key(self, key, is_current, can_send=lambda: True):
        """Keep remote commands restricted to source selection and guarded standby."""
        if key not in ('KEY_TV', 'KEY_POWER', 'KEY_HDMI', 'KEY_HDMI1', 'KEY_HDMI2', 'KEY_HDMI3', 'KEY_HDMI4'):
            raise ValueError('Unsupported restoration key')
        if not self.enabled or not self.config_file.exists():
            return False
        remote = None
        try:
            config = json.loads(self.config_file.read_text(encoding='utf-8'))
            fingerprint = config['certificate_sha256']
            token = config['token']
            if (not isinstance(fingerprint, str) or not re.fullmatch('[0-9a-f]{64}', fingerprint)
                    or not isinstance(token, str) or not token):
                raise ValueError('Invalid paired TV configuration')
            if not is_current():
                return False
            remote, updated = connect(config['host'], token, fingerprint)
            updated = config | updated  # Preserve the verified source binding on token refresh.
            if updated != config:
                save_config(self.config_file, updated)
            if not is_current() or not can_send():
                return False
            if not is_current():
                return False  # The power check can block while another call arrives.
            remote.send(json.dumps({'method': 'ms.remote.control', 'params': {
                'Cmd': 'Click', 'DataOfCmd': key, 'Option': 'false',
                'TypeOfRemote': 'SendRemoteKey'}}))
            logging.info('TV: paired Samsung key sent (%s)', key)
            return True
        except Exception as error:
            # Third-party errors may contain a token-bearing WebSocket URL.
            # Log only the exception type; power restoration must still run.
            logging.warning('TV: Samsung source restoration failed (%s)', type(error).__name__)
            return False
        finally:
            if remote:
                remote.close(timeout=0)
