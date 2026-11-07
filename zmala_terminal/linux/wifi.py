"""NetworkManager Wi-Fi enrollment using an application-owned connection.

Secrets enter through D-Bus, never command-line arguments. The
desktop user needs NetworkManager permission to create/activate connections.
"""
import os
import subprocess
import uuid
from zmala_terminal.common.connectivity import network_link_available
from zmala_terminal.common.setup_feedback import WifiSetupError


# @llr LLR-TERM-SETUP-029, LLR-TERM-NET-004
def _activation_failure(diagnostic):
    """Recognize only known C-locale nmcli reasons; never expose raw output.

    These are NetworkManager's activation/device reason messages. Unknown or
    changed wording falls back to a generic error, rather than guessing a cause.
    Authentication failures do not prove the password itself was incorrect.
    """
    prefix = 'Error: Connection activation failed: '
    line = next((line for line in diagnostic.splitlines() if line.startswith(prefix)), '')
    if not line:
        return 'connection_failed'
    reason = line[len(prefix):].rstrip('.')
    if reason.startswith('No suitable device found for this connection'):
        return 'wifi_unavailable'
    return {
        'The Wi-Fi network could not be found': 'network_not_found',
        'Secrets were required, but not provided': 'authentication_failed',
        'No agents were available for this request': 'authentication_failed',
        'No valid secrets': 'authentication_failed',
        'Invalid secrets': 'authentication_failed',
        '802.1X supplicant took too long to authenticate': 'authentication_failed',
        '802.1X supplicant failed': 'authentication_failed',
        'Not authorized to control networking': 'permission_denied',
        'Not authorized to perform this operation': 'permission_denied',
        'IP configuration could not be reserved (no available address, timeout, etc.)': 'address_failed',
        'IP configuration could not be reserved (no available address, timeout, etc)': 'address_failed',
        'DHCP client failed': 'address_failed',
        'DHCP client failed to start': 'address_failed',
        'DHCP client error': 'address_failed',
        'The connection attempt timed out': 'timed_out',
        'The device was removed': 'wifi_unavailable',
        'The device disappeared': 'wifi_unavailable',
        'Networking was disabled': 'wifi_unavailable',
    }.get(reason, 'connection_failed')


def _nmcli(arguments, timeout=40):
    try:
        result = subprocess.run(['nmcli', '--wait', '35', *arguments],
                                capture_output=True, timeout=timeout, text=True,
                                env=dict(os.environ, LC_ALL='C'))
    except subprocess.TimeoutExpired:
        raise WifiSetupError('timed_out') from None
    if result.returncode:
        # Keep potentially sensitive NetworkManager diagnostics out of logs.
        reason = 'timed_out' if result.returncode == 3 else 'connection_failed'
        if arguments[:2] == ['connection', 'up'] and result.returncode == 4:
            reason = _activation_failure(result.stderr)
        raise WifiSetupError(reason) from None
    return result.stdout.strip()


# @llr LLR-TERM-NET-004
def _add_connection(wifi, identifier, name):
    # D-Bus keeps passwords out of argv and persists the connection in NM's
    # protected system directory; no temporary credential file is necessary.
    from gi.repository import Gio, GLib
    variant = GLib.Variant
    settings = {
        'connection': {'id': variant('s', name), 'uuid': variant('s', identifier),
                       'type': variant('s', '802-11-wireless'), 'autoconnect': variant('b', True)},
        '802-11-wireless': {'ssid': variant('ay', list(wifi['ssid'].encode('utf-8'))),
                            'mode': variant('s', 'infrastructure'), 'hidden': variant('b', wifi['hidden']),
                            # Mains-powered video terminals need predictable RTP latency.
                            'powersave': variant('u', 2)},
        'ipv4': {'method': variant('s', 'auto')}, 'ipv6': {'method': variant('s', 'auto')},
    }
    if wifi['security'] == 'WPA':
        settings['802-11-wireless-security'] = {
            'key-mgmt': variant('s', 'wpa-psk'), 'psk': variant('s', wifi['password'])}
    try:
        proxy = Gio.DBusProxy.new_for_bus_sync(Gio.BusType.SYSTEM, Gio.DBusProxyFlags.NONE, None,
            'org.freedesktop.NetworkManager', '/org/freedesktop/NetworkManager/Settings',
            'org.freedesktop.NetworkManager.Settings', None)
        proxy.call_sync('AddConnection', variant('(a{sa{sv}})', (settings,)),
                        Gio.DBusCallFlags.NONE, 35000, None)
    except GLib.Error as error:
        remote = Gio.DBusError.get_remote_error(error)
        denied = remote in ('org.freedesktop.NetworkManager.Settings.PermissionDenied',
                            'org.freedesktop.NetworkManager.PermissionDenied',
                            'org.freedesktop.DBus.Error.AccessDenied')
        raise WifiSetupError('permission_denied' if denied else 'connection_failed') from None


def forget_wifi(wifi, profile):
    name = wifi.get('linux_profile', '')
    identifier = wifi.get('linux_uuid', '')
    if not name.startswith('ZmalaCall-' + profile + '-') or not identifier:
        return
    # Deletion can have succeeded just before a crash. Retrying is harmless.
    if identifier not in _nmcli(['-t', '-f', 'UUID', 'connection', 'show']).splitlines():
        return
    _nmcli(['connection', 'delete', 'uuid', identifier])


# @llr LLR-TERM-SETUP-029
def connect_wifi(wifi, profile, mode='existing-link', cancelled=None):
    if mode == 'existing-link':
        if not network_link_available():
            raise OSError('Connect the terminal to a network before testing QR setup')
        return dict(wifi, connection_mode=mode)
    if cancelled and cancelled.is_set():
        raise OSError('Wi-Fi setup cancelled')
    identifier = str(uuid.uuid4())
    name = 'ZmalaCall-' + profile + '-' + identifier[:12]
    loaded = False
    try:
        _add_connection(wifi, identifier, name)
        loaded = True
        _nmcli(['connection', 'up', 'uuid', identifier])
        if cancelled and cancelled.is_set():
            raise OSError('Wi-Fi setup cancelled')
        return dict(wifi, linux_profile=name, linux_uuid=identifier, connection_mode=mode)
    except Exception:
        if loaded:
            try:
                _nmcli(['connection', 'delete', 'uuid', identifier])
            except OSError:
                pass
        raise
