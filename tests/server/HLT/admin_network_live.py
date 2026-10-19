# @test S-HLT-033
# @requirements HLR-SRV-AUTH-013
# @environment hardware
# @plan Explicitly opt in with an idle enrolled Android phone on USB and a host on the server LAN.
# Create a temporary admin session from the LAN, disable phone Wi-Fi and verify a mobile route.
# Through the phone's curl with normal certificate validation, probe admin pages, login and a
# valid admin session with forged forwarding headers; fetch authenticated app configuration.
# Restore Wi-Fi and revoke the temporary session in finally. Do not print credentials or config.
# @pass LAN admin responds 200; mobile admin requests respond 403 even with a valid session;
# mobile authenticated app configuration responds 200. Wi-Fi is restored and the session revoked.
import argparse
import json
import os
import re
import subprocess
import time
import requests


def main():
    parser = argparse.ArgumentParser(description='Opt-in live LAN administration boundary check')
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--adb', required=True)
    parser.add_argument('--serial', required=True)
    args = parser.parse_args()
    if not args.run:
        parser.error('--run is required; this temporarily disables phone Wi-Fi')

    def adb(*command, data=None):
        return subprocess.check_output([args.adb, '-s', args.serial, *command], input=data,
                                       text=True, timeout=25)

    enrollment = json.loads(adb('exec-out', 'run-as', 'org.zmala.phone', 'cat', 'no_backup/enrollment.json'))
    url = enrollment['server_url'].rstrip('/')
    assert url.startswith('https://')
    assert requests.get(url + '/', timeout=15).status_code == 200
    wifi = adb('shell', 'settings', 'get', 'global', 'wifi_on').strip()
    assert wifi in ('0', '1')
    login = requests.post(url + '/api/auth/login', json={
        'password': os.environ['ZMALA_TEST_ADMIN_PASSWORD'], 'session_token': True}, timeout=15)
    login.raise_for_status()
    session = login.json()['session_token']

    def probe(route, expected, token=None, method='GET'):
        # Config enters curl on stdin, never argv or a shared device file.
        config = ('silent\nshow-error\nmax-time = 15\noutput = "/dev/null"\n'
                  'write-out = "%{http_code}"\nurl = ' + json.dumps(url + route) + '\n'
                  'request = ' + json.dumps(method) + '\n'
                  'header = "X-Forwarded-For: 192.168.1.20"\n'
                  'header = "Forwarded: for=127.0.0.1"\n')
        if token:
            config += 'header = ' + json.dumps('Authorization: Bearer ' + token) + '\n'
        if method == 'POST':
            config += 'data = "{}"\n'
        status = adb('shell', 'curl', '--config', '-', data=config).strip()
        assert status == str(expected), (route, status, expected)
        print(method, route, status)

    try:
        adb('shell', 'svc', 'wifi', 'disable')
        for _ in range(20):
            route = adb('shell', 'ip', 'route', 'get', '1.1.1.1')
            if re.search(r'\bdev (?:rmnet|ccmni)', route):
                break
            time.sleep(1)
        else:
            raise AssertionError('No cellular route; external check not performed')
        assert adb('shell', 'settings', 'get', 'global', 'wifi_on').strip() == '0'
        for route in ['/', '/admin.js', '/api/auth/status', '/api/admin']:
            probe(route, 403, session)
        probe('/api/auth/login', 403, method='POST')
        probe('/api/app/config', 200, enrollment['device_token'])
        probe('/health', 200)
    finally:
        try:
            adb('shell', 'svc', 'wifi', 'enable' if wifi == '1' else 'disable')
        finally:
            response = requests.post(url + '/api/auth/logout',
                                     headers={'Authorization': 'Bearer ' + session}, timeout=15)
            response.raise_for_status()
        assert adb('shell', 'settings', 'get', 'global', 'wifi_on').strip() == wifi
        print('Wi-Fi restored; temporary admin session revoked')


if __name__ == '__main__':
    main()
