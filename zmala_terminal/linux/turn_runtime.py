"""Load only the TURN correction built for the installed distro SDK version."""
import os
from pathlib import Path
import subprocess
import sys


# @llr LLR-TERM-COM-010
def prepare():
    directory = Path(__file__).resolve().with_name('turn-runtime')
    library = directory / 'turn-fix.so'
    if not library.exists():
        return  # LAN operation remains possible without the optional correction.
    version = subprocess.check_output(
        ['dpkg-query', '-W', '-f=${Version}', 'libmediastreamer2-14'], text=True, timeout=5)
    if version != (directory / 'sdk-version').read_text():
        raise RuntimeError('SDK version changed; rebuild the TURN correction before starting')
    loaded = str(library) in Path('/proc/self/maps').read_text()
    if not loaded:
        environment = dict(os.environ)
        environment['LD_PRELOAD'] = str(library)
        os.execve(sys.executable, [sys.executable, *sys.argv], environment)


def require_loaded():
    if 'turn-fix.so' not in Path('/proc/self/maps').read_text():
        raise RuntimeError('Secure calls require the tested TURN SDK correction; run the terminal installer')
