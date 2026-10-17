"""Real Liblinphone integration peer, run as a separate process per endpoint.

Uses a static camera and file audio to avoid capturing the room during tests.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from configuration import Configuration
from engine import Engine, P, S, I, encoded, SDK

parser = argparse.ArgumentParser()
parser.add_argument('--user', required=True)
parser.add_argument('--dial')
parser.add_argument('--duration', type=float, default=16)
parser.add_argument('--decline', action='store_true')
parser.add_argument('--expect-denied', action='store_true')
parser.add_argument('--video-cycle', action='store_true', help='Receive video initially; start, stop, then resume sending it')
parser.add_argument('--camera', help='Explicit real camera device, or auto; default uses a static test image')
args = parser.parse_args()
server_state = Path(os.environ.get('ZMALA_TEST_SERVER_STATE', ROOT.parent / 'zmala_server/data/server.json')).resolve()
server = json.loads(server_state.read_text())
isolated = 'ZMALA_TEST_SERVER_STATE' in os.environ
config = Configuration(bootstrap=server_state.parent / 'terminal.json' if isolated else ROOT / 'data/terminal.json',
                       cache=(server_state.parent if isolated else ROOT / 'data') / f'test-{args.user}-cache.json').fetch()
config['sip'].update(username=args.user, password=server['users'][args.user]['password'])
config['account_type'] = server['users'][args.user]['type']
if config['account_type'] == 'terminal':
    config['call_auth_key'] = server['users'][args.user]['device_token']
config['terminal_settings'] = {'camera': (None if args.camera == 'auto' else args.camera)
                             if args.camera else 'StaticImage: Static picture'}
events, pending, errors = [], [], []
received_media = {'audio': False, 'video': False}
engine = None


def on_call(call, state, user, domain):
    events.append(state)
    print(json.dumps({'user': args.user, 'call_state': state, 'remote': user}), flush=True)
    if state == 1:
        engine.hold_call(call)
        pending.append(('decline' if args.decline else 'answer', time.monotonic() + .8))
    elif state in (14, 19):
        engine.hold_call(None)
    elif state == 13:
        info = engine.dll.linphone_call_get_error_info
        info.argtypes, info.restype = [P], P
        code = engine.dll.linphone_error_info_get_protocol_code
        code.argtypes, code.restype = [P], I
        error = info(call)
        errors.append(code(error) if error else 0)


engine = Engine(config, on_call, lambda r: print(json.dumps({'user':args.user,'registered':r}),flush=True), profile='test-' + args.user)
set_direction = engine.dll.linphone_call_params_set_video_direction
set_direction.argtypes, set_direction.restype = [P, I], None
update = engine.dll.linphone_call_update
update.argtypes, update.restype = [P, P], I
connected_at, video_steps = None, []
if args.video_cycle:
    enable_video = engine.call_params_enable_video
    def receive_only(params, enabled):
        enable_video(params, enabled)
        set_direction(params, 2)
    engine.call_params_enable_video = receive_only
for name, types, arguments in [('core_set_use_files', [P, I], [engine.core, 1]),
                               ('core_set_play_file', [P, S], [engine.core, encoded(SDK / 'share/sounds/linphone/hello8000.wav')])]:
    function = getattr(engine.dll, 'linphone_' + name)
    function.argtypes, function.restype = types, None
    function(*arguments)
start = time.monotonic()
dialed = False
decoded_video = False
try:
    while time.monotonic() - start < args.duration:
        engine.iterate()
        decoded_video |= engine.incoming_video_active()
        if args.video_cycle and engine.call and engine.call_get_state(engine.call) == 8:
            if connected_at is None:
                connected_at = time.monotonic()
                video_steps = [(4, 3), (9, 2), (13, 3)]
            if video_steps and time.monotonic() - connected_at >= video_steps[0][0]:
                _, direction = video_steps.pop(0)
                params = engine.core_create_call_params(engine.core, engine.call)
                enable_video(params, 1)
                set_direction(params, direction)
                assert update(engine.call, params) == 0, 'Video renegotiation failed'
                engine.call_params_unref(params)
                print(json.dumps({'video_direction': direction}), flush=True)
        for kind, stats in engine.media_stats().items():
            if stats['download_kbps'] > 0:
                received_media[kind] = True
        if args.dial and engine.registered and not dialed and time.monotonic() - start > 2:
            engine.dial(f'sip:{args.dial}@{server["host"]}')
            dialed = True
        for action, when in list(pending):
            if time.monotonic() >= when:
                pending.remove((action, when))
                engine.end(True) if action == 'decline' else engine.answer()
        time.sleep(.02)
finally:
    engine.close()
    (ROOT / f'data/test-{args.user}-result.json').write_text(json.dumps({'registered':dialed or engine.registered,'states':events, 'received_media':received_media,'decoded_video':decoded_video,'errors':errors}))
if args.expect_denied:
    sys.exit(0 if 403 in errors and 8 not in events else 1)
if args.dial and (8 not in events or not all(received_media.values())) and not args.decline:
    sys.exit(1)
