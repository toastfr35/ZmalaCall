# @test T-HLT-014
# @requirements THLR008, THLR009
# @environment hardware
# @plan Run the real terminal against a controlled SIP peer, establish and end a call, collect native media counters and screenshots; assert connection, decoded video and cleanup.
# @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

"""Exercise the real terminal UI and its native embedded video surface."""
import ctypes as C
import argparse
import json
from pathlib import Path
import sys
import time
import faulthandler
faulthandler.enable()

ROOT = (Path(__file__).resolve().parents[3] / 'zmala_terminal')
sys.path.insert(0, str(ROOT.parent))
from zmala_terminal.common.main import Terminal
from zmala_terminal.common.model import State
from zmala_terminal.common.engine import P, S, I, encoded, SDK

parser = argparse.ArgumentParser()
parser.add_argument('--bootstrap', type=Path, default=ROOT / 'data/terminal.json')
parser.add_argument('--profile', default='terminal')
parser.add_argument('--video-cycle', action='store_true')
parser.add_argument('--dial')
parser.add_argument('--duration', type=float)
parser.add_argument('--fullscreen', action='store_true')
parser.add_argument('--live-camera', action='store_true', help='Explicitly send the connected webcam instead of a static image')
parser.add_argument('--real-audio', action='store_true', help='Explicitly use the Trust USB headset')
args=parser.parse_args()
terminal = Terminal(fullscreen=args.fullscreen, bootstrap=args.bootstrap.resolve(), profile=args.profile)
if args.fullscreen:
    # This integration test also runs without a window manager. Match the kiosk
    # resolution explicitly rather than relying on WM fullscreen support.
    terminal.root.geometry(f'{terminal.root.winfo_screenwidth()}x{terminal.root.winfo_screenheight()}+0+0')
    terminal.root.overrideredirect(True)
received = {'audio':False, 'video':False}
deadline = time.monotonic() + (args.duration or (25 if args.video_cycle else 17))
configured = None
connected = False
dialed = False
video_visibility = []
audio_during_missing = False
video_samples = []
media_samples = []
next_sample = 0
try:
    while time.monotonic() < deadline:
        terminal.root.update()
        engine = terminal.engine
        if engine and engine is not configured:
            camera = (next(name for name in engine.devices()['camera'] if not name.startswith('StaticImage:'))
                      if args.live_camera else 'StaticImage: Static picture')
            engine.core_set_video_device(engine.core,encoded(camera))
            if args.real_audio:
                devices = engine.devices()
                engine.apply_settings({kind: next(device for device in devices[kind] if 'Trust' in device)
                                       for kind in ('microphone', 'speaker')})
            for name, types, arguments in ([] if args.real_audio else [('core_set_use_files',[P,I],[engine.core,1]),
                                           ('core_set_play_file',[P,S],[engine.core,encoded(SDK/'share/sounds/linphone/hello8000.wav')])]):
                f = getattr(engine.dll,'linphone_'+name)
                f.argtypes, f.restype = types,None
                f(*arguments)
            configured = engine
        if terminal.model.state == State.RINGING:
            terminal.press('green')
        if args.dial and engine and engine.registered and not dialed and terminal.model.state == State.HOME:
            contacts = terminal.model.contacts
            target = next((i for i, contact in enumerate(contacts) if contact['id'] == args.dial and terminal.contact_online(contact)), None)
            if target is not None:
                terminal.model.index = target
                terminal.press('green')
                assert terminal.model.state == State.CONFIRMING and not engine.call
                terminal.root.update_idletasks()
                assert terminal.confirmation.winfo_ismapped()
                terminal.press('green')
                dialed = True
        if terminal.model.state == State.IN_CALL:
            connected = True
            terminal.render()
            terminal.root.update_idletasks()
            assert terminal.video.winfo_ismapped(), 'Video surface is not visible'
            visible = not terminal.missing_video_visible
            if sys.platform != 'win32' and visible and time.monotonic() >= next_sample:
                from PIL import ImageGrab
                window = terminal.video
                x, y = window.winfo_rootx(), window.winfo_rooty()
                sample = ImageGrab.grab(bbox=(x, y, x + window.winfo_width(), y + window.winfo_height()))
                video_samples.append(len(set(sample.resize((64, 48)).getdata())))
                media_samples.append(engine.media_stats())
                next_sample = time.monotonic() + 3
            if not video_visibility or video_visibility[-1] != visible:
                video_visibility.append(visible)
            for kind, stats in engine.media_stats().items():
                received[kind] |= stats['download_kbps'] > 0
                if kind == 'audio' and terminal.missing_video_visible and stats['download_kbps'] > 0:
                    audio_during_missing = True
        time.sleep(.02)
    assert connected and all(received.values()), ('Call/media failed',received)
    assert terminal.engine.incoming_video_active() and not terminal.missing_video_visible, ('Message obscured incoming video', video_visibility, terminal.engine._last_video_frame, terminal.model.state)
    if args.video_cycle:
        assert video_visibility == [False, True, False, True], ('Missing-video transitions failed', video_visibility)
        assert audio_during_missing, 'Audio did not continue while video was absent'
    if sys.platform == 'win32':
        renderer = terminal.engine._preloaded[-1]
        renderer.family_renderer_frames.restype = C.c_long
        renderer.family_renderer_coloured_frames.restype = C.c_long
        frames = renderer.family_renderer_frames()
        coloured_frames = renderer.family_renderer_coloured_frames()
        assert frames > 5 and coloured_frames > 0, ('Native renderer did not draw video', frames, coloured_frames)
    else:
        from PIL import ImageGrab
        window = terminal.video
        x, y = window.winfo_rootx(), window.winfo_rooty()
        image = ImageGrab.grab(bbox=(x, y, x + window.winfo_width(), y + window.winfo_height()))
        image.save(ROOT / 'data/linux-video.png')
        colors = len(set(image.resize((64, 48)).getdata()))
        assert colors > 8, ('Linux embedded video surface is blank', colors)
        assert len(video_samples) >= 2, ('Too few video samples', video_samples)
        if not args.video_cycle:
            # An intentional stream restart may briefly clear the native
            # surface before its first frame. The cycle test verifies the
            # missing-video transitions and the final recovered picture above.
            assert all(count > 8 for count in video_samples[1:]), ('Video became blank during call', video_samples)
        frames, coloured_frames = None, colors
    terminal.press('red')
    end = time.monotonic() + 3
    while terminal.model.state != State.HOME and time.monotonic() < end:
        terminal.root.update()
        time.sleep(.02)
    assert terminal.model.state == State.HOME, 'RED did not end the call'
    (ROOT/'data/ui-call-result.json').write_text(json.dumps({'connected':connected,'received_media':received,
        'rendered_frames':frames,'coloured_frames':coloured_frames,'red_returns_home':True,
        'video_visibility':video_visibility,'audio_during_missing_video':audio_during_missing,
        'video_samples':video_samples, 'media_samples':media_samples}))
    print('Terminal UI: answered, received audio/video, drew video frames, RED returned home.', frames, coloured_frames)
    if args.video_cycle:
        print('Confirmed outgoing call: no video / video / no video / video; audio continued throughout.')
finally:
    terminal.close()
