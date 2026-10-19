# @test A-HLT-005
# @requirements HLR-AND-CALL-005
# @environment hardware
# @plan Use the enrolled phone on mobile data (Wi-Fi off) and a Pi terminal on a separate NAT network. Verify trusted TLS on the public configuration, SIP and TURN endpoints and HTTPS health. Call both directions, inspect moving video and speech both ways, background the phone and verify push wake, decline and hangup. Supply an operator observation record only after those physical checks; save network preconditions with the result. No inbound rules may be added at either client.
# @pass Public TLS certificates validate, the phone uses cellular connectivity with Wi-Fi off, and every explicitly recorded physical call/media/push/cleanup observation is true. Endpoint probes alone or missing observations are not a passed hardware run.
"""Opt-in cross-network qualification with explicit operator media observations."""
import argparse
import json
from pathlib import Path
import socket
import ssl
import subprocess
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True)
    parser.add_argument('--sip-port', type=int, default=5061)
    parser.add_argument('--turn-port', type=int, default=5349)
    parser.add_argument('--https-port', type=int, default=443)
    parser.add_argument('--adb', default='adb')
    parser.add_argument('--serial', required=True)
    parser.add_argument('--observations', required=True, type=Path)
    args = parser.parse_args()

    def adb(*command):
        return subprocess.check_output([args.adb, '-s', args.serial, 'shell', *command],
                                       text=True, encoding='utf-8', errors='replace', timeout=15)

    assert adb('settings', 'get', 'global', 'wifi_on').strip() == '0', 'Turn phone Wi-Fi off.'
    network = adb('dumpsys', 'connectivity')
    assert 'CELLULAR' in network and 'VALIDATED' in network, 'Cellular internet is not established.'
    context = ssl.create_default_context()
    for port in (args.https_port, args.sip_port, args.turn_port):
        with socket.create_connection((args.host, port), timeout=10) as connection:
            with context.wrap_socket(connection, server_hostname=args.host) as tls:
                assert tls.getpeercert() and tls.version() in ('TLSv1.2', 'TLSv1.3')
                print(f'Trusted TLS endpoint: {args.host}:{port} ({tls.version()})')
    authority = args.host if args.https_port == 443 else f'{args.host}:{args.https_port}'
    with urllib.request.urlopen(f'https://{authority}/health', timeout=10) as response:
        assert json.load(response)['ok'] is True
    observations = json.loads(args.observations.read_text(encoding='utf-8'))
    for field in ('different_client_networks', 'no_client_inbound_rules', 'outgoing_two_way_audio',
                  'outgoing_two_way_moving_video', 'incoming_two_way_audio',
                  'incoming_two_way_moving_video', 'background_push_wake', 'decline', 'hangup'):
        assert observations.get(field) is True, f'Missing successful physical observation: {field}'
    print('PASS: trusted endpoints, cellular preconditions and explicit physical observations.')


if __name__ == '__main__':
    main()
