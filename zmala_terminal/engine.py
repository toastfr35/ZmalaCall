"""Small, typed ctypes adapter to the official Liblinphone C API.

All methods and callbacks run on the UI thread via iterate(). Native pointers
never cross the configuration worker thread.
"""
import ctypes as C
import logging
import hashlib
import hmac
import time
import math
from platforms.native_runtime import WINDOWS, library, resource

# Re-export native types used by SDK integration fixtures.
from linphone_api import (LinphoneAPI, P, S, I as I, ROOT, SDK, encoded,
                          CALL_CB, REG_CB, MESSAGE_CB, VIDEO_EVENT_CB as VIDEO_EVENT_CB,
                          VIDEO_FRAME_CB, OglContext, ListNode as ListNode, VideoSize)


class Engine(LinphoneAPI):
    def __init__(self, config, on_call, on_registration, video_window=0, profile='terminal', on_message=None, preview_window=0):
        self.config, self.on_call, self.on_registration = config, on_call, on_registration
        self.on_message = on_message
        self._seen_messages = set()
        self.registered = False
        self.call = None
        self._video_callbacks = None
        self._last_video_frame = None
        self._next_video_probe = 0
        self.core = None
        self.load_api()
        try:
            self.create_core(profile)
            self.configure_media(video_window, preview_window)
            self.configure_transports()
            self.install_callbacks()
            self.start_core(config)
        except Exception:
            self.close()
            raise

    def start_core(self, config):
        if self.core_start(self.core) != 0:
            raise RuntimeError('Liblinphone could not start')
        if config.get('sip'):
            self.register_account(config['sip'])
        self.core_set_network_reachable(self.core, 1)
        self.apply_settings(config.get('terminal_settings', {}))
        self.apply_speaker_volume()
        self.apply_call_timeout()


    def create_core(self, profile):
        self.factory = self.factory_get()
        data = ROOT / 'data' / profile
        data.mkdir(parents=True, exist_ok=True)
        from video_settings import VideoSettings
        self.video_settings = VideoSettings.for_config(self.config)
        for kind in ['config', 'data', 'download', 'cache']:
            function = getattr(self.dll, 'linphone_factory_set_' + kind + '_dir')
            function.argtypes, function.restype = [P, S], None
            function(self.factory, encoded(data))
        for kind in ('msplugins', 'sound_resources', 'ring_resources', 'image_resources'):
            directory = resource(kind)
            if directory:
                function = getattr(self.dll, 'linphone_factory_set_' + kind + '_dir')
                function.argtypes, function.restype = [P, S], None
                function(self.factory, encoded(directory))
        self.core = self.factory_create_core_3(self.factory, None, None, None)
        if not self.core:
            raise RuntimeError('Liblinphone could not create the call engine')

    def configure_media(self, video_window, preview_window=0):
        cfg = self.core_get_config(self.core)
        for section, key, value in [('sip', 'sip_port', -1), ('sip', 'sip_tcp_port', 0),
                                    ('sip', 'sip_tls_port', 0), ('net', 'nat_policy_ref', 0),
                                    ('video', 'automatically_initiate', 1), ('video', 'automatically_accept', 1),
                                    ('misc', 'max_calls', 1), ('sip', 'register_only_when_network_is_up', 0),
                                    ('sip', 'avpf', 1), ('rtp', 'rtcp_mux', 0)]:
            self.config_set_int(cfg, encoded(section), encoded(key), value)
        self.core_set_user_agent(self.core, b'ZmalaCallTerminal', b'0.1')
        self.core_enable_video_capture(self.core, 1)
        self.core_enable_video_display(self.core, 1)
        self.core_enable_video_preview(self.core, 0)
        # MSOGL ignores the legacy composited self-view input. The outgoing
        # stream is instead rendered into a dedicated child window below.
        self.core_enable_self_view(self.core, 0)
        self.core_enable_echo_cancellation(self.core, 1)
        from audio_processing import configure
        configure(self)
        self.core_set_media_encryption(self.core, 0)
        self.core_set_media_encryption_mandatory(self.core, 0)
        self.configure_video_target()
        self.core_set_upload_bandwidth(self.core, self.video_settings.upload_kbps)
        self.core_set_download_bandwidth(self.core, self.video_settings.download_kbps)
        codecs = self.core_get_video_payload_types(self.core)
        node = codecs
        allowed_codecs = {'VP8', 'H264'} if WINDOWS else {'H264'}
        if WINDOWS:
            from platforms.windows_media import configure
        else:
            from platforms.linux_media import configure
        configure(self)
        while node:
            mime = (self.payload_type_get_mime_type(node.contents.data) or b'').decode().upper()
            self.payload_type_enable(node.contents.data, int(mime in allowed_codecs))
            self.payload_type_unref(node.contents.data)
            node = node.contents.next
        self.bctbx = library('bctoolbox')
        self.bctbx.bctbx_list_free.argtypes, self.bctbx.bctbx_list_free.restype = [P], None
        self.bctbx.bctbx_list_free(codecs)
        self.configure_video_windows(video_window, preview_window)
        logging.info('Video codecs %s; renderer MSOGL', ','.join(sorted(allowed_codecs)))
        fps = self.dll.linphone_core_set_preferred_framerate
        fps.argtypes, fps.restype = [P, C.c_float], None
        fps(self.core, float(self.video_settings.fps))
        logging.info('Video target %s, fps=%s, upload=%s kbps', self.video_settings.resolution,
                     self.video_settings.fps or 'SDK default', self.video_settings.upload_kbps)

        # Bundle the same synthesized melody on both platforms; the historical
        # asset name is retained for compatibility with installed terminals.
        self.core_set_ring(self.core, encoded(ROOT / 'assets/gentle-chime.wav'))
        self.core_set_ringback(self.core, encoded(SDK / 'share/sounds/linphone/ringback.wav'))

    def configure_video_target(self):
        """Reject silently ignored SDK sizes; repair lost video packets on LAN calls."""
        dimensions = self.video_settings.dimensions
        self.core_set_preferred_video_size(self.core, VideoSize(*dimensions))
        actual = self.core_get_preferred_video_size(self.core)
        if (actual.width, actual.height) != dimensions:
            raise RuntimeError(f'SDK rejected video size {dimensions[0]}x{dimensions[1]}')
        # AVPF is already negotiated. The SDK otherwise disables NACK repair,
        # leaving lost H.264 reference packets corrupt until a later keyframe.
        self.core_enable_retransmission_on_nack(self.core, 1)

    def configure_video_windows(self, video_window, preview_window):
        """Keep both native contexts alive until the core releases its filters."""
        self.ogl = OglContext(video_window, 960, 540, None)
        # MSOGL uses the same native-window structure on Windows and Linux,
        # choosing EGL/GLES on the Pi rather than a desktop GLX context.
        display_filter = b'MSOGL' if WINDOWS else b'ZmalaPreviewOGL'
        self.core_set_video_display_filter(self.core, display_filter)
        window = C.addressof(self.ogl) if video_window else None
        self.core_set_native_video_window_id(self.core, window)
        self.preview_ogl = OglContext(preview_window, 240, 135, None)
        self.core_set_native_preview_window_id(self.core, C.addressof(self.preview_ogl) if preview_window else None)
        self.core_use_preview_window(self.core, int(bool(preview_window)))

    def configure_transports(self):
        transports = self.transports_new()
        self.transports_set_udp_port(transports, -1)
        self.transports_set_tcp_port(transports, 0)
        self.transports_set_tls_port(transports, 0)
        self.transports_set_dtls_port(transports, 0)
        self.core_set_transports(self.core, transports)
        self.transports_unref(transports)

    def install_callbacks(self):
        # ctypes callbacks must stay strongly referenced for the lifetime of the core.
        self.call_callback = CALL_CB(self._call_event)
        self.video_frame_callback = VIDEO_FRAME_CB(self._video_frame_decoded)
        self.reg_callback = REG_CB(self._registration_event)
        self.message_callback = MESSAGE_CB(self._message_event)
        cbs = self.factory_create_core_cbs(self.factory)
        self.callbacks = cbs
        self.core_cbs_set_call_state_changed(cbs, self.call_callback)
        self.core_cbs_set_registration_state_changed(cbs, self.reg_callback)
        self.core_cbs_set_message_received(cbs, self.message_callback)
        self.core_add_callbacks(self.core, cbs)
        self.core_cbs_unref(cbs)

    def register_account(self, account):
        auth = self.auth_info_new(encoded(account['username']), None, encoded(account['password']), None,
                                  encoded(account['domain']), encoded(account['domain']))
        self.core_add_auth_info(self.core, auth)
        self.auth_info_unref(auth)
        address = self.address_new(encoded(f"sip:{account['username']}@{account['domain']}"))
        proxy = self.core_create_proxy_config(self.core)
        self.proxy_config_set_identity_address(proxy, address)
        self.address_unref(address)
        self.proxy_config_set_server_addr(proxy, encoded(account['proxy']))
        self.proxy_config_set_route(proxy, encoded(account['proxy']))
        self.proxy_config_set_expires(proxy, 300)
        self.proxy_config_enable_register(proxy, 1)
        self.core_add_proxy_config(self.core, proxy)
        self.core_set_default_proxy_config(self.core, proxy)
        self.proxy_config_unref(proxy)

    def _registration_event(self, core, proxy, state, message):
        self.registered = state == 2
        logging.info('Registration %s: %s', state, message.decode(errors='replace') if message else '')
        self.on_registration(self.registered)

    def _call_event(self, core, call, state, message):
        try:
            address = self.call_get_remote_address(call)
            user = (self.address_get_username(address) or b'').decode()
            domain = (self.address_get_domain(address) or b'').decode()
            log = self.call_get_call_log(call)
            call_id = (self.call_log_get_call_id(log) or b'').decode() if log else ''
            if state == 1 and self.config.get('account_type', 'terminal') == 'terminal':
                params = self.call_get_remote_params(call)
                proof = (self.call_params_get_custom_header(params, b'X-Family-Auth') or b'').decode() if params else ''
                expected = hmac.new(encoded(self.config['call_auth_key']), encoded(f'{call_id}:{user}'), hashlib.sha256).hexdigest()
                if not hmac.compare_digest(proof, expected):
                    logging.warning('Rejected a call without proof from the family server')
                    self.call_decline(call, 2)
                    return
            logging.info('Call %s state %s: %s', call_id, state, message.decode(errors='replace') if message else '')
            self.on_call(call, state, user, domain)
        except Exception:
            logging.exception('Call callback failed')

    def _message_event(self, core, room, message):
        if not self.on_message or self.config.get('account_type', 'terminal') != 'terminal':
            return
        try:
            if not self.chat_message_is_text(message) or not (self.chat_message_get_utf8_text(message) or b'').strip():
                return
            address = self.chat_message_get_from_address(message)
            user = (self.address_get_username(address) or b'').decode()
            domain = (self.address_get_domain(address) or b'').decode()
            identifier = (self.chat_message_get_custom_header(message, b'X-Zmala-Message-Id') or b'').decode()
            proof = (self.chat_message_get_custom_header(message, b'X-Family-Auth') or b'').decode()
            if domain.lower() != self.config['sip']['domain'].lower() or not identifier or len(identifier) > 256:
                return
            if not any(c['id'] == user and c['can_receive'] for c in self.config.get('contacts', [])):
                return
            expected = hmac.new(encoded(self.config['call_auth_key']), encoded(f'message:{identifier}:{user}'), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(proof, expected) or identifier in self._seen_messages:
                return
            if len(self._seen_messages) >= 256:
                self._seen_messages.pop()
            self._seen_messages.add(identifier)
            self.on_message(user, domain)
        except Exception:
            logging.exception('Text notification callback failed')

    def hold_call(self, call):
        # Borrowed callback pointers need an owned reference until the UI releases the call.
        if self.call != call:
            if self.call:
                self.call_remove_callbacks(self.call, self._video_callbacks)
                self.call_cbs_unref(self._video_callbacks)
                self.call_unref(self.call)
            self.call = self.call_ref(call) if call else None
            self._video_callbacks = None
            self._last_video_frame = None
            self._next_video_probe = 0
            if self.call:
                self._video_callbacks = self.factory_create_call_cbs(self.factory)
                self.call_cbs_set_next_video_frame_decoded(self._video_callbacks, self.video_frame_callback)
                self.call_add_callbacks(self.call, self._video_callbacks)

    def _video_frame_decoded(self, call):
        if call == self.call:
            self._last_video_frame = time.monotonic()

    def incoming_video_active(self):
        """Show video only after a decoded frame, with tolerance for brief gaps."""
        if not self.call:
            return False
        params = self.call_get_current_params(self.call)
        # Directions are from our perspective: receive-only=2, send/receive=3.
        if not params or not self.call_params_video_enabled(params) or self.call_params_get_video_direction(params) not in (2, 3):
            self._last_video_frame = None
            return False
        if not WINDOWS and self.call_params_get_received_framerate(params) > 0:
            # Debian's OpenH264 plugin reports frame rate but cannot re-arm
            # next-frame callbacks. RTP/RTCP traffic alone is not proof of video.
            self._last_video_frame = time.monotonic()
        return self._last_video_frame is not None and time.monotonic() - self._last_video_frame < 4

    def dial(self, uri):
        address = self.address_new(encoded(uri))
        if not address:
            raise ValueError('Invalid SIP address')
        params = self.core_create_call_params(self.core, None)
        self.configure_call_audio(params)
        self.call_params_enable_video(params, 1)
        self.call_params_set_media_encryption(params, 0)
        call = self.core_invite_address_with_params(self.core, address, params)
        self.call_params_unref(params)
        self.address_unref(address)
        if not call:
            raise RuntimeError('The call could not be started')
        self.hold_call(call)

    def answer(self):
        if not self.call:
            return
        params = self.core_create_call_params(self.core, self.call)
        self.configure_call_audio(params)
        self.call_params_enable_video(params, 1)
        result = self.call_accept_with_params(self.call, params)
        self.call_params_unref(params)
        if result:
            raise RuntimeError('The call could not be answered')

    def configure_call_audio(self, params):
        """Without capture hardware, receive speech instead of opening a dummy input.

        Check at each new call so a reconnected USB microphone is usable without
        restarting. Keep the SDK's negotiated direction when capture is available.
        """
        if not self.devices()['microphone']:
            self.call_params_enable_mic(params, 0)
            self.call_params_set_audio_direction(params, 2)  # LinphoneMediaDirectionRecvOnly
            logging.warning('No microphone detected: call audio is receive-only')

    def end(self, decline=False):
        if self.call:
            if decline:
                self.call_decline(self.call, 3)
            else:
                self.call_terminate(self.call)

    def apply_settings(self, settings):
        if not WINDOWS:
            from platforms.linux_media import settings as c20_settings
            settings = c20_settings(self.devices())
        for key, setter in [('camera', self.core_set_video_device), ('microphone', self.core_set_capture_device),
                            ('speaker', self.core_set_playback_device)]:
            device = settings.get(key) or None
            if key == 'camera' and device is None:
                device = next((name for name in self.devices()['camera'] if not name.startswith('StaticImage:')), None)
            if device is not None or key != 'camera':
                if setter(self.core, encoded(device)):
                    logging.warning('Requested %s device is unavailable: %s', key, device)
        # Liblinphone routes ringtone playback separately from call audio.
        # Use the effective speaker (including system-default resolution).
        speaker = self.core_get_playback_device(self.core)
        if self.core_set_ringer_device(self.core, speaker):
            logging.warning('Requested ringtone device is unavailable: %s', speaker)

    def apply_call_timeout(self):
        delay = self.config.get('auto_answer_seconds', 10) if self.config.get('auto_answer') else 0
        self.core_set_inc_timeout(self.core, max(60, delay+30))

    def apply_speaker_volume(self):
        """C20 hardware volume affects both calls and ringing, independently of HDMI."""
        if not WINDOWS:
            from platforms.c20_volume import configure
            configure(self.config.get('c20_speaker_volume', 50))
            # C20's hardware 0% is -28 dB, not silence. Mute call playback too.
            self.sync_speaker_mute()
        else:
            percent = self.config.get('c20_speaker_volume', 50)
            self.core_set_playback_gain_db(self.core, 20*math.log10(percent/100) if percent else -120)

    def sync_speaker_mute(self):
        """Follow local remote gestures as well as server volume changes."""
        if WINDOWS:
            return
        from platforms.c20_volume import status
        desired, _, _ = status()
        muted = desired == 0
        if getattr(self, '_speaker_muted', None) != muted:
            self.core_set_playback_gain_db(self.core, -120 if muted else 0)
            self._speaker_muted = muted

    def refresh_usb_devices(self):
        """Re-enumerate native devices after C20 power-up without dropping SIP."""
        if WINDOWS:
            return
        if self.call and self.call_get_state(self.call) in (7, 8):
            return False  # Never replace device lists underneath running streams.
        for name in ('linphone_core_reload_sound_devices', 'linphone_core_reload_video_devices'):
            function = getattr(self.dll, name)
            function.argtypes, function.restype = [P], None
            function(self.core)
        self.apply_settings(self.config.get('terminal_settings', {}))
        from platforms.c20_volume import reapply
        reapply()
        logging.info('C20 devices refreshed after USB wake')

    def devices(self):
        def strings(pointer):
            values, index = [], 0
            while pointer and pointer[index] and index < 100:
                values.append(pointer[index].decode(errors='replace'))
                index += 1
            return values
        result = {'camera': strings(self.core_get_video_devices(self.core)), 'microphone': [], 'speaker': []}
        devices = self.core_get_extended_audio_devices(self.core)
        node = devices
        while node:
            device = node.contents.data
            name = (self.audio_device_get_id(device) or b'').decode(errors='replace')
            capabilities = self.audio_device_get_capabilities(device)
            for key, flag in [('microphone', 1), ('speaker', 2)]:
                if capabilities & flag and name not in result[key]:
                    result[key].append(name)
            self.audio_device_unref(device)
            node = node.contents.next
        self.bctbx.bctbx_list_free(devices)
        if not WINDOWS:
            from platforms.linux_media import c20_devices
            return c20_devices(result)
        return result

    def diagnostics(self):
        return {key: (getter(self.core) or b'').decode(errors='replace') for key, getter in
                [('camera', self.core_get_video_device), ('microphone', self.core_get_capture_device),
                 ('speaker', self.core_get_playback_device), ('ringer', self.core_get_ringer_device)]} | {
                     'registered': self.registered, 'devices': self.devices(),
                     'audio_profile': self.applied_audio_profile,
                     'requested_audio_profile': self.audio_profile,
                     'auto_framing_status': self.auto_framing.status if getattr(self, 'auto_framing', None)
                     else 'unsupported'}

    def media_stats(self):
        result = {}
        if self.call:
            for kind, getter in [('audio', self.call_get_audio_stats), ('video', self.call_get_video_stats)]:
                stats = getter(self.call)
                if stats:
                    result[kind] = {'download_kbps': self.call_stats_get_download_bandwidth(stats),
                                    'upload_kbps': self.call_stats_get_upload_bandwidth(stats),
                                    'jitter_buffer_ms': self.call_stats_get_jitter_buffer_size_ms(stats),
                                    'round_trip_seconds': self.call_stats_get_round_trip_delay(stats),
                                    'receiver_loss_percent': self.call_stats_get_receiver_loss_rate(stats),
                                    'sender_loss_percent': self.call_stats_get_sender_loss_rate(stats)}
                    self.call_stats_unref(stats)
            if 'video' in result:
                params = self.call_get_current_params(self.call)
                if params:
                    result['video']['received_fps'] = self.call_params_get_received_framerate(params)
                    result['video']['sent_fps'] = self.call_params_get_sent_framerate(params)
                    for direction in ('sent', 'received'):
                        size = getattr(self, 'call_params_get_'+direction+'_video_size')(params)
                        if size.width > 0 and size.height > 0:
                            result['video'][direction+'_resolution'] = [size.width, size.height]
        return result

    def iterate(self):
        self.sync_speaker_mute()
        self.core_iterate(self.core)
        now = time.monotonic()
        if WINDOWS and self.call and self.call_get_state(self.call) == 8 and now >= self._next_video_probe:
            # Sample actual decoded frames rather than RTP/RTCP traffic. Re-arm
            # on the UI thread, never recursively from the native callback.
            self.call_request_notify_next_video_frame_decoded(self.call)
            self._next_video_probe = now + 1

    def close(self):
        if getattr(self, 'auto_framing', None):
            self.auto_framing.close()
        if not self.core:
            return
        self.end()
        self.hold_call(None)
        self.core_stop(self.core)
        self.core_unref(self.core)
        self.core = None


def __getattr__(name):
    if name == 'NativeQRScanner':
        from native_qr import NativeQRScanner
        return NativeQRScanner
    raise AttributeError(name)


# Preserve the historical engine.QRScanner import for integrations.
from qr_scanner import QRScanner as QRScanner  # noqa: E402 -- compatibility re-export
