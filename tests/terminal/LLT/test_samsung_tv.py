# @test T-LLT-033
# @requirements LLR-TERM-TV-031
# @environment portable
# @plan Mock Samsung network responses, identity changes, timeouts and encrypted transport; assert pinned-TV commands, token lifecycle, bounded retries and truthful failure results. Run the pairing CLI with fake network/save boundaries and assert private pin persistence, bounded connect timeout and connection closure on success or failure.
# @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

"""Verify private authentication, certificate pins and restricted TV commands."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from zmala_terminal.linux.samsung_tv import SamsungTV, connect, save_config


class SamsungTVTests(unittest.TestCase):
    def test_pairing_helper_persists_pin_only_after_connection_and_always_closes(self):
        from tests.terminal.LLT.test_pi_install import module
        helper = module('pair-samsung-tv')
        with tempfile.TemporaryDirectory() as directory, patch.object(helper, 'connect') as connection, \
                patch.object(helper, 'save_config') as save, patch('builtins.print') as output, \
                patch.object(sys, 'argv', ['pair', '192.0.2.1', '--config', str(Path(directory)/'tv.json')]):
            remote = Mock()
            connection.return_value = (remote, {'certificate_sha256':'pin'})
            self.assertEqual(helper.main(), 0)
            connection.assert_called_once_with('192.0.2.1', timeout=30)
            save.assert_called_once_with(Path(directory)/'tv.json', {'certificate_sha256':'pin'})
            remote.close.assert_called_once_with(timeout=0)
            remote.reset_mock(); save.side_effect = OSError('private failure data')
            self.assertEqual(helper.main(), 1)
            remote.close.assert_called_once_with(timeout=0)
            self.assertNotIn('private failure data', str(output.call_args_list))
            connection.side_effect = RuntimeError('offline')
            remote.reset_mock(); save.reset_mock()
            self.assertEqual(helper.main(), 1)
            remote.close.assert_not_called()
            save.assert_not_called()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'tv.json'
        self.config = {'host': '192.168.1.130', 'token': 'private-token',
                       'certificate_sha256': 'a' * 64}
        self.tv = SamsungTV(self.path)

    def test_unpaired_tv_never_connects(self):
        with patch('zmala_terminal.linux.samsung_tv.connect') as connection:
            self.assertFalse(self.tv.restore_broadcast(lambda: True))
        connection.assert_not_called()

    def test_only_live_tv_key_is_sent_and_pin_is_required(self):
        save_config(self.path, self.config)
        remote = Mock()
        with patch('zmala_terminal.linux.samsung_tv.connect', return_value=(remote, self.config)) as connection:
            self.assertTrue(self.tv.restore_broadcast(lambda: True))
        connection.assert_called_once_with(self.config['host'], self.config['token'], 'a' * 64)
        command = json.loads(remote.send.call_args.args[0])
        self.assertEqual(command['params'], {'Cmd': 'Click', 'DataOfCmd': 'KEY_TV',
                                            'Option': 'false', 'TypeOfRemote': 'SendRemoteKey'})
        remote.close.assert_called_once()

    def test_superseded_call_during_connection_sends_no_key(self):
        save_config(self.path, self.config)
        remote = Mock()
        current = Mock(side_effect=[True, False])
        with patch('zmala_terminal.linux.samsung_tv.connect', return_value=(remote, self.config)):
            self.assertFalse(self.tv.restore_broadcast(current))
        remote.send.assert_not_called()
        remote.close.assert_called_once()

    def test_invalid_or_missing_pin_never_connects(self):
        for fingerprint in (None, 'bad', ''):
            save_config(self.path, self.config | {'certificate_sha256': fingerprint})
            with patch('zmala_terminal.linux.samsung_tv.connect') as connection, self.assertLogs(level='WARNING'):
                self.assertFalse(self.tv.restore_broadcast(lambda: True))
            connection.assert_not_called()

    def test_connection_failure_never_logs_credentials(self):
        save_config(self.path, self.config)
        with patch('zmala_terminal.linux.samsung_tv.connect', side_effect=RuntimeError('URL?token=private-token')):
            with self.assertLogs(level='WARNING') as logs:
                self.assertFalse(self.tv.restore_broadcast(lambda: True))
        self.assertNotIn('private-token', ' '.join(logs.output))

    def test_refreshed_token_is_saved(self):
        save_config(self.path, self.config)
        updated = self.config | {'token': 'renewed-token'}
        with patch('zmala_terminal.linux.samsung_tv.connect', return_value=(Mock(), updated)):
            self.assertTrue(self.tv.restore_broadcast(lambda: True))
        self.assertEqual(json.loads(self.path.read_text()), updated)

    def test_power_key_requires_fresh_on_confirmation(self):
        save_config(self.path, self.config)
        for on in (False, True):
            with self.subTest(on=on):
                remote = Mock()
                is_on = Mock(return_value=on)
                with patch('zmala_terminal.linux.samsung_tv.connect', return_value=(remote, self.config)):
                    self.assertEqual(self.tv.standby_if_on(lambda: True, is_on), on)
                is_on.assert_called_once()
                if on:
                    command = json.loads(remote.send.call_args.args[0])
                    self.assertEqual(command['params']['DataOfCmd'], 'KEY_POWER')
                else:
                    remote.send.assert_not_called()

    def test_verified_source_key_requires_same_connector_and_preserves_binding(self):
        binding = {'address': '1.0.0.0', 'key': 'KEY_HDMI'}
        saved = self.config | {'terminal_source': binding}
        save_config(self.path, saved)
        remote = Mock()
        renewed = self.config | {'token': 'renewed-token'}
        with patch('zmala_terminal.linux.samsung_tv.connect', return_value=(remote, renewed)):
            self.assertTrue(self.tv.select_terminal('1.0.0.0', lambda: True))
        command = json.loads(remote.send.call_args.args[0])
        self.assertEqual(command['params']['DataOfCmd'], 'KEY_HDMI')
        self.assertEqual(json.loads(self.path.read_text()), renewed | {'terminal_source': binding})
        for address in ('2.0.0.0', 'f.f.f.f', '0.0.0.0'):
            with patch('zmala_terminal.linux.samsung_tv.connect') as connection:
                self.assertFalse(self.tv.select_terminal(address, lambda: True))
            connection.assert_not_called()

    def test_unverified_or_unsafe_source_binding_never_sends_command(self):
        for binding in ({}, {'address': '1.0.0.0', 'key': 'KEY_POWER'}, None):
            save_config(self.path, self.config | {'terminal_source': binding})
            with patch('zmala_terminal.linux.samsung_tv.connect') as connection:
                self.assertFalse(self.tv.select_terminal('1.0.0.0', lambda: True))
            connection.assert_not_called()

    def test_unexpected_remote_keys_are_rejected(self):
        with self.assertRaises(ValueError):
            self.tv._send_key('KEY_MUTE', lambda: True)

    def test_new_call_during_power_query_prevents_toggle(self):
        save_config(self.path, self.config)
        current = [True]
        remote = Mock()
        def is_on():
            current[0] = False
            return True
        with patch('zmala_terminal.linux.samsung_tv.connect', return_value=(remote, self.config)):
            self.assertFalse(self.tv.standby_if_on(lambda: current[0], is_on))
        remote.send.assert_not_called()

    def test_changed_tls_certificate_blocks_websocket_handshake(self):
        tls = Mock()
        tls.getpeercert.return_value = b'a different certificate'
        context = Mock()
        context.wrap_socket.return_value = tls
        factory = Mock()
        with patch.dict(sys.modules, {'websocket': SimpleNamespace(create_connection=factory)}), \
                patch('zmala_terminal.linux.samsung_tv.ssl.SSLContext', return_value=context), \
                patch('zmala_terminal.linux.samsung_tv.socket.create_connection'):
            with self.assertRaisesRegex(ValueError, 'certificate changed'):
                connect(self.config['host'], self.config['token'], self.config['certificate_sha256'])
        factory.assert_not_called()
        tls.close.assert_called_once()

    def test_unauthorized_connection_closes_without_sending_keys(self):
        remote = Mock()
        remote.recv.return_value = json.dumps({'event': 'ms.channel.unauthorized'})
        tls = Mock()
        tls.getpeercert.return_value = b'certificate'
        context = Mock()
        context.wrap_socket.return_value = tls
        with patch.dict(sys.modules, {'websocket': SimpleNamespace(create_connection=Mock(return_value=remote))}), \
                patch('zmala_terminal.linux.samsung_tv.ssl.SSLContext', return_value=context), \
                patch('zmala_terminal.linux.samsung_tv.socket.create_connection'):
            with self.assertRaises(PermissionError):
                connect(self.config['host'])
        remote.send.assert_not_called()
        remote.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
