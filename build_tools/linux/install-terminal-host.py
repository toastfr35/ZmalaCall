"""Install boot helpers outside replaceable application slots (manual installer only)."""
import argparse
import os
from pathlib import Path
import shutil

FILES = {
    'prepare-display.py': 'build_tools/linux/prepare-display.py',
    'pair-presenter.py': 'build_tools/linux/pair-presenter.py',
    'picom.conf': 'build_tools/linux/picom.conf',
    'cec_observer.py': 'zmala_terminal/linux/cec_observer.py',
    'cec_device.py': 'zmala_terminal/linux/cec_device.py',
}


def install(source, layout=Path('/')):
    if os.geteuid() != 0:
        raise PermissionError('Host helper installation requires root')
    destination = layout/'usr/local/lib/zmalacall-terminal-host'
    destination.mkdir(mode=0o755, parents=True, exist_ok=True)
    if destination.is_symlink():
        raise ValueError('Host helper directory must not be a symlink')
    destination.chmod(0o755)
    for name, relative in FILES.items():
        original = source/relative
        if original.is_symlink() or not original.is_file():
            raise ValueError('Missing regular host helper: '+relative)
        temporary = destination/(name+'.next')
        temporary.unlink(missing_ok=True)
        with original.open('rb') as input_stream, temporary.open('xb') as output:
            shutil.copyfileobj(input_stream, output)
            output.flush()
            os.fchmod(output.fileno(), 0o644)
            os.fchown(output.fileno(), 0, 0)
            os.fsync(output.fileno())
        os.replace(temporary, destination/name)
    descriptor = os.open(destination, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    install(args.source)
