"""Explicit real-Pi peer for A-HLT-006; stop the kiosk before running, restore it afterward."""
import argparse
import json
from pathlib import Path
import sys
import time
import urllib.request

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--root', required=True, type=Path)
parser.add_argument('--contact', required=True)
parser.add_argument('--report', required=True, type=Path)
args = parser.parse_args()
sys.path.insert(0, str(args.root))
from zmala_terminal.linux.turn_runtime import prepare  # noqa: E402
prepare()
from zmala_terminal.common.engine import Engine  # noqa: E402

bootstrap = json.loads(Path('/var/lib/zmalacall/terminal/provisioning.json').read_text())['bootstrap']
request = urllib.request.Request(bootstrap['server_url'] + '/api/config',
                                 headers={'Authorization': 'Bearer ' + bootstrap['device_token']})
config = json.load(urllib.request.urlopen(request, timeout=10))
assert config['secure_calls']['mode'] == 'tls-relay'
contact = next(c for c in config['contacts'] if c['id'] == args.contact and c['can_call'])
def call_changed(call, state, user, domain):
    if state in (13, 14, 19):
        engine.hold_call(None)


engine = Engine(config, call_changed, lambda *x: None, profile='tls-diagnostic')
samples = []
try:
    deadline = time.monotonic() + 20
    while not engine.registered and time.monotonic() < deadline:
        engine.iterate()
        time.sleep(.02)
    assert engine.registered, 'Native peer did not register'
    engine.dial('sip:' + contact['id'] + '@' + config['sip']['domain'])
    started = time.monotonic()
    sampled = started
    while time.monotonic() - started < 55:
        engine.iterate()
        time.sleep(.02)
        if time.monotonic() - sampled >= 1:
            stats = engine.media_stats()
            stats['decoded_video'] = engine.incoming_video_active()
            samples.append(stats)
            sampled = time.monotonic()
        if time.monotonic() - started > 8 and not engine.call:
            break
    good = [s for s in samples if s.get('decoded_video') and
            s.get('video', {}).get('received_fps', 0) > 1 and
            all(s.get(k, {}).get(d, 0) > 1 for k in ('audio', 'video')
                for d in ('download_kbps', 'upload_kbps'))]
    assert len(good) >= 10, 'Pi did not sustain decoded video and bidirectional media'
    print('Native Pi peer passed: decoded video and bidirectional media in', len(good), 'samples.')
finally:
    args.report.write_text(json.dumps(samples, indent=2))
    engine.close()
