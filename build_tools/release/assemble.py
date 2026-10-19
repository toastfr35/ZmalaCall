"""Collect exactly the nine user downloads; keep private QA/source files outside."""
import argparse
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]
ASSETS = (
    'ZmalaTerminal-Installation.pdf', 'ZmalaTerminal-Guide.pdf',
    'ZmalaTerminal-Pi4-setup.exe', 'ZmalaServer-Installation.pdf',
    'ZmalaServer-Guide.pdf', 'ZmalaServer-Pi4-setup.exe',
    'ZmalaPhone-Installation.pdf', 'ZmalaPhone-Guide.pdf', 'ZmalaPhone.apk',
)


def collect(dist, apk, output):
    if output.exists():
        raise ValueError('Use a new empty destination; never merge with old release assets')
    sources = {name: apk if name.endswith('.apk') else
               dist / 'guides' / name if name.endswith('.pdf') else dist / name for name in ASSETS}
    for name, source in sources.items():
        if not source.is_file() or source.stat().st_size == 0:
            raise ValueError('Missing release input: ' + name)
        signature = source.read_bytes()[:4]
        expected = b'%PDF' if name.endswith('.pdf') else b'MZ' if name.endswith('.exe') else b'PK'
        if not signature.startswith(expected):
            raise ValueError('Invalid release input: ' + name)
    output.mkdir(parents=True)
    for name, source in sources.items():
        shutil.copy2(source, output / name)
    return list(ASSETS)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist', type=Path, default=ROOT / 'build_tools/dist')
    parser.add_argument('--apk', type=Path, required=True,
                        help='APK already verified by build_tools/android/release.py')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    for name in collect(args.dist, args.apk, args.output):
        print(name)


if __name__ == '__main__':
    main()
