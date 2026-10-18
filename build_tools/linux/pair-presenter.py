"""First-run Presenter+ pairing on BlueZ; no desktop or working remote needed.

Discover only while there is no saved Presenter. Pair one matching advertised
device at a time; the agent rejects authorization for every other device.
Runs outside Tk/media, with bounded D-Bus calls and retry backoff.
"""
import json
import logging
import os
from pathlib import Path
import time
import uuid

NAME = 'Microsoft Presenter+'
HID = '00001812-0000-1000-8000-00805f9b34fb'
STATUS = Path('/run/zmalacall-pairing/status.json')
AGENT = '/org/zmalacall/PresenterAgent'
BOND = Path('/var/lib/zmalacall-pairing/bond.json')


def bond_token(device, renew=False):
    """An opaque test identity, never a Bluetooth key; stable across reboots."""
    try:
        saved = json.loads(BOND.read_text())
        if not renew and saved.get('device') == device and isinstance(saved.get('token'), str):
            return saved['token']
    except (OSError, ValueError, AttributeError):
        pass
    token = uuid.uuid4().hex
    temp = BOND.with_suffix('.tmp')
    temp.write_text(json.dumps({'device': device, 'token': token}))
    os.replace(temp, BOND)
    return token
XML = '''<node><interface name="org.bluez.Agent1">
<method name="Release"/><method name="Cancel"/>
<method name="RequestAuthorization"><arg type="o" direction="in"/></method>
<method name="RequestConfirmation"><arg type="o" direction="in"/><arg type="u" direction="in"/></method>
<method name="AuthorizeService"><arg type="o" direction="in"/><arg type="s" direction="in"/></method>
<method name="RequestPinCode"><arg type="o" direction="in"/><arg type="s" direction="out"/></method>
<method name="RequestPasskey"><arg type="o" direction="in"/><arg type="u" direction="out"/></method>
</interface></node>'''


def is_presenter(properties):
    return properties.get('Name') == NAME and HID in properties.get('UUIDs', [])


# @llr TLLR021
def candidate(devices):
    """Do not choose between multiple nearby remotes or pair stale cache entries."""
    matches = [path for path, props in devices.items() if is_presenter(props)
               and not props.get('Paired') and not props.get('Blocked') and 'RSSI' in props]
    return matches[0] if len(matches) == 1 else None


class Pairing:
    def __init__(self):
        from gi.repository import Gio, GLib
        self.Gio, self.GLib = Gio, GLib
        self.bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        self.target = None
        self.retry_at = 0
        self.state = None
        self.discovery = None
        self.loop = GLib.MainLoop()
        self.failed = False
        info = Gio.DBusNodeInfo.new_for_xml(XML).interfaces[0]
        self.bus.register_object(AGENT, info, self.authorize, None, None)
        self.call('/org/bluez', 'org.bluez.AgentManager1', 'RegisterAgent', '(os)', (AGENT, 'NoInputNoOutput'))

    def call(self, path, interface, method, signature=None, values=()):
        args = self.GLib.Variant(signature, values) if signature else None
        return self.bus.call_sync('org.bluez', path, interface, method, args, None,
                                  self.Gio.DBusCallFlags.NONE, 3000, None).unpack()

    def set_property(self, path, interface, name, value):
        self.call(path, 'org.freedesktop.DBus.Properties', 'Set', '(ssv)',
                  (interface, name, self.GLib.Variant('b', value)))

    def authorize(self, connection, sender, path, interface, method, parameters, invocation):
        values = parameters.unpack()
        allowed = method in ('Release', 'Cancel') or (
            method in ('RequestAuthorization', 'RequestConfirmation', 'AuthorizeService')
            and values and values[0] == self.target)
        if allowed:
            invocation.return_value(None)
        else:
            invocation.return_dbus_error('org.bluez.Error.Rejected', 'Only the selected Presenter can pair')

    def publish(self, state, bond=None):
        payload = {'state': state}
        if bond:
            payload['bond'] = bond
        if payload != self.state:
            temp = STATUS.with_suffix('.tmp')
            temp.write_text(json.dumps(payload) + '\n')
            temp.chmod(0o644)
            os.replace(temp, STATUS)
            logging.info('Remote setup: %s', state)
            self.state = payload

    def paired(self, connection, result, unused):
        target = self.target
        try:
            connection.call_finish(result)
            self.set_property(target, 'org.bluez.Device1', 'Trusted', True)
            # Pair normally connects HID too. Do not block agent dispatch while
            # waiting for Connect; the normal BlueZ reconnection policy applies.
            self.bus.call('org.bluez', target, 'org.bluez.Device1', 'Connect', None, None,
                          self.Gio.DBusCallFlags.NONE, 10000, None, self.connected, None)
            self.publish('paired', bond_token(target, renew=True))
        except self.GLib.Error as error:
            logging.warning('Pairing did not finish: %s', error.message)
            self.retry_at = time.monotonic() + 10
            self.publish('unpaired')
        finally:
            self.target = None

    def connected(self, connection, result, unused):
        try:
            connection.call_finish(result)
        except self.GLib.Error:
            logging.info('Waiting for the paired remote to reconnect')

    def tick(self):
        try:
            objects, = self.call('/', 'org.freedesktop.DBus.ObjectManager', 'GetManagedObjects')
            adapters = {path: interfaces['org.bluez.Adapter1'] for path, interfaces in objects.items()
                        if 'org.bluez.Adapter1' in interfaces}
            devices = {path: interfaces['org.bluez.Device1'] for path, interfaces in objects.items()
                       if 'org.bluez.Device1' in interfaces}
            if not adapters:
                self.publish('bluetooth_unavailable')
                return True
            adapter, props = next(iter(adapters.items()))
            if not props.get('Powered'):
                self.set_property(adapter, 'org.bluez.Adapter1', 'Powered', True)
            saved = [path for path, props in devices.items() if is_presenter(props) and props.get('Paired')]
            if saved:
                for path in saved:
                    if not devices[path].get('Trusted') and not devices[path].get('Blocked'):
                        self.set_property(path, 'org.bluez.Device1', 'Trusted', True)
                if self.discovery:
                    self.call(self.discovery, 'org.bluez.Adapter1', 'StopDiscovery')
                    self.discovery = None
                self.publish('paired', bond_token(saved[0]))
                return True
            if self.target:
                return True
            self.publish('unpaired')
            if not self.discovery:
                self.call(adapter, 'org.bluez.Adapter1', 'SetDiscoveryFilter', '(a{sv})',
                          ({'Transport': self.GLib.Variant('s', 'le'),
                            'UUIDs': self.GLib.Variant('as', [HID])},))
                self.call(adapter, 'org.bluez.Adapter1', 'StartDiscovery')
                self.discovery = adapter
            target = candidate(devices)
            if target and time.monotonic() >= self.retry_at:
                self.target = target
                self.publish('pairing')
                self.bus.call('org.bluez', target, 'org.bluez.Device1', 'Pair', None, None,
                              self.Gio.DBusCallFlags.NONE, 45000, None, self.paired, None)
        except self.GLib.Error as error:
            logging.warning('Bluetooth setup unavailable: %s', error.message)
            self.publish('bluetooth_unavailable')
            # A restarted BlueZ loses this connection's registered agent. Let
            # systemd recreate it instead of silently scanning without an agent.
            self.failed = True
            self.loop.quit()
            return False
        return True


def main():
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    pairing = Pairing()
    if not pairing.tick():
        raise SystemExit(1)
    pairing.GLib.timeout_add_seconds(2, pairing.tick)
    pairing.loop.run()
    if pairing.failed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
