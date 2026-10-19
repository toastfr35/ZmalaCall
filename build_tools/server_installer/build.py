"""Build the standalone Windows server setup executable."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def main():
    if sys.platform != 'win32':
        raise SystemExit('Build on Windows with Python and Tk.')
    subprocess.run([sys.executable, str(ROOT/'build_tools/linux/package-server.py')], check=True)
    destination = ROOT/'build_tools/dist'
    work = ROOT/'build_tools/tmp/server-installer-build'
    work.mkdir(parents=True, exist_ok=True)
    args = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--windowed',
            '--name', 'ZmalaServer-Pi4-setup', '--paths', str(ROOT), '--distpath', str(destination),
            '--workpath', str(work/'work'), '--specpath', str(work)]
    for path in (destination/'ZmalaCall-Server-rpi.tar.gz', destination/'ZmalaCall-Server-rpi.tar.gz.sha256',
                 ROOT/'build_tools/windows_installer/remote_probe.py', ROOT/'zmala_terminal/common/assets/zmala-icon.png'):
        args += ['--add-data', str(path)+':.']
    subprocess.run(args+[str(Path(__file__).with_name('entrypoint.py'))], check=True)


if __name__ == '__main__':
    main()
