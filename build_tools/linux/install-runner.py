"""Keep a private, live installation log and preserve installer failures."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time


def run_install(command, log_dir):
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix=time.strftime('install-%Y%m%d-%H%M%S-'),
                                suffix='.log', dir=log_dir)
    print(f'Installation log: {name}', flush=True)
    child = None
    result = 1
    with os.fdopen(fd, 'w', encoding='utf-8') as log:
        def report(message):
            log.write(message)
            log.flush()
            print(message, end='', flush=True)

        try:
            child = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, encoding='utf-8', errors='replace',
                                     env={**os.environ, 'ZMALA_INSTALL_LOG': name},
                                     start_new_session=True)
            for line in child.stdout:
                report(line)
            result = child.wait()
        except KeyboardInterrupt:
            report('\nInstallation interrupted.\n')
            result = 130
        except OSError as error:
            report(f'Installation error: {error}\n')
        finally:
            if child is not None:
                if child.poll() is None:
                    os.killpg(child.pid, signal.SIGTERM)
                    try:
                        child.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid, signal.SIGKILL)
                        child.wait()
                child.stdout.close()
        if result:
            report(f'\nINSTALLATION FAILED (exit {result}). Log: {name}\n'
                   'Resolve the error above and rerun the same install command.\n'
                   'Do not reflash or reset enrollment to retry. OS changes are not automatically rolled back.\n')
        else:
            report(f'\nInstaller completed successfully. Log: {name}\n')
    return result if result >= 0 else 128 - result


def interrupted(_signum, _frame):
    raise KeyboardInterrupt


if __name__ == '__main__':
    if os.geteuid() != 0:
        sys.exit('Run the installer with sudo.')
    for task_signal in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(task_signal, interrupted)
    script = Path(__file__).with_name('install-kiosk.sh')
    sys.exit(run_install(['sh', str(script), *sys.argv[1:]], '/var/log/zmalacall-install'))
