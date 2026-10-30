"""Exercise any bundled TV plugin and save photographed, offline HTML evidence."""
import argparse
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from build_tools.tv_plugin_self_test import package_report, run_sequence  # noqa: E402
from zmala_terminal.linux.tv_plugins import DRIVERS, load_driver  # noqa: E402

METHODS = {'get_model', 'get_capabilities', 'get_power_status', 'set_power_on',
           'set_power_off', 'get_current_input', 'set_current_input'}


def worker(args):
    """One isolated operation; the parent enforces an overall wall-clock limit."""
    logging.disable(logging.CRITICAL)
    try:
        from zmala_terminal.linux.tv_control import TVControl
        controller = TVControl(device=args.cec_device)
        config = {'read_power': controller._driver_power_status,
                  'read_input': controller._previous_source,
                  'power_on': controller._driver_power_on}
        if args.config:
            config['config_file'] = args.config
        driver = load_driver(args.driver, config)
        method, values = json.loads(args.worker)
        if method not in METHODS:
            raise ValueError('Unknown test method')
        value = getattr(driver, method)(*values)
        if method == 'get_capabilities':
            value = sorted(set(value) & (METHODS - {'get_model', 'get_capabilities'}))
        elif method in ('get_model', 'get_current_input'):
            if value is not None and (not isinstance(value, str) or len(value) > 256):
                raise ValueError('Invalid observation')
        elif value is not None and not isinstance(value, bool):
            raise ValueError('Invalid result')
        result = {'status': 'returned', 'value': value}
    except NotImplementedError:
        result = {'status': 'unsupported', 'value': None}
    except Exception as error:
        result = {'status': 'error', 'error': type(error).__name__, 'value': None}
    print(json.dumps(result))


def capture(args):
    """A separate camera process prevents a stalled USB read hanging the test."""
    import cv2
    camera = cv2.VideoCapture(args.camera, cv2.CAP_V4L2)
    try:
        camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        for _ in range(15):
            ok, frame = camera.read()
        if not ok or not cv2.imwrite(args.capture, frame):
            raise RuntimeError('Camera capture failed')
    finally:
        camera.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--driver', choices=sorted(DRIVERS), default='samsung')
    parser.add_argument('--config', help='Private plugin config path; never copied into the report')
    parser.add_argument('--cec-device', help='Optional CEC adapter; otherwise detect connected output')
    parser.add_argument('--camera', default='/dev/video0')
    parser.add_argument('--input', action='append', default=[], help='Restorable plugin input ID; repeat in test order')
    parser.add_argument('--delay', type=float, default=4)
    parser.add_argument('--timeout', type=float, default=20)
    parser.add_argument('--output', type=Path, help='New ZIP filename; existing files are never overwritten')
    parser.add_argument('--operate-tv', action='store_true', help='Explicitly permit power and source changes')
    parser.add_argument('--pause-terminal', action='store_true', help='Pause terminal/C20 ownership, then restart it')
    parser.add_argument('--worker', help=argparse.SUPPRESS)
    parser.add_argument('--capture', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        worker(args)
        return 0
    if args.capture:
        capture(args)
        return 0
    if not args.operate_tv or not args.output:
        parser.error('--operate-tv and --output are required; run only while no call is active')
    if not (0 <= args.delay <= 30 and 1 <= args.timeout <= 60):
        parser.error('delay must be 0..30 seconds and timeout 1..60 seconds')
    if args.output.exists():
        parser.error('output already exists')
    os.umask(0o077)
    active = subprocess.run(['systemctl', 'is-active', '--quiet', 'zmalacall-terminal'], check=False).returncode == 0
    if active and not args.pause_terminal:
        parser.error('terminal is active; use --pause-terminal during an idle maintenance window')
    paused = False
    report = None
    try:
        if active:
            subprocess.run(['sudo', '-n', 'systemctl', 'stop', 'zmalacall-terminal'], check=True, timeout=30)
            paused = True
        subprocess.run(['sudo', '-n', '/usr/local/libexec/zmala-usb-power', 'on'], check=True, timeout=45)
        with tempfile.TemporaryDirectory(prefix='zmala-tv-test-') as temporary:
            folder = Path(temporary)
            command = [sys.executable, str(Path(__file__).resolve()), '--driver', args.driver]
            for flag, value in [('--config', args.config), ('--cec-device', args.cec_device)]:
                if value:
                    command.extend([flag, value])

            def invoke(method, values):
                try:
                    result = subprocess.run(command + ['--worker', json.dumps([method, values])],
                                            capture_output=True, text=True, timeout=args.timeout, check=True)
                    # Never copy third-party stdout/stderr into evidence: they may contain credentials.
                    return json.loads(result.stdout.splitlines()[-1])
                except subprocess.TimeoutExpired:
                    return {'status': 'timeout', 'value': None}
                except Exception as error:
                    return {'status': 'error', 'error': type(error).__name__, 'value': None}

            def snapshot(index):
                name = f'photo-{index:02d}.jpg'
                subprocess.run(command + ['--camera', args.camera, '--capture', str(folder / name)],
                               capture_output=True, timeout=20, check=True)
                print(f'Captured step {index}', flush=True)
                return name

            report = run_sequence(invoke, snapshot, args.input, args.delay)
            report['driver'] = args.driver
            report['terminal_service_paused'] = paused
            package_report(report, folder, args.output)
            print('Evidence ZIP:', args.output, flush=True)
    finally:
        if paused:
            subprocess.run(['sudo', '-n', 'systemctl', 'start', 'zmalacall-terminal'], check=True, timeout=30)
    return 0 if report and report.get('sequence_status', '').startswith('Sequence finished') else 1


if __name__ == '__main__':
    raise SystemExit(main())
