"""Build a single Windows EXE containing Python, SSH and the Pi package."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def main():
    if sys.platform != 'win32':
        raise SystemExit('Build the installer on Windows using Python with Tk support.')
    subprocess.run([sys.executable, str(ROOT / 'build_tools/linux/package-terminal.py')], check=True)
    destination = ROOT / 'build_tools/dist'
    work = ROOT / 'build_tools/tmp/windows-installer-build'
    work.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--windowed',
                    '--name', 'zmala_terminal_setup', '--distpath', str(destination),
                    '--workpath', str(work / 'work'), '--specpath', str(work),
                    '--add-data', str(destination / 'ZmalaCall-Terminal-rpi.tar.gz') + ':.',
                    '--add-data', str(destination / 'ZmalaCall-Terminal-rpi.tar.gz.sha256') + ':.',
                    '--add-data', str(Path(__file__).with_name('remote_probe.py')) + ':.',
                    '--add-data', str(ROOT / 'zmala_terminal/common/assets/zmala-icon.png') + ':.',
                    str(Path(__file__).with_name('entrypoint.py'))], check=True)
    print(destination / 'zmala_terminal_setup.exe')


if __name__ == '__main__':
    main()
