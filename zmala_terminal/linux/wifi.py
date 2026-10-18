"""NetworkManager Wi-Fi enrollment using an application-owned connection.

Secrets enter through D-Bus, never command-line arguments. The
desktop user needs NetworkManager permission to create/activate connections.
"""
import subprocess
import uuid
from zmala_terminal.common.connectivity import network_link_available


def _nmcli(arguments, timeout=40):
    result = subprocess.run(['nmcli', '--wait', '35', *arguments],
                            capture_output=True, timeout=timeout, text=True)
    if result.returncode:
        # Keep potentially sensitive NetworkManager diagnostics out of logs.
        raise OSError('NetworkManager operation failed; check Wi-Fi and user permissions')
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
    except GLib.Error:
        raise OSError('Wi-Fi setup failed; check NetworkManager user permissions') from None


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
