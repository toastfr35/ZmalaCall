"""Opt-in Windows receiver check against an idle, auto-answering Pi terminal.

Run with both terminals idle. Defaults to static outgoing video and file audio;
--camera selects the PC webcam and --synthetic uses a moving SDK test pattern.
An explicit --snapshot saves one received frame for visual verification.
--check-audio measures decoded PCM and deletes the temporary recording.
"""
import argparse
import array
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import time
import wave

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT.parent))
from zmala_terminal.common.configuration import Configuration
from zmala_terminal.common.engine import Engine, P, I, SDK, encoded, S


def decoded_audio_report(path):
    """Measure decoded PCM, not RTP traffic; never retain the room recording."""
    with wave.open(str(path), 'rb') as recording:
        if recording.getsampwidth() != 2:
            raise ValueError('Audio probe requires 16-bit PCM')
        samples = array.array('h', recording.readframes(recording.getnframes()))
        if sys.byteorder != 'little':
            samples.byteswap()
        count = len(samples)
        return {'seconds': recording.getnframes()/recording.getframerate(),
                'sample_rate': recording.getframerate(), 'channels': recording.getnchannels(),
                'nonzero_samples': sum(value != 0 for value in samples),
                'rms': math.sqrt(sum(value*value for value in samples)/count)/32768 if count else 0,
                'peak': max((abs(value) for value in samples), default=0)/32768}


def minimum_received_fps(samples, minimum, direction='received'):
    """Ignore five startup samples, then require the chosen direction's floor.

    A static no-camera placeholder can produce regular decoded notifications
    at 1 fps. Those notifications alone do not establish usable camera video.
    Zero/missing/invalid measurements fail an explicitly requested frame floor.
    """
    if not minimum:
        return None, True
    rates = [sample.get('video', {}).get(direction+'_fps', 0) for sample in samples[5:]]
    # The C20 tops out at 30 fps; the SDK sometimes reports a bogus 100 fps.
    if len(rates) < 2 or any(not isinstance(rate, (int, float)) or not math.isfinite(rate) or not 0 <= rate <= 30
                             for rate in rates):
        return None, False
    lowest = min(rates)
    return lowest, lowest >= minimum


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', default='term2')
    parser.add_argument('--seconds', type=float, default=25)
    parser.add_argument('--min-fps', type=float, default=0, help='Required received fps after five startup samples')
    parser.add_argument('--output', type=Path, required=True)
    sources = parser.add_mutually_exclusive_group()
    sources.add_argument('--camera', action='store_true', help='Use the configured real webcam to test both directions')
    sources.add_argument('--synthetic', action='store_true', help='Use the SDK moving test pattern for a receive workload')
    parser.add_argument('--snapshot', type=Path, help='Save one received webcam frame after the call settles')
    parser.add_argument('--check-audio', action='store_true', help='Require decoded, nonzero received audio; retain scalar results only')
    args = parser.parse_args()
    if not math.isfinite(args.min_fps) or not 0 <= args.min_fps <= 30:
        parser.error('--min-fps must be between 0 and 30')
    args.output = args.output.resolve()
    if args.snapshot:
        # Engine loads the SDK from its own working directory on Windows.
        args.snapshot = args.snapshot.resolve()
    config = Configuration(cache=ROOT/'data/camera-feed-test-cache.json').fetch()
    moving = args.camera or args.synthetic
    if args.synthetic:
        # SDK test cameras are enabled by DEBUG=1. This opt-in fixture does not
        # alter the server profile or expose a synthetic camera in normal use.
        os.environ['DEBUG'] = '1'
        config['terminal_settings']['camera'] = 'Mire: Mire (synthetic moving picture)'
    elif not moving:
        config['terminal_settings'] = {'camera': 'StaticImage: Static picture'}
    states, decoded, stats = [], [], []
    engine = Engine(config, lambda call, state, *_: states.append(state),
                    lambda *_: None, profile='camera-feed-test')
    snapshot_requested = False
    if args.snapshot:
        snapshot = engine.dll.linphone_call_take_video_snapshot
        snapshot.argtypes, snapshot.restype = [P, S], I
    use_files = engine.dll.linphone_core_set_use_files
    use_files.argtypes, use_files.restype = [P, I], None
    # File mode also replaces the camera with a static picture. Keep normal
    # capture enabled when testing the real webcams in both directions.
    use_files(engine.core, int(not moving))
    if not moving and args.check_audio:
        # File playback writes decoded PCM to disk, never to a speaker. Measure
        # the incoming signal before the user's 0% listening-volume attenuation.
        engine.core_set_playback_gain_db(engine.core, 0)
    recording_folder = tempfile.TemporaryDirectory() if args.check_audio else None
    if recording_folder:
        record = engine.dll.linphone_core_set_record_file
        record.argtypes, record.restype = [P, S], None
        record(engine.core, encoded(Path(recording_folder.name)/'received.wav'))
    play = engine.dll.linphone_core_set_play_file
    play.argtypes, play.restype = [P, S], None
    if not moving:
        play(engine.core, encoded(SDK/'share/sounds/linphone/hello8000.wav'))
    else:
        # Reapply the selected device after changing the test core's media mode.
        engine.apply_settings(config.get('terminal_settings', {}))
        assert not engine.diagnostics()['camera'].startswith('StaticImage:'), 'Real webcam unavailable'
    started, connected, dialed, last_frame, last_sample = time.monotonic(), None, False, None, 0
    try:
        while time.monotonic()-started < args.seconds+20:
            engine.iterate()
            now = time.monotonic()
            if engine.registered and not dialed:
                engine.dial('sip:'+args.target+'@'+config['sip']['domain'])
                dialed = True
            if engine.call and engine.call_get_state(engine.call) == 8:
                connected = connected or now
                if engine._last_video_frame is not None and engine._last_video_frame != last_frame:
                    last_frame = engine._last_video_frame
                    decoded.append(round(now-connected, 3))
                if now-last_sample >= 1:
                    stats.append(engine.media_stats())
                    last_sample = now
                if args.snapshot and not snapshot_requested and decoded and now-connected >= 5:
                    # Capture the remote camera, not a screenshot of the receiver
                    # window: only the physical TV view proves input selection.
                    assert snapshot(engine.call, encoded(args.snapshot)) == 0, 'Snapshot request failed'
                    snapshot_requested = True
                if now-connected >= args.seconds:
                    break
            time.sleep(.01)
        gaps = [b-a for a, b in zip(decoded, decoded[1:])]
        elapsed = time.monotonic()-connected if connected else 0
        sustained = len(decoded) >= args.seconds/2 and decoded[-1] >= args.seconds-3 and max(gaps, default=99) < 3
        report = {'states': states, 'connected_seconds': round(elapsed, 2),
                  'decoded_frame_notifications': decoded, 'max_notification_gap': max(gaps, default=None),
                  'sustained_video': sustained, 'media_stats': stats}
        lowest, meets_floor = minimum_received_fps(stats, args.min_fps)
        sent_lowest, sent_meets_floor = minimum_received_fps(stats, args.min_fps, 'sent') if moving else (None, True)
        if args.min_fps:
            report.update(min_received_fps=lowest, meets_min_fps=meets_floor)
            if moving:
                report.update(min_sent_fps=sent_lowest, sent_meets_min_fps=sent_meets_floor)
        if args.snapshot:
            report['snapshot_saved'] = args.snapshot.is_file()
        # Preserve measurements even if a broken native media graph stalls
        # teardown. The runner's exit status still records a failed test.
        args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    finally:
        engine.end()
        until = time.monotonic()+2
        while time.monotonic() < until:
            engine.iterate()
            time.sleep(.02)
        engine.close()
    if recording_folder:
        try:
            report['decoded_audio'] = decoded_audio_report(Path(recording_folder.name)/'received.wav')
        except (OSError, ValueError, wave.Error) as error:
            report['decoded_audio'] = {'error': str(error), 'nonzero_samples': 0}
        finally:
            recording_folder.cleanup()
    args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({key: value for key, value in report.items() if key != 'media_stats'}))
    audio_ok = not args.check_audio or report['decoded_audio']['nonzero_samples'] > 0
    return 0 if sustained and meets_floor and sent_meets_floor and audio_ok and (not args.snapshot or report['snapshot_saved']) else 1


if __name__ == '__main__':
    sys.exit(main())
