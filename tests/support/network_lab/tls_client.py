"""Lab-only SIP TLS + ICE/SRTP + TURN TLS configuration for the native Engine."""
import ctypes as C
import json
from pathlib import Path


def configure(engine, identity):
    def api(name, result, types, *args):
        f = getattr(engine.dll, 'linphone_'+name)
        f.restype, f.argtypes = result, types
        return f(*args)
    p, s, i = C.c_void_p, C.c_char_p, C.c_int
    transports = engine.transports_new()
    engine.transports_set_udp_port(transports, 0)
    engine.transports_set_tcp_port(transports, 0)
    engine.transports_set_tls_port(transports, -1)
    engine.core_set_transports(engine.core, transports)
    engine.transports_unref(transports)
    api('core_set_root_ca', None, [p, s], engine.core, b'/lab/ca.pem')
    api('core_verify_server_certificates', None, [p, i], engine.core, 1)
    api('core_verify_server_cn', None, [p, i], engine.core, 1)
    engine.core_set_media_encryption(engine.core, 1)  # SRTP, keys carried by TLS signalling.
    engine.core_set_media_encryption_mandatory(engine.core, 1)
    api('core_enable_forced_ice_relay', None, [p, i], engine.core, 1)
    set_encryption = engine.call_params_set_media_encryption
    engine.call_params_set_media_encryption = lambda params, mode: set_encryption(params, 1)
    policy = api('core_create_nat_policy', p, [p], engine.core)
    try:
        for setting, enabled in (('ice', 1), ('turn', 1), ('stun', 1),
                                 ('udp_turn_transport', 0), ('tcp_turn_transport', 0),
                                 ('tls_turn_transport', 1)):
            api('nat_policy_enable_'+setting, None, [p, i], policy, enabled)
        api('nat_policy_set_stun_server', None, [p, s], policy, b'10.231.100.14:443')
        api('nat_policy_set_stun_server_username', None, [p, s], policy, identity.encode())
        password = json.loads(Path('/lab/turn.json').read_text())[identity]
        auth = engine.auth_info_new(identity.encode(), None, password.encode(), None, b'zmala.lab', None)
        engine.core_add_auth_info(engine.core, auth)
        engine.auth_info_unref(auth)
        api('core_set_nat_policy', None, [p, p], engine.core, policy)
    finally:
        api('nat_policy_unref', None, [p], policy)


def status(engine):
    params = engine.call_get_current_params(engine.call) if engine.call else None
    if not params:
        return {}
    f = engine.dll.linphone_call_params_get_media_encryption
    f.restype, f.argtypes = C.c_int, [C.c_void_p]
    result = {'media_encryption': f(params)}
    ice = engine.dll.linphone_call_stats_get_ice_state
    ice.restype, ice.argtypes = C.c_int, [C.c_void_p]
    for kind in ('audio', 'video'):
        stats = getattr(engine, 'call_get_'+kind+'_stats')(engine.call)
        if stats:
            try:
                result[kind+'_ice_state'] = ice(stats)
            finally:
                engine.call_stats_unref(stats)
    return result
