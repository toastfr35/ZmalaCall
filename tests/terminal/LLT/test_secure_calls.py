# @test T-LLT-077
# @requirements LLR-TERM-COM-010
# @environment portable
# @plan Validate complete, expired and malformed secure profiles with a fixed clock, including default 443 and separate 5061/5349 endpoints and invalid port bounds. Substitute only native ABI functions and local CA discovery; verify TLS TURN, ICE, forced relay, certificate/hostname checks and mandatory SRTP. Inject allocation failure and verify owned policy release. Deliver changed relay credentials through polling at an unchanged revision and require normal configuration application. Check outgoing call encryption in the existing Engine adapter tests.
# @pass Invalid profiles fail before native configuration; valid profiles request the stated secure policy and release references. Real handshakes and decoded media are verified by the network HLT.
import copy
import unittest
from unittest.mock import Mock, patch
from zmala_terminal.common import secure_calls


def config():
    return {'sip': {'proxy': 'sip:sip.example.org:443;transport=tls'}, 'secure_calls': {
        'mode':'tls-relay', 'turn_server':'turn.example.org:443', 'turn_realm':'example.org',
        'turn_username':'2000:a', 'turn_password':'password', 'expires':2000}}


class SecureCallTests(unittest.TestCase):
    def test_poll_dispatches_same_revision_relay_changes_to_idle_or_deferred_apply(self):
        from zmala_terminal.common.management import ManagementLoop
        from zmala_terminal.common.model import State
        from tests.terminal.LLT.test_terminal import config as full_config
        loop = ManagementLoop()
        previous = full_config() | config()
        loop.model = Mock(config=previous, state=State.HOME)
        loop.apply_config = Mock()
        loop.render = Mock()
        loop.apply_poll_config(copy.deepcopy(previous))
        loop.apply_config.assert_not_called()
        for state in (State.HOME, State.IN_CALL):
            loop.model.state = state
            updated = copy.deepcopy(previous)
            updated['secure_calls']['turn_password'] = 'renewed-fixture-password'
            loop.apply_poll_config(updated)
            loop.apply_config.assert_called_with(updated)
        # Removal also needs engine reconfiguration, rather than retaining TLS policy.
        updated = copy.deepcopy(previous)
        updated.pop('secure_calls')
        loop.apply_poll_config(updated)
        loop.apply_config.assert_called_with(updated)
        self.assertEqual(loop.apply_config.call_count, 3)

    def test_dial_keeps_srtp_and_credential_refresh_rebuilds_once_at_idle(self):
        from zmala_terminal.common.engine import Engine
        from zmala_terminal.common.configuration_control import ConfigurationControl
        from zmala_terminal.common.video_settings import VideoSettings
        e = Mock(config=config(), core=123)
        e.address_new.return_value = 10
        e.core_create_call_params.return_value = 20
        Engine.dial(e, 'sip:b@example.org')
        e.call_params_set_media_encryption.assert_called_once_with(20, 1)
        desired = config()
        app = ConfigurationControl()
        app.engine = Mock(config=copy.deepcopy(desired), audio_profile='normal',
                          video_settings=VideoSettings.for_config(desired))
        original = app.engine
        desired['secure_calls']['turn_password'] = 'new-password'
        replacement = Mock(config=copy.deepcopy(desired), audio_profile='normal',
                           video_settings=VideoSettings.for_config(desired))
        app.make_engine = Mock(return_value=replacement)
        app.configure_engine(desired, desired['sip'], 'normal')
        original.close.assert_called_once()
        app.make_engine.assert_called_once_with(desired)
        app.configure_engine(desired, desired['sip'], 'normal')
        app.make_engine.assert_called_once()

    def test_validation_rejects_expiry_downgrade_and_malformed_fields(self):
        value = config()
        self.assertEqual(secure_calls.validate(value, 1000), value['secure_calls'])
        self.assertIsNone(secure_calls.validate({}))
        shared = copy.deepcopy(value)
        shared['sip']['proxy'] = 'sip:calls.example.org:5061;transport=tls'
        shared['secure_calls']['turn_server'] = 'calls.example.org:5349'
        self.assertEqual(secure_calls.validate(shared, 1000), shared['secure_calls'])
        with self.assertRaises(ValueError):
            secure_calls.validate({'sip':value['sip']})
        for field, invalid in [('mode','udp'), ('turn_server','host:0'), ('turn_server','host:65536'), ('turn_username','a\nb'),
                               ('turn_password',''), ('expires',1000), ('expires',True)]:
            bad = copy.deepcopy(value)
            bad['secure_calls'][field] = invalid
            with self.subTest(field=field), self.assertRaises(ValueError):
                secure_calls.validate(bad, 1000)
        value['sip']['proxy'] = 'sip:sip.example.org:443;transport=udp'
        with self.assertRaises(ValueError):
            secure_calls.validate(value, 1000)

    @patch('zmala_terminal.common.secure_calls.time.time', return_value=1000)
    @patch('zmala_terminal.common.secure_calls.sys.platform', 'test')
    @patch.dict('os.environ', {'SSL_CERT_FILE':'/trusted/local.pem'})
    def test_native_policy_is_secure_and_resources_released(self, clock):
        e = Mock(config=config(), core=123)
        e.dll.linphone_core_create_nat_policy.return_value = 456
        e.auth_info_new.return_value = 789
        secure_calls.configure(e)
        e.dll.linphone_core_verify_server_certificates.assert_called_once_with(123,1)
        e.dll.linphone_core_verify_server_cn.assert_called_once_with(123,1)
        e.core_set_media_encryption_mandatory.assert_called_once_with(123,1)
        e.core_set_media_encryption.assert_called_once_with(123,1)
        e.dll.linphone_nat_policy_enable_udp_turn_transport.assert_called_once_with(456,0)
        e.dll.linphone_nat_policy_enable_tcp_turn_transport.assert_called_once_with(456,0)
        e.dll.linphone_nat_policy_enable_tls_turn_transport.assert_called_once_with(456,1)
        e.dll.linphone_core_enable_forced_ice_relay.assert_called_once_with(123,1)
        e.dll.linphone_core_set_nat_policy.assert_called_once_with(123,456)
        e.auth_info_unref.assert_called_once_with(789)
        e.dll.linphone_nat_policy_unref.assert_called_once_with(456)
        e.reset_mock()
        e.auth_info_new.return_value = None
        with self.assertRaises(RuntimeError):
            secure_calls.configure(e)
        e.dll.linphone_nat_policy_unref.assert_called_once_with(456)
