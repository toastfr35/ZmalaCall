"""Shared Liblinphone ABI; library discovery is delegated to platform adapters."""
import ctypes as C
from platforms.native_runtime import ROOT as ROOT, SDK as SDK, load_linphone

# ABI aliases are also re-exported by engine for native integration probes.
P, S, I = C.c_void_p, C.c_char_p, C.c_int
CALL_CB = C.CFUNCTYPE(None, P, P, I, S)
REG_CB = C.CFUNCTYPE(None, P, P, I, S)
MESSAGE_CB = C.CFUNCTYPE(None, P, P, P)
VIDEO_EVENT_CB = C.CFUNCTYPE(None, P, P, C.c_uint, P)
VIDEO_FRAME_CB = C.CFUNCTYPE(None, P)


def encoded(value):
    return str(value).encode('utf-8') if value is not None else None


class OglContext(C.Structure):
    _fields_ = [('window', P), ('width', C.c_uint), ('height', C.c_uint), ('getProcAddress', P)]


class VideoSize(C.Structure):
    _fields_ = [('width', I), ('height', I)]


class ListNode(C.Structure):
    pass


ListNode._fields_ = [('next', C.POINTER(ListNode)), ('prev', C.POINTER(ListNode)), ('data', P)]


SIGNATURES = {
    'factory_get': (P, []), 'factory_create_core_3': (P, [P, S, S, P]),
    'factory_create_core_cbs': (P, [P]),
    'core_cbs_set_call_state_changed': (None, [P, CALL_CB]),
    'core_cbs_set_registration_state_changed': (None, [P, REG_CB]),
    'core_cbs_set_message_received': (None, [P, MESSAGE_CB]),
    'chat_message_get_from_address': (P, [P]),
    'chat_message_get_custom_header': (S, [P, S]),
    'chat_message_get_utf8_text': (S, [P]), 'chat_message_is_text': (I, [P]),
    'core_add_callbacks': (None, [P, P]), 'core_cbs_unref': (None, [P]),
    'core_start': (I, [P]), 'core_stop': (None, [P]), 'core_unref': (None, [P]),
    'core_iterate': (None, [P]), 'core_get_config': (P, [P]),
    'core_set_inc_timeout': (None, [P, I]),
    'core_set_playback_gain_db': (None, [P, C.c_float]),
    'core_set_network_reachable': (None, [P, I]),
    'transports_new': (P, []), 'transports_set_udp_port': (None, [P, I]),
    'transports_set_tcp_port': (None, [P, I]), 'transports_set_tls_port': (None, [P, I]),
    'transports_set_dtls_port': (None, [P, I]), 'transports_unref': (None, [P]),
    'core_set_transports': (I, [P, P]),
    'config_set_int': (None, [P, S, S, I]), 'config_set_string': (None, [P, S, S, S]),
    'core_set_user_agent': (None, [P, S, S]),
    'core_enable_video_capture': (None, [P, I]), 'core_enable_video_display': (None, [P, I]),
    'core_enable_video_preview': (None, [P, I]), 'core_enable_echo_cancellation': (None, [P, I]),
    'core_enable_self_view': (None, [P, I]),
    'core_set_media_encryption': (I, [P, I]), 'core_set_media_encryption_mandatory': (None, [P, I]),
    'core_set_native_video_window_id': (None, [P, P]),
    'core_set_native_preview_window_id': (None, [P, P]),
    'core_use_preview_window': (None, [P, I]),
    'core_set_video_display_filter': (None, [P, S]),
    'core_set_preferred_video_size_by_name': (None, [P, S]),
    'core_set_preferred_video_size': (None, [P, VideoSize]),
    'core_get_preferred_video_size': (VideoSize, [P]),
    'core_enable_retransmission_on_nack': (None, [P, I]),
    'core_set_upload_bandwidth': (None, [P, I]), 'core_set_download_bandwidth': (None, [P, I]),
    'core_get_video_payload_types': (C.POINTER(ListNode), [P]),
    'payload_type_get_mime_type': (S, [P]), 'payload_type_enable': (I, [P, I]),
    'payload_type_unref': (None, [P]),
    'call_get_audio_stats': (P, [P]), 'call_get_video_stats': (P, [P]),
    'call_stats_get_download_bandwidth': (C.c_float, [P]),
    'call_stats_get_upload_bandwidth': (C.c_float, [P]), 'call_stats_unref': (None, [P]),
    'call_stats_get_jitter_buffer_size_ms': (C.c_float, [P]),
    'call_stats_get_round_trip_delay': (C.c_float, [P]),
    'call_stats_get_receiver_loss_rate': (C.c_float, [P]),
    'call_stats_get_sender_loss_rate': (C.c_float, [P]),
    'core_set_video_device': (I, [P, S]), 'core_get_video_device': (S, [P]),
    'core_set_capture_device': (I, [P, S]), 'core_get_capture_device': (S, [P]),
    'core_set_playback_device': (I, [P, S]), 'core_get_playback_device': (S, [P]),
    'core_set_ringer_device': (I, [P, S]), 'core_get_ringer_device': (S, [P]),
    'core_get_video_devices': (C.POINTER(S), [P]), 'core_get_sound_devices': (C.POINTER(S), [P]),
    'core_get_extended_audio_devices': (C.POINTER(ListNode), [P]),
    'audio_device_get_id': (S, [P]), 'audio_device_get_capabilities': (I, [P]),
    'audio_device_unref': (None, [P]),
    'core_set_ring': (None, [P, S]), 'core_set_ringback': (None, [P, S]),
    'core_create_proxy_config': (P, [P]), 'proxy_config_set_identity_address': (I, [P, P]),
    'proxy_config_set_server_addr': (I, [P, S]), 'proxy_config_set_route': (I, [P, S]),
    'proxy_config_enable_register': (None, [P, I]), 'proxy_config_set_expires': (None, [P, I]),
    'core_add_proxy_config': (I, [P, P]), 'core_set_default_proxy_config': (None, [P, P]),
    'proxy_config_unref': (None, [P]), 'auth_info_new': (P, [S, S, S, S, S, S]),
    'core_add_auth_info': (None, [P, P]), 'auth_info_unref': (None, [P]),
    'address_new': (P, [S]), 'address_unref': (None, [P]), 'address_get_username': (S, [P]),
    'address_get_domain': (S, [P]), 'call_get_remote_address': (P, [P]),
    'call_ref': (P, [P]), 'call_unref': (None, [P]), 'call_get_state': (I, [P]),
    'call_get_call_log': (P, [P]), 'call_log_get_call_id': (S, [P]),
    'call_get_remote_params': (P, [P]), 'call_params_get_custom_header': (S, [P, S]),
    'call_get_current_params': (P, [P]), 'call_params_video_enabled': (I, [P]),
    'call_params_get_video_direction': (I, [P]),
    'call_params_get_received_framerate': (C.c_float, [P]),
    'call_params_get_sent_framerate': (C.c_float, [P]),
    'call_params_get_sent_video_size': (VideoSize, [P]),
    'call_params_get_received_video_size': (VideoSize, [P]),
    'factory_create_call_cbs': (P, [P]), 'call_cbs_unref': (None, [P]),
    'call_cbs_set_next_video_frame_decoded': (None, [P, VIDEO_FRAME_CB]),
    'call_add_callbacks': (None, [P, P]), 'call_remove_callbacks': (None, [P, P]),
    'call_request_notify_next_video_frame_decoded': (None, [P]),
    'call_terminate': (I, [P]), 'call_decline': (I, [P, I]),
    'core_create_call_params': (P, [P, P]), 'call_params_enable_video': (None, [P, I]),
    'call_params_set_audio_direction': (None, [P, I]), 'call_params_enable_mic': (None, [P, I]),
    'call_params_set_media_encryption': (None, [P, I]), 'call_params_unref': (None, [P]),
    'core_invite_address_with_params': (P, [P, P, P]), 'call_accept_with_params': (I, [P, P]),
    'core_get_current_call': (P, [P]), 'core_refresh_registers': (None, [P]),
}


class LinphoneAPI:
    def load_api(self):
        self.dll = load_linphone(self)
        for name, (result, arguments) in SIGNATURES.items():
            function = getattr(self.dll, 'linphone_' + name)
            function.restype, function.argtypes = result, arguments
            setattr(self, name, function)
