"""Advertise a current LAN IPv4 address; SIP/HTTP still bind all interfaces."""
import json
import os
import subprocess

adapters = json.loads(subprocess.check_output(['ip', '-j', '-4', 'address'], text=True))
choices = [(a['ifname'], v['local']) for a in adapters if a.get('operstate') == 'UP'
           for v in a.get('addr_info', []) if v.get('scope') == 'global']
choices.sort(key=lambda pair: (pair[0] != 'eth0', pair[0] != 'wlan0'))
if not choices:
    raise SystemExit('No LAN IPv4 address yet; systemd will retry.')
os.environ['VIDEOCALL_HOST'] = choices[0][1]
os.execv('/usr/bin/node', ['node', '/opt/zmalacall-server/current/zmala_server/main.js'])
