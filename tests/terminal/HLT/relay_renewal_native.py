# @test T-HLT-038
# @requirements HLR-TERM-COM-009
# @environment hardware
# @plan On a Pi with the installed SDK, use an isolated non-started native core and
# synthetic loopback relay credentials. Renew 50 credential sets (including unchanged usernames) and inspect the actual
# native NAT policy and authentication list after each renewal. Keep one SIP entry.
# No call, real credential, camera, microphone or USB power command is used.
# @pass Each renewal selects its new TURN username and TLS-only policy, the auth
# list stays at exactly SIP+TURN, the SIP entry survives, and native refs are released.
# This verifies SDK integration, not a real relay handshake or physical USB sleep.
import copy
import ctypes as C
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from zmala_terminal.common.linphone_api import LinphoneAPI, ListNode, P, S
from zmala_terminal.common import secure_calls


def main():
    api = LinphoneAPI(); api.load_api()
    def native(name, result, types, *args):
        f = getattr(api.dll, 'linphone_' + name)
        f.restype, f.argtypes = result, types
        return f(*args)
    with tempfile.TemporaryDirectory(prefix='relay-renewal-') as folder:
        factory = api.factory_get()
        for kind in ('config', 'data', 'download', 'cache'):
            native('factory_set_'+kind+'_dir', None, [P,S], factory, folder.encode())
        api.core = api.factory_create_core_3(factory, None, None, None)
        assert api.core
        try:
            api.call = None
            expiry = int(time.time()) + 8*3600
            api.config = {'sip':{'proxy':'sip:127.0.0.1:5061;transport=tls'}, 'secure_calls':{
                'mode':'tls-relay','turn_server':'127.0.0.1:5349','turn_realm':'fixture',
                'turn_username':'0:fixture','turn_password':'test-only','expires':expiry}}
            auth = api.auth_info_new(b'sip-fixture', None, b'test-only', None, b'sip-fixture', None)
            api.core_add_auth_info(api.core, auth); api.auth_info_unref(auth)
            secure_calls._configure_relay(api, api.config['secure_calls'])
            for i in range(1,51):
                desired = copy.deepcopy(api.config)
                desired['secure_calls']['turn_username'] = f'{(i+1)//2}:fixture'
                desired['secure_calls']['turn_password'] = f'test-only-{i}'
                secure_calls.refresh_credentials(api, desired)
                nat = native('core_get_nat_policy', P, [P], api.core)
                assert native('nat_policy_get_stun_server_username', S, [P], nat) == f'{(i+1)//2}:fixture'.encode()
                for transport, enabled in [('tls',1),('udp',0),('tcp',0)]:
                    assert native('nat_policy_'+transport+'_turn_transport_enabled', C.c_int, [P], nat) == enabled
                head = native('core_get_auth_info_list', C.POINTER(ListNode), [P], api.core)
                count = 0
                while head:
                    count += 1; assert count <= 2, f'renewal {i}: more than two auth entries'
                    head = head.contents.next
                assert count == 2, f'renewal {i}: {count} auth entries'
                assert native('core_find_auth_info', P, [P,S,S,S], api.core, b'sip-fixture', b'sip-fixture', None)
            print('PASS: 50 native relay renewals; TLS policy retained; exactly SIP + TURN credentials')
        finally:
            api.core_unref(api.core)


if __name__ == '__main__': main()
