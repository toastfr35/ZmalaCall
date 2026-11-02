# @test T-LLT-077
# @requirements LLR-TERM-COM-010
# @environment portable
# @plan Validate complete, expired and malformed secure profiles with a fixed clock, including default 443 and separate 5061/5349 endpoints and invalid port bounds. Substitute only native ABI functions and local CA discovery; verify TLS TURN, ICE, forced relay, certificate/hostname checks and mandatory SRTP. Inject allocation failure and verify owned policy release. Deliver changed relay credentials through polling at an unchanged revision; exercise real idle configuration application with native ABI stubs. Assert no USB preparation, engine replacement, SIP refresh or device probes; defer active calls and retry failed allocation without losing the registered core. Inject policy-application failure and verify credential rollback/reference release. Replace changed TURN identities without removing unchanged/SIP credentials. Check outgoing call encryption in the existing Engine adapter tests.
# @pass Invalid profiles fail before native configuration; credentials expiring on a running core block both dial and answer before media opens. Valid profiles request the stated secure policy and release references. Real handshakes and decoded media are verified by the network HLT.
from zmala_terminal.common.callbacks import CallbackController
import copy
import unittest
from unittest.mock import Mock, patch
from zmala_terminal.common import secure_calls


def config():
    return {'sip': {'proxy': 'sip:sip.example.org:443;transport=tls'}, 'secure_calls': {
        'mode':'tls-relay', 'turn_server':'turn.example.org:443', 'turn_realm':'example.org',
        'turn_username':'2000:a', 'turn_password':'password', 'expires':2000}}


class SecureCallTests(unittest.TestCase):
    @patch('zmala_terminal.common.secure_calls.time.time', return_value=2000)
    def test_running_core_rechecks_expiry_before_dial_and_answer(self, clock):
        from zmala_terminal.common.engine import Engine
        e = Mock(config=config(), call=42)
        e.prepare_call_media.side_effect = lambda: Engine.prepare_call_media(e)
        for operation, args in ((Engine.dial, ('sip:b@example.org',)), (Engine.answer, ())):
            with self.subTest(operation=operation.__name__), self.assertRaisesRegex(ValueError, 'Expired'):
                operation(e, *args)
        e.refresh_usb_devices.assert_not_called()
        e.core_create_call_params.assert_not_called()
        e.core_invite_address_with_params.assert_not_called()
        e.call_accept_with_params.assert_not_called()
        e.config['secure_calls']['expires'] = 2001
        with patch('zmala_terminal.common.engine.WINDOWS', False):
            Engine.prepare_call_media(e)
        e.refresh_usb_devices.assert_called_once()

    def test_poll_dispatches_same_revision_relay_changes_to_idle_or_deferred_apply(self):
        from zmala_terminal.common.management import ManagementLoop
        from zmala_terminal.common.model import State
        from tests.terminal.LLT.test_terminal import config as full_config
        loop = ManagementLoop(); loop.callbacks = CallbackController()
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

    def test_dial_keeps_srtp_and_relay_endpoint_change_rebuilds_once_at_idle(self):
        from zmala_terminal.common.engine import Engine
        from zmala_terminal.common.configuration_control import ConfigurationControl
        from zmala_terminal.common.video_settings import VideoSettings
        e = Mock(config=config(), core=123)
        e.address_new.return_value = 10
        e.core_create_call_params.return_value = 20
        Engine.dial(e, 'sip:b@example.org')
        e.call_params_set_media_encryption.assert_called_once_with(20, 1)
        desired = config()
        app = ConfigurationControl(); app.callbacks = CallbackController()
        app.engine = Mock(config=copy.deepcopy(desired), audio_profile='normal',
                          video_settings=VideoSettings.for_config(desired))
        original = app.engine
        desired['secure_calls']['turn_server'] = 'new-relay.example.org:443'
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

    def idle_controller(self):
        from zmala_terminal.common.configuration_control import ConfigurationControl
        from zmala_terminal.common.model import TerminalModel
        from tests.terminal.LLT.test_terminal import config as full_config
        previous = full_config()
        previous['sip']['proxy'] = config()['sip']['proxy']
        previous['secure_calls'] = config()['secure_calls']
        app = ConfigurationControl(); app.callbacks = CallbackController(); app.model = TerminalModel(); app.model.configure(previous)
        app.engine = Mock(config=copy.deepcopy(previous), call=None, core=123, auto_framing=None)
        app.engine.dll.linphone_core_create_nat_policy.return_value = 456
        app.engine.dll.linphone_core_find_auth_info.return_value = 800
        app.engine.dll.linphone_auth_info_clone.return_value = 801
        app.engine.auth_info_new.return_value = 789
        app.setup_stage = None; app.engine_retry_at = 0; app.available_fonts = set()
        app.root = Mock(); app.text = lambda key:key; app.render = Mock(); app.notice = ''
        app.usb_media_ready = Mock(); app.make_engine = Mock(); app.configure_engine = Mock()
        app.missed_calls_store = Mock()
        app.missed_calls_store.account.return_value = ('family.test', 'terminal')
        return app

    @patch('zmala_terminal.common.secure_calls.time.time', return_value=1000)
    def test_idle_renewal_preserves_sleep_native_core_and_sip(self, clock):
        app = self.idle_controller(); original = app.engine
        updated = copy.deepcopy(app.model.config)
        updated['secure_calls'].update(turn_username='3000:a', turn_password='renewed', expires=3000)
        updated['contacts'][0]['online'] = False
        app.apply_config(updated)
        self.assertIs(app.engine, original); self.assertEqual(app.model.config, updated)
        self.assertEqual(original.config, updated); self.assertIsNone(app.pending_config)
        app.usb_media_ready.assert_not_called(); app.configure_engine.assert_not_called()
        app.make_engine.assert_not_called(); original.close.assert_not_called()
        original.core_refresh_registers.assert_not_called(); original.apply_settings.assert_not_called()
        original.dll.linphone_core_set_nat_policy.assert_called_once_with(123,456)
        original.dll.linphone_core_find_auth_info.assert_called_once_with(123,b'example.org',b'2000:a',None)
        original.dll.linphone_core_remove_auth_info.assert_called_once_with(123,800)
        self.assertEqual([c.args[0] for c in original.auth_info_unref.call_args_list], [801,789])
        original.dll.linphone_nat_policy_unref.assert_called_once_with(456)

    @patch('zmala_terminal.common.secure_calls.time.time', return_value=1000)
    def test_renewal_waits_for_call_and_preserves_core_on_allocation_failure(self, clock):
        from zmala_terminal.common.model import State
        app = self.idle_controller(); original = app.engine
        updated = copy.deepcopy(app.model.config); updated['secure_calls']['expires'] = 3000
        app.model.state = State.IN_CALL; app.engine.call = 42
        app.apply_config(updated)
        original.core_add_auth_info.assert_not_called(); self.assertEqual(app.pending_config, updated)
        app.model.state = State.HOME; app.engine.call = None
        original.auth_info_new.return_value = None
        with patch('time.monotonic', return_value=100), self.assertLogs(level='WARNING'):
            app.apply_config(updated)
        self.assertEqual(app.engine_retry_at,105); self.assertEqual(app.pending_config,updated)
        self.assertIs(app.engine,original); self.assertEqual(original.config['secure_calls']['expires'],2000)
        self.assertEqual(app.model.config['secure_calls']['expires'],2000)
        original.close.assert_not_called(); app.usb_media_ready.assert_not_called()
        original.dll.linphone_nat_policy_unref.assert_called_once_with(456)
        original.auth_info_new.return_value = 789
        with patch('time.monotonic', return_value=106): app.apply_config(updated)
        self.assertEqual(app.engine_retry_at,0); self.assertIsNone(app.pending_config)
        original.dll.linphone_core_remove_auth_info.assert_called_once_with(123,800)  # Same-identity replacement is explicit.
        app.usb_media_ready.assert_not_called()

    @patch('zmala_terminal.common.secure_calls.time.time', return_value=1000)
    def test_refresh_rejects_invalid_active_or_other_changes(self, clock):
        app = self.idle_controller(); old = app.engine.config
        for field,value in [('turn_server','elsewhere:443'),('turn_realm','elsewhere'),('mode','other')]:
            new=copy.deepcopy(old);new['secure_calls'][field]=value
            self.assertFalse(secure_calls.credentials_only(old,new))
        new=copy.deepcopy(old);new['secure_calls']['expires']=3000
        for field,value in [('configuration_version',2),('video_fps',30),('action_sound_volume',10)]:
            changed=copy.deepcopy(new);changed[field]=value
            self.assertFalse(secure_calls.credentials_only(old,changed))
        app.engine.call=42
        with self.assertRaises(ValueError):secure_calls.refresh_credentials(app.engine,new)
        app.engine.call=None;new['secure_calls']['expires']=999
        with self.assertRaises(ValueError):secure_calls.refresh_credentials(app.engine,new)
        app.engine.core_add_auth_info.assert_not_called()
        self.assertIs(app.engine.config,old)

    @patch('zmala_terminal.common.secure_calls.time.time', return_value=1000)
    def test_failed_policy_application_restores_previous_auth_without_wake(self, clock):
        app = self.idle_controller(); original = app.engine
        desired = copy.deepcopy(original.config); desired['secure_calls']['turn_username'] = '3000:a'
        original.dll.linphone_core_set_nat_policy.side_effect = RuntimeError('fixture failure')
        with self.assertLogs(level='WARNING'): app.apply_config(desired)
        self.assertEqual([c.args for c in original.core_add_auth_info.call_args_list], [(123,789),(123,801)])
        self.assertEqual([c.args for c in original.dll.linphone_core_remove_auth_info.call_args_list], [(123,800),(123,789)])
        self.assertEqual([c.args[0] for c in original.auth_info_unref.call_args_list], [801,789])
        original.dll.linphone_nat_policy_unref.assert_called_once_with(456)
        self.assertEqual(original.config['secure_calls']['turn_username'],'2000:a')
        self.assertIs(app.engine,original); self.assertEqual(app.pending_config,desired)
        original.close.assert_not_called(); app.usb_media_ready.assert_not_called()
