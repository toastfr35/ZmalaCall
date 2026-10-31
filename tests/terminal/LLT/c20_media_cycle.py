# @test T-LLT-082
# @requirements LLR-TERM-AUDIO-003, LLR-TERM-VIDEO-019
# @environment hardware
# @plan On an installed Pi with the terminal service stopped and its selected C10 or C20 host policy loaded, repeatedly open three-second 16 kHz stereo capture and 48 kHz stereo silent playback. Require the microphone PCM to remain RUNNING for 750 ms before opening 1080p MJPEG capture, with a five-second readiness deadline. Close all streams between cycles. Require successful processes, the expected microphone byte count and complete JPEG data. Retain aggregate results privately. This checks the physical staged-startup sequence, not acoustic quality, H.264, network calls or indefinite reliability; native boundary tests separately exercise the production worker's gate.
# @pass Every requested cycle completes without a command timeout, audio parameter failure or video streaming failure and produces the expected data. A skipped/unavailable device is not a passed run.
"""Explicit hardware qualification; never selected by portable unittest discovery."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time


def cycle(video, directory, environment, model="C20"):
    audio, picture = directory/'capture.raw', directory/'capture.mjpg'
    commands = [
        ['arecord', '-q', '-D', 'default:'+model, '-t', 'raw', '-f', 'S16_LE', '-c', '2', '-r', '16000', '-d', '3', str(audio)],
        ['aplay', '-q', '-D', 'default:'+model, '-f', 'S16_LE', '-c', '2', '-r', '48000', '-d', '3', '/dev/zero'],
        ['v4l2-ctl', '-d', str(video), '--set-fmt-video=width=1920,height=1080,pixelformat=MJPG',
         '--stream-mmap', '--stream-count=30', '--stream-to='+str(picture)],
    ]
    processes = []
    try:
        for command in commands[:2]:
            processes.append(subprocess.Popen(command, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE))
        deadline, stable = time.monotonic()+5, None
        while True:
            now = time.monotonic()
            assert now < deadline and processes[0].poll() is None, 'Microphone did not remain ready'
            status = (Path('/proc/asound')/model/'pcm0c/sub0/status').read_text()
            if 'state: RUNNING' in status:
                stable = now if stable is None else stable
                if now-stable >= .75:
                    break
            else:
                stable = None
            time.sleep(.02)
        processes.append(subprocess.Popen(commands[2], env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE))
        results = []
        for process in processes:
            _, errors = process.communicate(timeout=15)
            results.append({'code': process.returncode, 'errors': errors.decode(errors='replace')[-1200:]})
        assert all(result['code'] == 0 for result in results), results
        assert audio.stat().st_size == 3*16000*2*2, 'Incomplete microphone capture'
        jpeg = picture.read_bytes()
        assert jpeg.startswith(b'\xff\xd8') and b'\xff\xd9' in jpeg, 'No complete MJPEG frame'
        return {'microphone_bytes': audio.stat().st_size, 'mjpeg_bytes': len(jpeg)}
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass  # The failed run requires USB recovery; do not claim cleanup passed.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', choices=('C10', 'C20'), default='C20')
    parser.add_argument('--cycles', type=int, default=30)
    parser.add_argument('--alsa-policy', type=Path, default=Path(__file__).resolve().parents[3]/'zmala_terminal/linux/media/audio/c20-alsa.conf')
    parser.add_argument('--output', type=Path, required=True, help='Private aggregate results, outside the source tree')
    args = parser.parse_args()
    if not 1 <= args.cycles <= 200:
        parser.error('--cycles must be between 1 and 200')
    state = subprocess.check_output(['systemctl', 'show', '--value', '-p', 'ActiveState',
                                     'zmalacall-terminal.service'], text=True).strip()
    assert state in ('inactive', 'failed'), 'Stop the terminal service before this hardware test'
    assert args.alsa_policy.is_file(), 'Missing C20 ALSA policy'
    nodes = [Path('/dev')/entry.name for entry in sorted(Path('/sys/class/video4linux').glob('video*'))
             if ('nuroum '+args.model.lower()) in (entry/'name').read_text().lower()]
    video = next((node for node in nodes if b'MJPG' in subprocess.check_output(
        ['v4l2-ctl', '-d', str(node), '--list-formats'])), None)
    assert video is not None, 'No C20 MJPEG camera'
    assert any(path.read_text().strip() == args.model for path in Path('/proc/asound').glob('card*/id')), 'No C20 sound card'
    environment = dict(os.environ, ALSA_CONFIG_PATH=str(args.alsa_policy.resolve()))
    results = []
    try:
        with tempfile.TemporaryDirectory(prefix='zmala-c20-cycle-') as folder:
            for index in range(args.cycles):
                results.append(cycle(video, Path(folder), environment, args.model))
                print(f'{args.model} media cycle {index+1}/{args.cycles} passed', flush=True)
                time.sleep(.3)
    finally:
        args.output.write_text(json.dumps({'requested': args.cycles, 'completed': len(results),
                                          'cycles': results}, indent=2))


if __name__ == '__main__':
    main()
