# @test T-LLT-026
# @requirements LLR-TERM-SETUP-023, LLR-TERM-SETUP-026, LLR-TERM-UI-018, LLR-TERM-NET-006, LLR-TERM-MAINT-013
# @environment portable
# @plan Feed runtime display, firewall and Bluetooth helpers synthetic observations. Assert supported connected display selection, interface-scoped firewall rules, bounded RAM journal/zram policy and exclusive verified Presenter pairing. Exercise BlueZ initialization, discovery, asynchronous trust/connect, retry backoff and agent restart with fake D-Bus and temporary state files. Effective mounts and reboot persistence require HLT.
# @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

"""Pi runtime display, Bluetooth and host-policy boundaries."""
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[3]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'build_tools/linux' / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


guard = module('ssh-guard')
pair = module('pair-presenter')
kiosk = module('kiosk-session')


class PiInstallTests(unittest.TestCase):
    def test_runtime_storage_policy_uses_bounded_ram_journal_and_zram(self):
        from tests.support.host_policy import assert_storage_policy
        assert_storage_policy(self)

    def pairing(self):
        """Fake the D-Bus transport, retaining the actual pairing state machine."""
        class BusError(Exception):
            message = 'injected bus failure'
        bus, loop = Mock(), Mock()
        bus.call_sync.return_value.unpack.return_value = ()
        glib = SimpleNamespace(Error=BusError, MainLoop=Mock(return_value=loop),
                               Variant=Mock(side_effect=lambda signature, value: (signature, value)),
                               timeout_add_seconds=Mock())
        gio = SimpleNamespace(bus_get_sync=Mock(return_value=bus), BusType=SimpleNamespace(SYSTEM=1),
                              DBusCallFlags=SimpleNamespace(NONE=0), DBusNodeInfo=Mock())
        gio.DBusNodeInfo.new_for_xml.return_value.interfaces = ['agent-interface']
        with patch.dict('sys.modules', {'gi.repository': SimpleNamespace(Gio=gio, GLib=glib)}):
            agent = pair.Pairing()
        bus.register_object.assert_called_once_with(pair.AGENT, 'agent-interface', agent.authorize, None, None)
        self.assertEqual(bus.call_sync.call_args.args[3:5], ('RegisterAgent', ('(os)', (pair.AGENT, 'NoInputNoOutput'))))
        bus.reset_mock()
        return agent, bus, glib

    def test_pairing_discovers_one_device_then_trusts_and_connects_asynchronously(self):
        agent, bus, _ = self.pairing()
        objects = {'/adapter': {'org.bluez.Adapter1': {'Powered': False}},
                   '/remote': {'org.bluez.Device1': {'Name': pair.NAME, 'UUIDs': [pair.HID], 'RSSI': -35}}}
        bus.call_sync.return_value.unpack.side_effect = lambda: (objects,)
        with tempfile.TemporaryDirectory() as folder, patch.object(pair, 'STATUS', Path(folder)/'status.json'), \
                patch.object(pair, 'BOND', Path(folder)/'bond.json'), patch.object(pair.time, 'monotonic', return_value=100):
            agent.retry_at = 101
            self.assertTrue(agent.tick())
            bus.call.assert_not_called()
            self.assertEqual(agent.discovery, '/adapter')
            methods = [c.args[3] for c in bus.call_sync.call_args_list]
            self.assertEqual(methods, ['GetManagedObjects', 'Set', 'SetDiscoveryFilter', 'StartDiscovery'])
            agent.retry_at = 0
            self.assertTrue(agent.tick())
            self.assertEqual(agent.target, '/remote')
            self.assertEqual(bus.call.call_args.args[1:4], ('/remote', 'org.bluez.Device1', 'Pair'))
            self.assertEqual(bus.call.call_args.args[7], 45000)
            self.assertTrue(agent.tick())
            self.assertEqual(bus.call.call_count, 1)
            agent.paired(bus, 'result', None)
            bus.call_finish.assert_called_once_with('result')
            self.assertIsNone(agent.target)
            self.assertEqual(bus.call.call_args.args[3], 'Connect')
            self.assertEqual(agent.state['state'], 'paired')
            token = agent.state['bond']
            objects['/remote']['org.bluez.Device1']['Paired'] = True
            self.assertTrue(agent.tick())
            self.assertIsNone(agent.discovery)
            self.assertEqual(agent.state['bond'], token)
            self.assertIn('StopDiscovery', [c.args[3] for c in bus.call_sync.call_args_list])

    def test_pairing_bus_failure_restarts_agent_and_pair_failure_backs_off(self):
        agent, bus, glib = self.pairing()
        with tempfile.TemporaryDirectory() as folder, patch.object(pair, 'STATUS', Path(folder)/'status.json'), \
                patch.object(pair.time, 'monotonic', return_value=20):
            bus.call_sync.return_value.unpack.return_value = ({},)
            self.assertTrue(agent.tick())
            self.assertEqual(agent.state, {'state': 'bluetooth_unavailable'})
            agent.target = '/remote'
            bus.call_finish.side_effect = glib.Error()
            agent.paired(bus, 'result', None)
            self.assertIsNone(agent.target)
            self.assertEqual(agent.retry_at, 30)
            self.assertEqual(agent.state, {'state': 'unpaired'})
            agent.connected(bus, 'result', None)
            bus.call_finish.side_effect = None
            agent.connected(bus, 'result', None)
            bus.call_sync.side_effect = glib.Error()
            self.assertFalse(agent.tick())
            self.assertTrue(agent.failed)
            agent.loop.quit.assert_called_once()

    def test_pairing_main_exits_on_lost_agent_and_schedules_healthy_agent(self):
        for initial, failed in [(False, False), (True, True), (True, False)]:
            agent = Mock(failed=failed)
            agent.tick.return_value = initial
            with patch.object(pair, 'Pairing', return_value=agent):
                if not initial or failed:
                    with self.assertRaises(SystemExit) as error:
                        pair.main()
                    self.assertEqual(error.exception.code, 1)
                else:
                    pair.main()
            self.assertEqual(agent.loop.run.called, initial)
            if initial:
                agent.GLib.timeout_add_seconds.assert_called_once_with(2, agent.tick)


    def test_boot_guard_prepares_sshd_directory_before_configuration_probe(self):
        events = []
        config, run_dir, rules_file, temp_file = Mock(), Mock(), Mock(), Mock()
        config.read_text.return_value = 'eth0\n'
        run_dir.mkdir.side_effect = lambda **kwargs: events.append('directory')
        rules_file.with_suffix.return_value = temp_file
        def run(args, **kwargs):
            events.append(args[0])
            if args[0] == '/usr/sbin/sshd':
                self.assertIn('directory', events)
                return Mock(stdout='port 2222\n')
            self.assertIn('22, 2222', kwargs['input'])
        paths = {'/etc/zmalacall/ssh-interface': config, '/run/sshd': run_dir,
                 '/etc/nftables.d/zmala-ssh.nft': rules_file}
        with patch.object(guard, 'Path', side_effect=paths.__getitem__), \
                patch.object(guard.subprocess, 'run', side_effect=run), patch.object(guard.os, 'replace') as replace:
            guard.main()
        self.assertEqual(events, ['directory', '/usr/sbin/sshd', '/usr/sbin/nft', '/usr/sbin/nft'])
        replace.assert_called_once_with(temp_file, rules_file)

    def test_display_mode_uses_only_connected_supported_outputs(self):
        query = ('HDMI-1 disconnected\n   1280x720 60.0\nHDMI-2 connected primary 3840x2160+0+0\n'
                 '   3840x2160 30.0*+\n   1280x720 60.0 50.0\nDP-1 connected\n   1024x768 60.0\n')
        self.assertEqual(kiosk.display_outputs(query, '1280x720'), ['HDMI-2'])
        self.assertEqual(kiosk.display_outputs(query, '1920x1080'), [])

    def test_guard_covers_ipv4_ipv6_custom_ports_and_socket_activation(self):
        value = guard.rules('eth0', [2222, 2222])
        self.assertIn('table inet zmala_ssh', value)
        self.assertIn('hook input priority -10', value)
        self.assertIn('iifname != "eth0" tcp dport { 22, 2222 } counter drop', value)
        self.assertNotIn('flush ruleset', value)
        for interface in ('eth0"; accept', '', '../eth0', 'x' * 16):
            with self.assertRaises(ValueError):
                guard.rules(interface, [22])
        with self.assertRaises(ValueError):
            guard.rules('eth0', [65536])


    def test_pair_only_one_presenter_currently_advertising_hid(self):
        props = {'Name': pair.NAME, 'UUIDs': [pair.HID], 'RSSI': -40}
        self.assertEqual(pair.candidate({'/one': props}), '/one')
        self.assertIsNone(pair.candidate({'/one': props, '/two': props}))
        for invalid in ({**props, 'Name': 'Keyboard'}, {**props, 'UUIDs': []},
                        {**props, 'Blocked': True}, {**props, 'Paired': True},
                        {key: value for key, value in props.items() if key != 'RSSI'}):
            self.assertIsNone(pair.candidate({'/one': invalid}))

    def test_agent_rejects_other_devices_and_passkey_requests(self):
        agent = pair.Pairing.__new__(pair.Pairing)
        agent.target = '/chosen'
        for method, path, allowed in [('RequestAuthorization', '/other', False),
                                      ('RequestConfirmation', '/chosen', True),
                                      ('RequestPasskey', '/chosen', False),
                                      ('AuthorizeService', '/chosen', True)]:
            parameters, invocation = Mock(), Mock()
            parameters.unpack.return_value = (path,)
            agent.authorize(None, None, None, None, method, parameters, invocation)
            self.assertEqual(invocation.return_value.called, allowed)
            self.assertEqual(invocation.return_dbus_error.called, not allowed)

    def test_status_changes_written_atomically_without_device_secrets(self):
        agent = pair.Pairing.__new__(pair.Pairing)
        agent.state = None
        with tempfile.TemporaryDirectory() as folder, patch.object(pair, 'STATUS', Path(folder) / 'status.json'):
            agent.publish('paired')
            self.assertEqual(json.loads(pair.STATUS.read_text()), {'state': 'paired'})
            self.assertFalse(pair.STATUS.with_suffix('.tmp').exists())

    def test_pairing_token_survives_restart_but_changes_when_repaired(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(pair, 'BOND', Path(folder)/'bond.json'):
            first = pair.bond_token('/remote')
            self.assertEqual(first, pair.bond_token('/remote'))
            renewed = pair.bond_token('/remote', renew=True)
            self.assertNotEqual(first, renewed)
            self.assertEqual(renewed, pair.bond_token('/remote'))
            self.assertNotEqual(renewed, pair.bond_token('/replacement'))


if __name__ == '__main__':
    unittest.main()
