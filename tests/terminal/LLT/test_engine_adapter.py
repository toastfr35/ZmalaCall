# @test T-LLT-057
# @requirements LLR-TERM-START-005, LLR-TERM-START-006, LLR-TERM-CALL-011, LLR-TERM-AUDIO-004, LLR-TERM-AUDIO-005, LLR-TERM-VIDEO-004, LLR-TERM-VIDEO-006, LLR-TERM-VIDEO-012, LLR-TERM-MAINT-018
# @environment portable
# @plan Substitute only Liblinphone ABI calls, OS media hooks and storage roots; run the real Engine constructor, registration, callback dispatch, dialing/answering and shutdown. Inspect bound retain/release signatures to prevent truncation of native call handles. Verify resource ownership, native configuration/transport requests, signed caller proof, absent microphone fallback, device enumeration and diagnostic units. Inject native startup, address, invite and accept failures and verify errors/cleanup without loading the SDK or contacting SIP. Exercise the real Linux plugin adapter with fake ABI libraries: registration order, rate/registration failure, framing configuration, native resource lookup and deferred USB/mixer refresh.
# @pass Recorded native arguments and reference releases match the requested policy; rejected/forged calls cannot notify the UI. These adapter checks do not establish real codec quality, network interoperability or hardware timing.
import ctypes as C
import hashlib
import hmac
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, call, patch

from zmala_terminal.common import engine
from zmala_terminal.common.linphone_api import SIGNATURES, S, ListNode, VideoSize
from tests.terminal.LLT.test_terminal import config


def bind_native(e):
    e.dll = Mock()
    for name, (result, _) in SIGNATURES.items():
        setattr(e, name, Mock(return_value=b'' if result is S else 0))
    for name, result in {'factory_get':1, 'factory_create_core_3':2, 'factory_create_core_cbs':3,
                         'address_new':5, 'core_create_call_params':6, 'auth_info_new':7,
                         'core_create_proxy_config':8, 'transports_new':9, 'factory_create_call_cbs':10}.items():
        getattr(e, name).return_value = result
    e.core_set_preferred_video_size.side_effect = lambda core, size: setattr(e, 'requested_size', size)
    e.core_get_preferred_video_size.side_effect = lambda core: e.requested_size
    e.call_ref.side_effect = lambda pointer: pointer


class LinuxMediaAdapterTests(unittest.TestCase):
    def test_call_handle_bindings_use_pointer_width_and_fail_on_missing_symbol(self):
        from zmala_terminal.common import linphone_api
        api = linphone_api.LinphoneAPI()
        library = Mock()
        with patch.object(linphone_api, 'load_linphone', return_value=library) as load:
            api.load_api()
        load.assert_called_once_with(api)
        self.assertIs(api.call_ref, library.linphone_call_ref)
        self.assertIs(api.call_ref.restype, C.c_void_p)
        self.assertEqual(api.call_ref.argtypes, [C.c_void_p])
        self.assertIsNone(api.call_unref.restype)
        self.assertEqual(api.call_unref.argtypes, [C.c_void_p])
        self.assertEqual(api.core_unref.argtypes, [C.c_void_p])
        missing = Mock()
        del missing.linphone_call_ref
        with patch.object(linphone_api, 'load_linphone', return_value=missing):
            with self.assertRaises(AttributeError):
                linphone_api.LinphoneAPI().load_api()

    def test_native_library_and_resource_selection_honors_prefix_and_missing_defaults(self):
        from zmala_terminal.linux import native_runtime as runtime
        with tempfile.TemporaryDirectory() as directory, patch.object(runtime, 'SDK', Path(directory)), \
                patch.object(runtime.C, 'CDLL', side_effect=lambda path: path), \
                patch.object(runtime.ctypes.util, 'find_library', return_value='liblinphone.so.system') as find:
            self.assertEqual(runtime.load_linphone(None), 'liblinphone.so.system')
            for folder in ('lib64', 'lib'):
                path = Path(directory)/folder/'liblinphone.so'
                path.parent.mkdir(parents=True); path.touch()
                self.assertEqual(runtime.library('linphone'), str(path))
            self.assertEqual(find.call_count, 1)
            self.assertIsNone(runtime.resource('ring_resources'))
            rings = Path(directory)/'share/sounds/linphone/rings'; rings.mkdir(parents=True)
            self.assertEqual(runtime.resource('ring_resources'), rings)
            self.assertEqual(runtime.process_options(), {'start_new_session':True})
        with patch.object(runtime, 'SDK', Path('/usr')), patch.object(runtime.ctypes.util, 'find_library', return_value=None):
            with self.assertRaisesRegex(RuntimeError, 'Missing native library'):
                runtime.library('missing')
            with patch.object(runtime.Path, 'glob', return_value=[Path('/usr/lib/arch/mediastreamer/plugins')]), \
                    patch.object(runtime.Path, 'is_dir', return_value=True):
                self.assertEqual(runtime.resource('msplugins'), Path('/usr/lib/arch/mediastreamer/plugins'))

    def test_plugin_registration_order_rate_errors_and_framing_configuration(self):
        from zmala_terminal.linux import media
        e = SimpleNamespace(core=1, dll=Mock(), video_settings=SimpleNamespace(fps=20), config={'auto_framing':True})
        with tempfile.TemporaryDirectory() as directory, patch.object(media, 'ROOT', Path(directory)), \
                patch.object(media.C, 'CDLL') as load, patch('zmala_terminal.linux.auto_framing.AutoFraming') as framing:
            with self.assertRaisesRegex(RuntimeError, 'plugin is missing'):
                media.configure(e)
            load.assert_not_called()
            path = Path(directory)/'linux/media/video/libzmala_video.so'
            path.parent.mkdir(parents=True); path.touch()
            plugin = load.return_value
            plugin.zmala_video_set_framerate.return_value = 1
            with self.assertRaisesRegex(RuntimeError, 'frame rate'):
                media.configure(e)
            plugin.zmala_video_set_framerate.return_value = 0
            names = ('zmala_video_register', 'zmala_mjpeg_register', 'zmala_preview_register', 'zmala_framing_register')
            for name in names:
                getattr(plugin, name).return_value = 0
            e.dll.linphone_core_get_ms_factory.return_value = 42
            for name in names:
                getattr(plugin, name).return_value = -1
                with self.assertRaisesRegex(RuntimeError, name):
                    media.configure(e)
                getattr(plugin, name).return_value = 0
            plugin.reset_mock()
            media.configure(e)
            self.assertEqual([c[0] for c in plugin.mock_calls], ['zmala_video_set_framerate', *names])
            self.assertTrue(all(getattr(plugin, name).call_args.args == (42,) for name in names))
            e.dll.linphone_core_reload_video_devices.assert_called_once_with(1)
            framing.return_value.configure.assert_called_once_with(True)
            self.assertIs(e.auto_framing, framing.return_value)

    def test_usb_refresh_preserves_live_streams_then_reloads_devices_and_volume(self):
        from zmala_terminal.linux import media
        e = Mock(core=1, call=2, config={'terminal_settings': {'speaker': 'chosen'}, 'c20_speaker_volume': 37})
        with patch('zmala_terminal.linux.c20_volume.reapply') as reapply:
            for state in (7, 8):
                e.call_get_state.return_value = state
                self.assertFalse(media.refresh_usb_devices(e))
            e.dll.linphone_core_reload_sound_devices.assert_not_called()
            e.call = None
            media.refresh_usb_devices(e)
            e.dll.linphone_core_reload_sound_devices.assert_called_once_with(1)
            e.dll.linphone_core_reload_video_devices.assert_called_once_with(1)
            e.apply_settings.assert_called_once_with({'speaker': 'chosen'})
            reapply.assert_called_once_with()
        with patch('zmala_terminal.linux.c20_volume.configure') as configure:
            media.apply_speaker_volume(e)
            configure.assert_called_once_with(37)
            e.sync_speaker_mute.assert_called_once()
        e.devices.return_value = {'camera':['ZmalaMJPEG:C20'], 'speaker':['Nuroum C20 speaker'], 'microphone':['Nuroum C20 microphone']}
        self.assertEqual(media.select_settings(e, {}), {key: values[0] for key, values in e.devices.return_value.items()})
        e.call_params_get_received_framerate.return_value = 12
        self.assertTrue(media.received_frame(e, 5))
        e.call_params_get_received_framerate.return_value = 0
        self.assertFalse(media.received_frame(e, 5))
        self.assertIsNone(media.poll_video(e, 10))


class EngineAdapterTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.media = Mock(CODECS={'H264'}, DISPLAY_FILTER=b'ZmalaDisplay')
        self.media.select_settings.side_effect = lambda e, settings: settings
        self.media.filter_devices.side_effect = lambda devices: devices
        patches = [patch.object(engine, 'ROOT', Path(temporary.name)),
                   patch.object(engine, 'resource', return_value=Path(temporary.name)),
                   patch.object(engine, 'library', return_value=Mock()),
                   patch.object(engine, 'media_backend', return_value=self.media),
                   patch('zmala_terminal.common.audio_processing.configure'),
                   patch.object(engine.Engine, 'load_api', autospec=True, side_effect=bind_native)]
        for item in patches: item.start(); self.addCleanup(item.stop)

    def build(self, **overrides):
        return engine.Engine(config() | overrides, Mock(), Mock(), 101, on_message=Mock(), preview_window=102)

    def test_constructor_registers_account_and_keeps_callbacks_and_windows_alive(self):
        e = self.build()
        self.addCleanup(e.close)
        e.core_set_transports.assert_called_once_with(2, 9)
        e.transports_set_udp_port.assert_called_once_with(9, -1)
        for name in ('tcp', 'tls', 'dtls'):
            getattr(e, 'transports_set_' + name + '_port').assert_called_once_with(9, 0)
        e.transports_unref.assert_called_once_with(9)
        e.auth_info_new.assert_called_once_with(b'terminal', None, b'secret', None, b'family.test', b'family.test')
        e.auth_info_unref.assert_called_once_with(7); e.address_unref.assert_called_once_with(5)
        e.proxy_config_unref.assert_called_once_with(8)
        e.proxy_config_set_server_addr.assert_called_once_with(8, b'sip:family.test')
        e.proxy_config_set_expires.assert_called_once_with(8, 300)
        e.core_set_network_reachable.assert_called_once_with(2, 1)
        self.assertEqual(e.ogl.window, 101); self.assertEqual(e.preview_ogl.window, 102)
        e.core_set_native_video_window_id.assert_called_once_with(2, C.addressof(e.ogl))
        e.core_use_preview_window.assert_called_once_with(2, 1)
        e.core_enable_self_view.assert_called_once_with(2, 0)
        self.assertEqual(e.dll.linphone_core_set_preferred_framerate.call_args.args, (2, 15.0))
        self.assertTrue(e.core_set_ringback.call_args.args[1].endswith(b'ringback.wav'))
        e.core_cbs_set_call_state_changed.assert_called_once_with(3, e.call_callback)
        e.core_cbs_set_registration_state_changed.assert_called_once_with(3, e.reg_callback)
        e.core_cbs_set_message_received.assert_called_once_with(3, e.message_callback)
        e.reg_callback(2, 8, 2, b'OK'); self.assertTrue(e.registered)
        e.reg_callback(2, 8, 4, None); self.assertFalse(e.registered)
        e.on_registration.assert_has_calls([call(True), call(False)])

    def test_startup_failure_releases_allocated_core_and_no_sip_is_supported(self):
        for fail in ('factory_create_core_3', 'core_start'):
            captured = []
            def bind(e):
                bind_native(e); captured.append(e)
                getattr(e, fail).return_value = 0 if fail == 'factory_create_core_3' else -1
            with self.subTest(fail=fail), patch.object(engine.Engine, 'load_api', new=bind):
                with self.assertRaisesRegex(RuntimeError, 'could not'): self.build()
                e = captured[0]; self.assertFalse(e.core)
                if fail == 'core_start': e.core_unref.assert_called_once_with(2)
        e = self.build(sip=None); self.addCleanup(e.close)
        e.auth_info_new.assert_not_called(); e.core_set_network_reachable.assert_called_once()

    def test_codec_allowlist_and_per_call_devices_and_ringer(self):
        e = self.build(); self.addCleanup(e.close)
        nodes = (ListNode * 3)()
        for index, node in enumerate(nodes):
            node.data = index+20
            if index < 2: node.next = C.pointer(nodes[index+1])
        e.core_get_video_payload_types.return_value = C.pointer(nodes[0])
        e.payload_type_get_mime_type.side_effect = [b'h264', b'VP8', None]
        e.configure_media(101, 102)
        e.payload_type_enable.assert_has_calls([call(20,1), call(21,0), call(22,0)])
        self.assertEqual(e.payload_type_unref.call_count, 3)
        e.core_get_video_devices.return_value = [b'StaticImage: Static picture', b'C20', None]
        e.core_get_playback_device.return_value = b'actual-speaker'
        e.core_set_capture_device.return_value = -1; e.core_set_ringer_device.return_value = -1
        with self.assertLogs(level='WARNING'):
            e.apply_settings({'microphone':'missing-mic'})
        e.core_set_video_device.assert_called_with(2, b'C20')
        e.core_set_capture_device.assert_called_with(2, b'missing-mic')
        e.core_set_ringer_device.assert_called_with(2, b'actual-speaker')

    def test_signed_call_proof_and_callback_exceptions_are_contained(self):
        e = self.build(); self.addCleanup(e.close)
        e.call_get_remote_address.return_value = 4
        e.address_get_username.return_value = b'alice'; e.address_get_domain.return_value = b'family.test'
        e.call_get_call_log.return_value = 10; e.call_log_get_call_id.return_value = b'call-id'
        e.call_get_remote_params.return_value = 11
        e.call_params_get_custom_header.return_value = b'forged'
        with self.assertLogs(level='WARNING'): e._call_event(2, 42, 1, None)
        e.call_decline.assert_called_once_with(42, 2); e.on_call.assert_not_called()
        e.call_params_get_custom_header.return_value = hmac.new(e.config['call_auth_key'].encode(), b'call-id:alice', hashlib.sha256).hexdigest().encode()
        e._call_event(2, 42, 1, b'Incoming')
        e.on_call.assert_called_once_with(42, 1, 'alice', 'family.test')
        e.on_call.side_effect = RuntimeError('UI failure')
        with self.assertLogs(level='ERROR'): e._call_event(2, 42, 2, None)
        e.call_get_remote_address.side_effect = ValueError('native failure')
        with self.assertLogs(level='ERROR'): e._call_event(2, 42, 1, None)

    def test_dial_answer_end_and_failures_own_and_release_native_objects(self):
        e = self.build(); self.addCleanup(e.close)
        e.address_unref.reset_mock(); e.core_invite_address_with_params.return_value = 42
        with self.assertLogs(level='WARNING'): e.dial('sip:alice@family.test')
        self.assertEqual(e.call, 42)
        e.call_params_enable_mic.assert_called_with(6, 0)
        e.call_params_set_audio_direction.assert_called_with(6, 2)
        e.call_params_unref.assert_called_once_with(6); e.address_unref.assert_called_once_with(5)
        e.core_get_extended_audio_devices.return_value = 0
        with self.assertLogs(level='WARNING'): e.answer()
        e.call_accept_with_params.assert_called_once_with(42, 6)
        e.end(); e.end(True)
        e.call_terminate.assert_called_once_with(42); e.call_decline.assert_called_once_with(42, 3)
        e.call_accept_with_params.return_value = 1
        with self.assertLogs(level='WARNING'), self.assertRaisesRegex(RuntimeError, 'answered'): e.answer()
        e.core_invite_address_with_params.return_value = 0
        with self.assertLogs(level='WARNING'), self.assertRaisesRegex(RuntimeError, 'started'): e.dial('sip:x@y')
        e.address_new.return_value = 0
        with self.assertRaisesRegex(ValueError, 'Invalid SIP'): e.dial('bad')
        e.hold_call(None); e.call_accept_with_params.reset_mock(); e.answer()
        e.call_accept_with_params.assert_not_called()

    def test_audio_device_capabilities_deduplicate_and_stats_report_negotiated_size(self):
        e = self.build(); self.addCleanup(e.close)
        nodes = (ListNode * 3)()
        for index, node in enumerate(nodes):
            node.data = index+20
            if index < 2: node.next = C.pointer(nodes[index+1])
        e.core_get_extended_audio_devices.return_value = C.pointer(nodes[0])
        e.audio_device_get_id.side_effect = [b'C20', b'C20', b'output\xff']
        e.audio_device_get_capabilities.side_effect = [3,1,2]
        self.assertEqual(e.devices(), {'camera':[], 'microphone':['C20'], 'speaker':['C20','output\ufffd']})
        self.assertEqual(e.audio_device_unref.call_count, 3)
        e.core_get_extended_audio_devices.return_value = 0
        e.applied_audio_profile = 'speech'; e.audio_profile = 'speech'; e.auto_framing = Mock(status='tracking')
        self.assertEqual(e.diagnostics()['auto_framing_status'], 'tracking')
        self.assertEqual(e.media_stats(), {})
        e.call = 42; e._video_callbacks = 10
        e.call_get_video_stats.return_value = 20; e.call_get_current_params.return_value = 6
        e.call_params_get_sent_framerate.return_value = 19.5
        e.call_params_get_received_framerate.return_value = 20
        e.call_params_get_sent_video_size.return_value = VideoSize(1920,1080)
        e.call_params_get_received_video_size.return_value = VideoSize(0,0)
        report = e.media_stats()['video']
        self.assertEqual(report['sent_resolution'], [1920,1080]); self.assertEqual(report['sent_fps'],19.5)
        self.assertNotIn('received_resolution', report); e.call_stats_unref.assert_called_once_with(20)
        with patch.object(engine.time, 'monotonic', return_value=55): e.iterate()
        e.core_iterate.assert_called_once_with(2); self.media.poll_video.assert_called_once_with(e,55)
        self.media.sync_speaker_mute.assert_called_once_with(e)
        e.refresh_usb_devices(); self.media.refresh_usb_devices.assert_called_once_with(e)
