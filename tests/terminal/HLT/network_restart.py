# @test T-HLT-031
# @requirements HLR-TERM-NET-001
# @environment hardware
# @plan On a configured Pi with Ethernet and a controlled Wi-Fi AP connected, run --before with its provisioning file and a private evidence path. Reboot normally, then run --after with the same arguments. Fetch and validate real server configuration through a socket bound separately to eth0 and wlan0, inspect NetworkManager's active saved Wi-Fi UUID/autoconnect and compare boot IDs/profile identity. No network settings are changed by this test.
# @pass Both interface-bound authenticated requests succeed before and after a real reboot, with unchanged terminal identity and saved Wi-Fi profile. This opt-in script never reboots the terminal itself. It retains only boot IDs, profile UUID and terminal ID; no credentials, SSID or response payloads.

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import urllib.request
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from zmala_terminal.common.configuration import Configuration, NoCredentialRedirect


def command(*args):
    return subprocess.check_output(args, text=True, timeout=15).strip()


def measure(bootstrap, interfaces):
    if sys.platform != 'linux' or os.geteuid() != 0:
        raise RuntimeError('Run as root on the prepared Pi; interface binding requires privilege')
    wifi = interfaces[1]
    identifier = command('nmcli', '-g', 'GENERAL.CON-UUID', 'device', 'show', wifi)
    if not identifier or identifier == '--':
        raise AssertionError('Wi-Fi has no active saved connection')
    if command('nmcli', '-g', 'connection.autoconnect', 'connection', 'show', 'uuid', identifier) != 'yes':
        raise AssertionError('Wi-Fi profile is not configured to reconnect')
    if command('nmcli', '-g', 'connection.type', 'connection', 'show', 'uuid', identifier) != '802-11-wireless':
        raise AssertionError('The selected connection is not Wi-Fi')
    with tempfile.TemporaryDirectory(prefix='zmala-network-rbt-') as directory:
        config = Configuration(bootstrap, Path(directory)/'cache.json')
        config.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoCredentialRedirect())
        try:
            for interface in interfaces:
                def connection(address, timeout=4, source_address=None, **kwargs):
                    last = None
                    for family, kind, proto, _, destination in socket.getaddrinfo(*address, type=socket.SOCK_STREAM):
                        stream = socket.socket(family, kind, proto)
                        try:
                            stream.settimeout(timeout)
                            stream.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, interface.encode()+b'\0')
                            stream.connect(destination)
                            return stream
                        except OSError as error:
                            last = error
                            stream.close()
                    raise last or OSError('No server address resolved')
                with patch.object(socket, 'create_connection', side_effect=connection):
                    received = config.fetch(persist=False)
                if received['device_id'] != bootstrap['device_id']:
                    raise AssertionError('Interface request returned another terminal identity')
        finally:
            config.deactivate()
    return {'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            'wifi_uuid': identifier, 'device_id': bootstrap['device_id'], 'interfaces': interfaces}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--before', action='store_true')
    modes.add_argument('--after', action='store_true')
    parser.add_argument('--provisioning', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--ethernet', default='eth0')
    parser.add_argument('--wifi', default='wlan0')
    args = parser.parse_args()
    saved = json.loads(args.provisioning.read_text())
    sample = measure(saved['bootstrap'], [args.ethernet, args.wifi])
    if args.before:
        # Do not overwrite evidence from an earlier acceptance run by accident.
        with args.evidence.open('x') as output:
            json.dump(sample, output, indent=2)
        print('T-HLT-031: before-reboot checks passed; reboot and run --after.')
    else:
        before = json.loads(args.evidence.read_text())
        if before['boot_id'] == sample['boot_id']:
            raise AssertionError('No reboot occurred between measurements')
        for key in ('wifi_uuid', 'device_id', 'interfaces'):
            if sample[key] != before[key]:
                raise AssertionError('Network enrollment changed across reboot: '+key)
        print('T-HLT-031: both interfaces and Wi-Fi enrollment passed across reboot.')


if __name__ == '__main__':
    main()
