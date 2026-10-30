# @test T-LLT-086
# @requirements LLR-TERM-TV-033, LLR-TERM-TV-031
# @environment portable
# @plan Load only registered drivers; exercise all seven API methods with temporary paired settings and mocked HTTP, WebSocket and CEC. Check truthful capabilities, unknown/transition states, source round trips, metadata timeout/redirect/oversize rejection, fresh LAN power fallback for ambiguous CEC, unchanged getters after writes, no constructor I/O, cancellation before/after authentication and before toggle, and controller fallback failure isolation.
# @pass Assertions pass without operating a TV; this does not qualify physical Samsung input or power behaviour.
"""Contract and controller integration tests for the simple TV driver API."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from zmala_terminal.linux.tv_control import TVControl
from zmala_terminal.linux.tv_plugins import load_driver
from zmala_terminal.linux.tv_plugins.api import TVDriver as BaseTVDriver
from zmala_terminal.linux.tv_plugins.samsung import driver as samsung


class TVPluginTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / 'tv.json'
        self.saved = {'host': '192.0.2.10', 'token': 'private-token',
                      'certificate_sha256': 'a' * 64,
                      'terminal_source': {'address': '2.0.0.0', 'key': 'KEY_HDMI'}}
        samsung.save_config(self.path, self.saved)
        metadata = patch.object(samsung.http.client, 'HTTPConnection')
        self.http = metadata.start()
        self.addCleanup(metadata.stop)
        self.http.return_value.getresponse.return_value.status = 503

    def driver(self, **config):
        return load_driver('samsung', {'config_file': self.path, **config})

    def test_registry_contract_and_construction_do_not_access_tv(self):
        with patch.object(samsung, 'connect') as connect, patch.object(samsung.http.client, 'HTTPConnection') as http:
            driver = self.driver()
            self.assertIsInstance(driver, BaseTVDriver)
            self.assertEqual(driver.get_capabilities(), {'set_current_input', 'get_power_status', 'set_power_off'})
            connect.assert_not_called()
            http.assert_not_called()
        for name in ('../samsung', 'os', 'unknown', None):
            with self.assertRaises(ValueError):
                load_driver(name, {})
        for method in ('get_current_input', 'set_power_on'):
            with self.assertRaises(NotImplementedError):
                getattr(driver, method)()

    def test_capabilities_and_unknown_observations_are_truthful(self):
        driver = self.driver(read_power=lambda: None, read_input=lambda: None, power_on=lambda: True)
        self.assertEqual(driver.get_capabilities(), {'get_power_status', 'get_current_input',
                         'set_current_input', 'set_power_on', 'set_power_off'})
        self.assertIsNone(driver.get_power_status())
        self.assertIsNone(driver.get_current_input())
        for value in (True, False, None, 'on', 1):
            observed = self.driver(read_power=lambda: value).get_power_status()
            self.assertIs(observed, value if isinstance(value, bool) else None)
        for source in ('0.0.0.0', '2.0.0.0', '3.0.0.0', None):
            driver = self.driver(read_input=lambda: source)
            self.assertEqual(driver.get_current_input(), source if source in ('0.0.0.0', '2.0.0.0') else None)

    def test_read_input_roundtrips_without_optimistic_updates(self):
        with patch.object(samsung, 'connect', return_value=(Mock(), self.saved)) as connect:
            driver = self.driver(read_input=lambda: '0.0.0.0')
            self.assertTrue(driver.set_current_input(driver.get_current_input()))
            self.assertEqual(json.loads(connect.return_value[0].send.call_args.args[0])['params']['DataOfCmd'], 'KEY_TV')
            self.assertTrue(driver.set_current_input('2.0.0.0'))
            self.assertEqual(driver.get_current_input(), '0.0.0.0')
            self.assertEqual(json.loads(connect.return_value[0].send.call_args.args[0])['params']['DataOfCmd'], 'KEY_HDMI')
            connect.reset_mock()
            for value in ('3.0.0.0', '', None, 'KEY_POWER'):
                self.assertFalse(driver.set_current_input(value))
            connect.assert_not_called()

    def test_model_metadata_is_bounded_and_does_not_follow_redirects(self):
        with patch.object(samsung.http.client, 'HTTPConnection') as factory:
            connection = factory.return_value
            response = connection.getresponse.return_value
            response.status = 200
            response.read.return_value = b'{"device":{"modelName":"Samsung test model"}}'
            self.assertEqual(self.driver().get_model(), 'Samsung test model')
            factory.assert_called_once_with('192.0.2.10', 8001, timeout=2)
            connection.request.assert_called_once_with('GET', '/api/v2/')
            response.read.assert_called_once_with(65537)
            connection.close.assert_called_once()
            response.status = 302
            self.assertIsNone(self.driver().get_model())
            response.status = 200
            for payload in (b'{}', b'[]', b'bad', b'{"device":{"modelName":42}}'):
                response.read.return_value = payload
                self.assertIsNone(self.driver().get_model())
            connection.request.side_effect = TimeoutError()
            self.assertIsNone(self.driver().get_model())
        self.assertEqual(self.driver(model='Known model').get_model(), 'Known model')
        self.path.unlink()
        self.assertIsNone(self.driver().get_model())

    def test_wake_and_standby_preserve_cancellation_and_never_blindly_toggle(self):
        wake = Mock(return_value=True)
        self.assertTrue(self.driver(power_on=wake).set_power_on())
        self.assertFalse(self.driver(power_on=wake, is_current=lambda: False).set_power_on())
        wake.assert_called_once()
        with patch.object(samsung, 'connect', return_value=(Mock(), self.saved)) as connect:
            for state, expected in ((False, True), (None, False)):
                self.assertEqual(self.driver(read_power=lambda: state).set_power_off(), expected)
            connect.assert_not_called()
            self.assertTrue(self.driver(read_power=lambda: True).set_power_off())
            connect.return_value[0].send.assert_called_once()
            connect.return_value[0].send.reset_mock()
            for after in (None, False):
                reader = Mock(side_effect=[True, after])
                self.assertFalse(self.driver(read_power=reader).set_power_off())
            connect.return_value[0].send.assert_not_called()
            self.assertFalse(self.driver(read_power=lambda: True, is_current=lambda: False).set_power_off())

    def test_controller_dispatches_common_api_and_contains_driver_failure(self):
        tv = TVControl(device='/dev/cec0')
        tv._driver_config_file = self.path
        tv._run = Mock(return_value='pwr-state: on (0)')
        with patch.object(samsung, 'connect', return_value=(Mock(), self.saved)) as connect:
            self.assertTrue(tv._driver_call('set_current_input', '2.0.0.0', is_current=lambda: True))
            self.assertFalse(tv._driver_call('set_current_input', '2.0.0.0', is_current=lambda: False))
            connect.assert_called_once()
            tv._network_enabled = False
            self.assertFalse(tv._driver_call('set_current_input', '2.0.0.0', is_current=lambda: True))
            tv._network_enabled = True
            self.assertFalse(tv._driver_call('arbitrary_method', is_current=lambda: True))
        with patch('zmala_terminal.linux.tv_control.load_driver', side_effect=RuntimeError('token=secret')):
            with self.assertLogs(level='WARNING') as logs:
                self.assertFalse(tv._driver_call('set_power_off', is_current=lambda: True))
            self.assertNotIn('secret', str(logs.output))
        for status, expected in (('on', True), ('standby', False), ('to-on', None), ('unknown', None)):
            tv._run.return_value = 'pwr-state: ' + status + ' (0)'
            self.assertIs(tv._driver_power_status(), expected)
        tv._run.side_effect = TimeoutError()
        self.assertIsNone(tv._driver_power_status())
        tv._run.side_effect = None
        self.assertTrue(tv._driver_power_on())
        tv._run.assert_called_with('--to', '0', '--image-view-on')

    def test_trial_source_is_explicit_and_does_not_save_unconfirmed_binding(self):
        with patch.object(samsung, 'connect', return_value=(Mock(), self.saved)) as connect:
            trial = {'address': '3.0.0.0', 'key': 'KEY_HDMI2'}
            self.assertTrue(self.driver(trial_source=trial).set_current_input('3.0.0.0'))
            self.assertEqual(json.loads(connect.return_value[0].send.call_args.args[0])['params']['DataOfCmd'], 'KEY_HDMI2')
            self.assertEqual(json.loads(self.path.read_text()), self.saved)
            self.assertFalse(self.driver().set_current_input('3.0.0.0'))
            self.assertFalse(self.driver(trial_source={'address':'3.0.0.0','key':'KEY_MUTE'}).set_current_input('3.0.0.0'))

    def test_metadata_power_fallback_is_fresh_and_never_guesses_on_failure(self):
        response = self.http.return_value.getresponse.return_value
        response.status = 200
        driver = self.driver(read_power=lambda: None)
        for state, expected in [('standby', False), ('on', True), ('to-on', None),
                                ('off', None), (True, None), ({}, None)]:
            response.read.return_value = json.dumps({'device': {'PowerState': state}}).encode()
            self.assertIs(driver.get_power_status(), expected)
        response.read.return_value = b'x' * 65537
        self.assertIsNone(driver.get_power_status())
        response.read.return_value = b'{"device": {"PowerState": "on"}}'
        response.status = 302
        self.assertIsNone(driver.get_power_status())
        self.http.return_value.request.side_effect = TimeoutError()
        self.assertIsNone(driver.get_power_status())
        self.assertFalse(driver.set_power_off())

    def test_settled_cec_avoids_network_query_and_metadata_cannot_cache_a_write(self):
        self.assertTrue(self.driver(read_power=lambda: True).get_power_status())
        self.http.assert_not_called()
        response = self.http.return_value.getresponse.return_value
        response.status = 200
        response.read.side_effect = [b'{"device":{"PowerState":"on"}}',
                                    b'{"device":{"PowerState":"standby"}}']
        with patch.object(samsung, 'connect', return_value=(Mock(), self.saved)) as connect:
            self.assertFalse(self.driver().set_power_off())
            connect.return_value[0].send.assert_not_called()
