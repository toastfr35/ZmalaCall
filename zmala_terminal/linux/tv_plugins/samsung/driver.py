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
import http.client
import ipaddress
import json
import logging
from pathlib import Path
import re
import socket
import ssl
import time
from urllib.parse import urlencode


from zmala_terminal.linux.tv_plugins.api import TVDriver as BaseTVDriver


DEFAULT_CONFIG = Path(__file__).resolve().parents[3] / 'data/tv-remote.json'


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


# @llr LLR-TERM-TV-031
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


# @llr LLR-TERM-TV-033
class TVDriver(BaseTVDriver):
    """Paired Samsung LAN control, optionally backed by bounded CEC callbacks.

    config_file points to private paired credentials. read_power, read_input and
    power_on are optional controller-supplied CEC operations, not user settings.
    is_current fences each operation against newer calls, including after I/O.
    A fresh instance captures these callbacks for one operation.
    """

    def __init__(self, config: dict):
        super().__init__(config)
        self.config_file = Path(config.get('config_file', DEFAULT_CONFIG))
        self._is_current = config.get('is_current', lambda: True)

    def _metadata(self) -> dict:
        """Read fresh local observations; never cache a command as TV state.

        Port 8001 remains available in standby on the tested Q60C, while its
        authenticated WebSocket port closes. Metadata contains no credentials;
        all commands still require the separately pinned TLS connection.
        """
        connection = None
        try:
            settings = json.loads(self.config_file.read_text(encoding='utf-8'))
            host = str(ipaddress.ip_address(settings['host']))
            connection = http.client.HTTPConnection(host, 8001, timeout=2)
            connection.request('GET', '/api/v2/')
            response = connection.getresponse()
            if response.status != 200:
                return {}
            payload = response.read(65537)
            if len(payload) > 65536:
                return {}
            device = json.loads(payload).get('device', {})
            return device if isinstance(device, dict) else {}
        except (OSError, ValueError, TypeError, KeyError, AttributeError, http.client.HTTPException):
            return {}
        finally:
            if connection:
                connection.close()

    def get_model(self) -> str | None:
        model = self.config.get('model')
        if not isinstance(model, str) or not model.strip():
            model = self._metadata().get('modelName')
        return model if isinstance(model, str) and model.strip() else None

    def get_capabilities(self) -> set[str]:
        capabilities = {'set_current_input', 'get_power_status', 'set_power_off'}
        if callable(self.config.get('read_input')):
            capabilities.add('get_current_input')
        if callable(self.config.get('power_on')):
            capabilities.add('set_power_on')
        return capabilities

    def get_power_status(self) -> bool | None:
        reader = self.config.get('read_power')
        power = reader() if callable(reader) else None
        if isinstance(power, bool):
            return power
        # This Q60C reports CEC 'to-on' indefinitely in standby. Ask the TV's
        # local metadata endpoint instead; unreachable is unknown, never off.
        state = self._metadata().get('PowerState')
        return {'on': True, 'standby': False}.get(state) if isinstance(state, str) else None

    def get_current_input(self) -> str | None:
        if 'get_current_input' not in self.get_capabilities():
            raise NotImplementedError
        source = self.config['read_input']()
        # Only sources this LAN driver can select are restorable identifiers.
        if source == '0.0.0.0':
            return source
        binding = self._binding()
        return source if source is not None and source == binding.get('address') else None

    def set_power_on(self) -> bool:
        if 'set_power_on' not in self.get_capabilities():
            raise NotImplementedError
        return bool(self._is_current() and self.config['power_on']())

    # @llr LLR-TERM-TV-031
    def set_power_off(self) -> bool:
        if 'set_power_off' not in self.get_capabilities():
            raise NotImplementedError
        if not self._is_current():
            return False
        power = self.get_power_status()
        if not self._is_current():
            return False
        if power is False:
            return True
        if power is not True:
            return False
        # Query after authentication: pairing may take seconds. Unknown is never
        # permission to toggle. The callback is bounded by the CEC transport.
        return self._send_key('KEY_POWER', self._is_current,
                              lambda: self.get_power_status() is True)

    def _binding(self):
        try:
            value = json.loads(self.config_file.read_text(encoding='utf-8'))
            binding = value.get('terminal_source', {})
            if (isinstance(binding, dict) and
                    isinstance(binding.get('address'), str) and
                    re.fullmatch(r'[1-9a-f](\.[0-9a-f]){3}', binding['address']) and
                    binding.get('key') in ('KEY_HDMI', 'KEY_HDMI1', 'KEY_HDMI2', 'KEY_HDMI3', 'KEY_HDMI4')):
                return binding
            return {}
        except (OSError, ValueError, TypeError, AttributeError):
            return {}

    # @llr LLR-TERM-TV-031
    def set_current_input(self, input_id: str) -> bool:
        if input_id == '0.0.0.0':
            return self._send_key('KEY_TV', self._is_current)
        if not isinstance(input_id, str) or not re.fullmatch(r'[1-9a-f](\.[0-9a-f]){3}', input_id):
            return False
        binding = self._binding()
        # The guided input test can try a key before the user confirms it.
        # Ordinary calls only use the persisted, connector-bound result.
        trial = self.config.get('trial_source', {})
        if trial:
            binding = trial
        if (binding.get('address') != input_id or binding.get('key') not in
                ('KEY_HDMI', 'KEY_HDMI1', 'KEY_HDMI2', 'KEY_HDMI3', 'KEY_HDMI4')):
            return False
        return self._send_key(binding['key'], self._is_current)

    def _send_key(self, key, is_current, can_send=lambda: True):
        """Keep remote commands restricted to source selection and guarded standby."""
        if key not in ('KEY_TV', 'KEY_POWER', 'KEY_HDMI', 'KEY_HDMI1', 'KEY_HDMI2', 'KEY_HDMI3', 'KEY_HDMI4'):
            raise ValueError('Unsupported restoration key')
        if not self.config_file.exists():
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
