"""Standalone Linux codec benchmark; it does not change terminal configuration.

Requires FFmpeg. --camera /dev/video0 needs exclusive camera access: stop the
terminal before running it, then restart it afterwards. Temporary raw camera
frames and encoded samples are deleted automatically. Only timings/logs remain
in the requested JSON report. This measures throughput, not call latency or
equivalent perceptual quality between codecs.
"""
import argparse
import json
from pathlib import Path
import resource
import subprocess
import tempfile
import time


def measure(arguments):
    """Count child CPU time separately from elapsed time and retain device logs."""
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    started = time.monotonic()
    try:
        process = subprocess.run(
            ['ffmpeg', '-hide_banner', '-nostdin', '-y', *arguments],
            capture_output=True, text=True, timeout=90)
        code, log = process.returncode, process.stderr
    except subprocess.TimeoutExpired:
        code, log = 124, 'Timed out after 90 seconds'
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    return {'exit_code': code, 'elapsed_seconds': round(time.monotonic() - started, 3),
            'cpu_seconds': round(after.ru_utime + after.ru_stime
                                 - before.ru_utime - before.ru_stime, 3),
            'log': log[-6000:]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--camera', help='Optional V4L2 camera, e.g. /dev/video0')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = {'size': '640x480', 'fps': 15, 'frames': 150, 'camera': args.camera,
              'ffmpeg_version': subprocess.check_output(
                  ['ffmpeg', '-version'], text=True).splitlines()[0], 'tests': {}}
    with tempfile.TemporaryDirectory(prefix='zmala-codec-') as directory:
        root = Path(directory)
        raw = root / 'camera.yuv'
        source = (['-f', 'v4l2', '-input_format', 'yuyv422', '-video_size', '640x480',
                   '-framerate', '30', '-i', args.camera, '-vf', 'fps=15']
                  if args.camera else
                  ['-f', 'lavfi', '-i', 'testsrc2=size=640x480:rate=15'])
        report['capture'] = measure([*source, '-frames:v', '150', '-pix_fmt', 'yuv420p',
                                     '-f', 'rawvideo', str(raw)])
        if report['capture']['exit_code'] == 0:
            input_args = ['-f', 'rawvideo', '-pix_fmt', 'yuv420p', '-video_size', '640x480',
                          '-framerate', '15', '-i', str(raw)]
            for codec, options, extension in [
                # The generic V4L2 encoder accepts numeric AV_PROFILE_H264_BASELINE
                # (66), rather than libx264's string spelling "baseline".
                ('h264_v4l2m2m', ['-g', '30', '-bf', '0', '-profile:v', '66'], 'h264'),
                ('libx264', ['-preset', 'ultrafast', '-tune', 'zerolatency', '-g', '30'], 'h264'),
                ('libvpx', ['-deadline', 'realtime', '-cpu-used', '8', '-threads', '4', '-g', '30'], 'ivf'),
                ('vp8_v4l2m2m', ['-g', '30'], 'ivf')]:
                sample = root / (codec + '.' + extension)
                report['tests']['encode_' + codec] = measure([
                    *input_args, '-an', '-c:v', codec, '-b:v', '500k', *options, str(sample)])
            hardware_sample = root / 'h264_v4l2m2m.h264'
            if report['tests']['encode_h264_v4l2m2m']['exit_code'] == 0:
                for codec in ['h264_v4l2m2m', 'h264']:
                    # framehash consumes decoded pixels; a successful open alone
                    # would not prove that the hardware delivered usable frames.
                    hashes = root / (codec + '.hash')
                    result = measure(['-c:v', codec, '-i', str(hardware_sample), '-an',
                                      '-pix_fmt', 'yuv420p', '-f', 'framehash', str(hashes)])
                    result['decoded_frames'] = (sum(not line.startswith('#') and bool(line.strip())
                        for line in hashes.read_text().splitlines()) if hashes.exists() else 0)
                    report['tests']['decode_' + codec] = result
            vp8_sample = root / 'libvpx.ivf'
            if report['tests']['encode_libvpx']['exit_code'] == 0:
                result = measure(['-c:v', 'vp8', '-i', str(vp8_sample), '-an',
                                  '-pix_fmt', 'yuv420p', '-f', 'framehash', str(root / 'vp8.hash')])
                result['decoded_frames'] = (sum(not line.startswith('#') and bool(line.strip())
                    for line in (root / 'vp8.hash').read_text().splitlines())
                    if (root / 'vp8.hash').exists() else 0)
                report['tests']['decode_vp8'] = result
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    for name, result in report['tests'].items():
        print(name, {key: value for key, value in result.items() if key != 'log'})
    if report['capture']['exit_code']:
        raise SystemExit('Capture failed; see the report.')


if __name__ == '__main__':
    main()
