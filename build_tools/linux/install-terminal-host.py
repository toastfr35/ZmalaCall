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
    'argon_fan.py': 'zmala_terminal/linux/argon_fan.py',
}


def sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def copy_root_file(original, target, mode):
    if original.is_symlink() or not original.is_file():
        raise ValueError('Missing regular host helper: '+str(original))
    target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    temporary = target.with_name(target.name+'.next')
    temporary.unlink(missing_ok=True)
    with original.open('rb') as input_stream, temporary.open('xb') as output:
        shutil.copyfileobj(input_stream, output)
        output.flush()
        os.fchmod(output.fileno(), mode)
        os.fchown(output.fileno(), 0, 0)
        os.fsync(output.fileno())
    os.replace(temporary, target)
    sync_directory(target.parent)


def install(source, layout=Path('/')):
    if os.geteuid() != 0:
        raise PermissionError('Host helper installation requires root')
    destination = layout/'usr/local/lib/zmalacall-terminal-host'
    destination.mkdir(mode=0o755, parents=True, exist_ok=True)
    if destination.is_symlink():
        raise ValueError('Host helper directory must not be a symlink')
    destination.chmod(0o755)
    for name, relative in FILES.items():
        copy_root_file(source/relative, destination/name, 0o644)
    helper = layout/'usr/local/libexec/zmala-usb-power'
    copy_root_file(source/'build_tools/linux/usb-power.py', helper, 0o755)
    dropin = layout/'etc/systemd/system/zmalacall-terminal.service.d/usb-power.conf'
    if dropin.is_symlink():
        raise ValueError('USB cleanup drop-in must not be a symlink')
    if dropin.is_file():
        value = dropin.read_text()
        old = 'ExecStopPost=+/usr/local/libexec/zmala-usb-power on'
        new = 'ExecStopPost=+/usr/local/libexec/zmala-usb-power restore'
        if old not in value and new not in value:
            raise ValueError('Unrecognized USB cleanup policy needs manual review')
        temporary = dropin.with_suffix('.next')
        temporary.write_text(value.replace(old, new))
        temporary.chmod(0o644)
        with temporary.open('rb') as stream:
            os.fsync(stream.fileno())
        os.replace(temporary, dropin)
        sync_directory(dropin.parent)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    install(args.source)
