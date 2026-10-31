"""Bounded helper lifetimes and recovery for the opt-in TV evidence tool."""
import subprocess
import time


def wait_for_file(path, process, timeout):
    """Fail if the camera exits or stops delivering frames."""
    deadline = time.monotonic() + timeout
    while not path.exists():
        if process.poll() is not None:
            raise RuntimeError('Camera process exited')
        if time.monotonic() >= deadline:
            raise TimeoutError('Camera observation timed out')
        time.sleep(.01)


def stop_process(process):
    """Reap exited children; bound both graceful and forced termination."""
    if process is None:
        return
    if process.poll() is not None:
        process.wait(timeout=0)
        return
    try:
        process.terminate()
    except ProcessLookupError:
        pass  # It may have exited between poll and terminate.
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def cleanup(camera, card, paused):
    """Attempt every cleanup action even if one child refuses to exit.

    Restarting the terminal must not depend on camera/card cleanup succeeding.
    Only exception types escape: subprocess diagnostics may contain private data.
    """
    errors = []
    for name, process in [('camera', camera), ('test card', card)]:
        try:
            stop_process(process)
        except (Exception, KeyboardInterrupt) as error:
            errors.append(name + ': ' + type(error).__name__)
    if paused:
        try:
            subprocess.run(['sudo', '-n', 'systemctl', 'start', 'zmalacall-terminal'],
                           check=True, timeout=30)
        except (Exception, KeyboardInterrupt) as error:
            errors.append('terminal restart: ' + type(error).__name__)
    if errors:
        raise RuntimeError('TV test cleanup incomplete: ' + '; '.join(errors))
