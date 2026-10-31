"""Strict SIP TLS and TURN TLS policy, applied on the native core owner thread."""
import ctypes as C
import os
import re
import ssl
import time
import sys


# @llr LLR-TERM-COM-010
def validate(config, now=None):
    policy = config.get('secure_calls')
    if policy is None:
        if 'transport=tls' in (config.get('sip') or {}).get('proxy', ''):
            raise ValueError('Missing secure-call policy')
        return None
    if not isinstance(policy, dict) or policy.get('mode') != 'tls-relay':
        raise ValueError('Unsupported secure-call policy')
    host = r'[a-zA-Z0-9][a-zA-Z0-9.-]{0,252}'
    sip = re.fullmatch(r'sip:' + host + r':([0-9]{1,5});transport=tls', (config.get('sip') or {}).get('proxy', ''))
    turn = re.fullmatch(host + r':([0-9]{1,5})', policy.get('turn_server', '')) if isinstance(policy.get('turn_server'), str) else None
    if not sip or not 1 <= int(sip[1]) <= 65535:
        raise ValueError('Secure calls require a valid SIP TLS endpoint')
    if not turn or not 1 <= int(turn[1]) <= 65535:
        raise ValueError('Secure calls require a valid TURN TLS endpoint')
    for field in ('turn_username', 'turn_password', 'turn_realm'):
        value = policy.get(field)
        if not isinstance(value, str) or not 1 <= len(value) <= 512 or any(c.isspace() for c in value):
            raise ValueError('Invalid TURN credentials')
    expires = policy.get('expires')
    if type(expires) is not int or expires <= (time.time() if now is None else now):
        raise ValueError('Expired TURN credentials; reconnect to the server')
    return policy


# @llr LLR-TERM-COM-010
def configure(engine):
    policy = validate(engine.config)
    if policy is None:
        return
    if sys.platform.startswith('linux'):
        from zmala_terminal.linux.turn_runtime import require_loaded
        require_loaded()

    def api(name, result, types, *args):
        function = getattr(engine.dll, 'linphone_' + name)
        function.restype, function.argtypes = result, types
        return function(*args)

    p, s, i = C.c_void_p, C.c_char_p, C.c_int
    # Trust is installed locally, never supplied by the remote configuration.
    ca = os.environ.get('SSL_CERT_FILE') or ssl.get_default_verify_paths().cafile
    if not ca:
        raise RuntimeError('A trusted CA bundle is required for secure calls')
    api('core_set_root_ca', None, [p, s], engine.core, os.fsencode(ca))
    api('core_verify_server_certificates', None, [p, i], engine.core, 1)
    api('core_verify_server_cn', None, [p, i], engine.core, 1)
    engine.core_set_media_encryption(engine.core, 1)
    engine.core_set_media_encryption_mandatory(engine.core, 1)
    api('core_enable_forced_ice_relay', None, [p, i], engine.core, 1)
    _configure_relay(engine, policy)


# @llr LLR-TERM-COM-010
def _configure_relay(engine, policy, previous=None):
    """Replace only TURN/ICE policy; never enumerate or open media devices."""
    def api(name, result, types, *args):
        function = getattr(engine.dll, 'linphone_' + name)
        function.restype, function.argtypes = result, types
        return function(*args)

    p, s, i = C.c_void_p, C.c_char_p, C.c_int
    nat = api('core_create_nat_policy', p, [p], engine.core)
    if not nat:
        raise RuntimeError('Cannot allocate secure media policy')
    try:
        for setting, enabled in (('ice', 1), ('turn', 1), ('stun', 1),
                                 ('udp_turn_transport', 0), ('tcp_turn_transport', 0),
                                 ('tls_turn_transport', 1)):
            api('nat_policy_enable_' + setting, None, [p, i], nat, enabled)
        api('nat_policy_set_stun_server', None, [p, s], nat, policy['turn_server'].encode())
        api('nat_policy_set_stun_server_username', None, [p, s], nat, policy['turn_username'].encode())
        auth = engine.auth_info_new(policy['turn_username'].encode(), None,
                                    policy['turn_password'].encode(), None,
                                    policy['turn_realm'].encode(), None)
        if not auth:
            raise RuntimeError('Cannot allocate TURN credentials')
        old = saved = None
        try:
            if previous:
                old = api('core_find_auth_info', p, [p, s, s, s], engine.core,
                          previous['turn_realm'].encode(), previous['turn_username'].encode(), None)
                if old:
                    saved = api('auth_info_clone', p, [p], old)
                    if not saved:
                        raise RuntimeError('Cannot retain previous TURN credentials')
            # The installed SDK can append even when the username is unchanged.
            # Remove exactly the old TURN entry; retain a copy for rollback.
            if old:
                api('core_remove_auth_info', None, [p, p], engine.core, old)
            try:
                engine.core_add_auth_info(engine.core, auth)
                api('core_set_nat_policy', None, [p, p], engine.core, nat)
            except Exception:
                api('core_remove_auth_info', None, [p, p], engine.core, auth)
                if saved:
                    engine.core_add_auth_info(engine.core, saved)
                raise
        finally:
            if saved:
                engine.auth_info_unref(saved)
            engine.auth_info_unref(auth)
    finally:
        api('nat_policy_unref', None, [p], nat)


# @llr LLR-TERM-COM-010
def credentials_only(previous, desired):
    """Allow only relay credential changes plus independently polled contact state."""
    if not isinstance(previous, dict) or not isinstance(desired, dict):
        return False
    ignored = {'secure_calls', 'contacts', 'callbacks'}
    if {k:v for k,v in previous.items() if k not in ignored} != {k:v for k,v in desired.items() if k not in ignored}:
        return False
    old, new = previous.get('secure_calls'), desired.get('secure_calls')
    if not isinstance(old, dict) or not isinstance(new, dict) or old == new:
        return False
    credentials = {'turn_username', 'turn_password', 'expires'}
    return {k:v for k,v in old.items() if k not in credentials} == {k:v for k,v in new.items() if k not in credentials}


# @llr LLR-TERM-COM-010
def refresh_credentials(engine, config):
    """Apply a validated idle renewal without changing transports or core ownership."""
    if engine.call or not credentials_only(engine.config, config):
        raise ValueError('Relay renewal requires an idle, otherwise unchanged core')
    policy = validate(config)
    _configure_relay(engine, policy, engine.config['secure_calls'])
    engine.config = config
