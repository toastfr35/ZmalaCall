# @test T-HLT-001
# @requirements HLR-TERM-CALL-001
# @environment hardware
# @plan Start isolated caller/receiver peers and the real terminal UI; assert allowed calls connect and forbidden accounts fail without unintended media.
# @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

"""Provision isolated QA accounts, exercise real group calls, then remove them.

Uses static images and file audio, with separate runtime profiles.
"""
import json
import os
import argparse
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

ROOT = (Path(__file__).resolve().parents[3] / 'zmala_terminal')
server_state = Path(os.environ.get('ZMALA_TEST_SERVER_STATE', ROOT.parent / 'zmala_server/data/server.json')).resolve()
settings = json.loads(server_state.read_text())
base = f"http://127.0.0.1:{settings['http_port']}"


def api(route, method='GET', data=None):
    request = urllib.request.Request(base + route, method=method,
        headers={'Authorization': 'Bearer ' + settings['admin_token'], 'Content-Type': 'application/json'},
        data=None if data is None else json.dumps(data).encode())
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.load(response)


def pair(caller, receiver, denied=False):
    processes, logs = [], []
    try:
        for user, dial, duration in [(receiver, None, 17 if not denied else 8), (caller, receiver, 15 if not denied else 6)]:
            log = (ROOT / f'data/live-{user}.log').open('w')
            logs.append(log)
            args = [sys.executable, str(ROOT.parent / 'tests/support/terminal/sip_peer.py'), '--user', user, '--duration', str(duration)]
            if dial:
                args += ['--dial', dial]
                if denied:
                    args += ['--expect-denied']
            processes.append(subprocess.Popen(args, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT))
        for process in processes:
            assert process.wait(timeout=30) == 0, 'SIP peer failed; check data/live-qa_*.log'
        results = {u: json.loads((ROOT / f'data/test-{u}-result.json').read_text()) for u in [caller, receiver]}
        if denied:
            assert 403 in results[caller]['errors']
            assert 1 not in results[receiver]['states'], 'Forbidden call reached the recipient'
            print('Accounts without a shared group rejected with SIP 403; recipient did not ring.')
        else:
            for result in results.values():
                assert 8 in result['states'] and all(result['received_media'].values()), results
            print('Allowed direction connected with bidirectional audio/video and terminal caller authentication.')
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
        for log in logs:
            log.close()


def ui_call(video_cycle=False):
    bootstrap = ROOT / 'data/qa-terminal.json'
    bootstrap.write_text(json.dumps(api('/api/terminal-bootstrap?id=qa_terminal')))
    processes, logs = [], []
    try:
        ui_profile = 'qa-ui' if 'ZMALA_TEST_SERVER_STATE' not in os.environ else 'qa-ui-' + str(time.time_ns())
        ui_args = [str(ROOT.parent / 'tests/terminal/HLT/terminal_ui_call.py'), '--bootstrap', str(bootstrap), '--profile', ui_profile]
        peer_args = [str(ROOT.parent / 'tests/support/terminal/sip_peer.py'), '--user', 'qa_phone', '--duration', '28' if video_cycle else '19']
        if video_cycle:
            ui_args += ['--video-cycle', '--dial', 'qa_phone']
            peer_args += ['--video-cycle']
        else:
            peer_args += ['--dial', 'qa_terminal']
        for name, args in [('terminal-ui', ui_args), ('caller', peer_args)]:
            log = (ROOT / f'data/live-{name}.log').open('w')
            logs.append(log)
            processes.append(subprocess.Popen([sys.executable, *args], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT))
            if name == 'terminal-ui':
                deadline = time.monotonic() + 8
                while time.monotonic() < deadline:
                    if any(r['user'] == 'qa_terminal' for r in api('/api/admin')['sip_status']['registrations']):
                        break
                    time.sleep(.2)
                else:
                    raise AssertionError('QA terminal UI did not register')
        for process in processes:
            assert process.wait(timeout=30) == 0, 'UI call failed; check data/live-terminal-ui.log and data/live-caller.log'
        print('Dark carousel terminal answered, received audio/video, rendered native video and returned home.')
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
        for log in logs:
            log.close()


created, group_id = [], None
parser = argparse.ArgumentParser()
parser.add_argument('--ui-only', action='store_true', help='Only exercise the real terminal call display')
parser.add_argument('--video-cycle', action='store_true', help='Check confirmed outgoing calls and missing-video recovery')
args = parser.parse_args()
try:
    for user, kind in [('qa_phone', 'linphone'), ('qa_terminal', 'terminal')]:
        api('/api/users', 'POST', {'id': user, 'name': 'Temporary ' + user, 'type': kind, 'emails': [user+'@example.test']})
        created.append(user)
    group_id = api('/api/groups', 'POST', {'name': 'Temporary media QA', 'members': created})['id']
    if not args.ui_only:
        pair('qa_phone', 'qa_terminal')
        pair('qa_terminal', 'qa_phone')
    ui_call(args.video_cycle)
    api('/api/groups/' + group_id, 'DELETE')
    group_id = None
    if not args.ui_only:
        pair('qa_terminal', 'qa_phone', denied=True)
finally:
    if group_id:
        api('/api/groups/' + group_id, 'DELETE')
    for user in reversed(created):
        api('/api/users/' + user, 'DELETE')
