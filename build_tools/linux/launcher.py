"""Per-profile Linux launch/stop with a lock and PID-reuse protection."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import runpy
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
TERMINAL = ROOT / 'zmala_terminal/common/main.py'


def start_time(pid):
    # comm can contain spaces and parentheses: fields follow its final ')'.
    return Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[19]


# @llr TLLR005
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['start', 'stop', 'run'])
    parser.add_argument('--profile', default='terminal')
    args, forwarded = parser.parse_known_args()
    import re
    if not re.fullmatch(r'[a-z][a-z0-9_-]{0,40}', args.profile):
        parser.error('Invalid terminal profile')
    os.umask(0o077)
    data = ROOT / 'zmala_terminal/data'
    data.mkdir(parents=True, exist_ok=True)
    runtime = Path(os.environ.get('ZMALA_RUNTIME_DIR', str(data)))
    runtime.mkdir(parents=True, exist_ok=True)
    record = runtime / f'{args.profile}.pid.json'
    if args.action == 'stop':
        if not record.exists():
            print('Terminal is stopped.'); return
        value = json.loads(record.read_text())
        pid = value['pid']
        try:
            if start_time(pid) != value['started']:
                raise ProcessLookupError()
            command = Path(f'/proc/{pid}/cmdline').read_bytes()
            if str(Path(__file__).resolve()).encode() not in command or b'run' not in command.split(b'\0'):
                raise RuntimeError('PID belongs to a different process; refusing to stop it')
            os.killpg(pid, signal.SIGTERM)
            for _ in range(50):
                time.sleep(.1)
                stat = Path(f'/proc/{pid}/stat')
                if not stat.exists() or stat.read_text().rsplit(')', 1)[1].split()[0] == 'Z':
                    break
            else:
                if start_time(pid) == value['started']:
                    os.killpg(pid, signal.SIGKILL)
        except (FileNotFoundError, ProcessLookupError):
            pass
        record.unlink(missing_ok=True)
        print('Terminal stopped.'); return
    if args.action == 'start':
        if not os.environ.get('DISPLAY'):
            parser.error('Run from an X11/XWayland desktop session (DISPLAY is missing)')
        with (runtime / f'{args.profile}-startup.log').open('ab', buffering=0) as log:
            process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), 'run',
                '--profile', args.profile, *forwarded], cwd=ROOT, stdin=subprocess.DEVNULL,
                stdout=log, stderr=log, start_new_session=True)
        time.sleep(1)
        if process.poll() is not None:
            parser.error(f'Startup failed; read {runtime / (args.profile + "-startup.log")}')
        print(f'Terminal started (PID {process.pid}, profile {args.profile}).'); return
    with (runtime / f'{args.profile}.lock').open('a') as lock:
        # The running supervisor owns this descriptor for its entire lifetime.
        # A second launcher can start, but cannot run another app for this profile.
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.error('This terminal profile is already running')
        record.write_text(json.dumps({'pid': os.getpid(), 'started': start_time(os.getpid())}))
        def stop(signum, frame):
            raise KeyboardInterrupt()
        signal.signal(signal.SIGTERM, stop)
        sys.path.insert(0, str(ROOT))
        sys.argv = [str(TERMINAL), '--profile', args.profile, *forwarded]
        try:
            runpy.run_path(str(TERMINAL), run_name='__main__')
        except KeyboardInterrupt:
            pass
        finally:
            record.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
