"""Collect ten user downloads plus two signed machine-update assets."""
import argparse
import json
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[2]
LEAFLETS = 'ZmalaTerminal-Leaflets.zip'
ASSETS = (
    'ZmalaTerminal-Installation.pdf', 'ZmalaTerminal-Guide.pdf',
    'ZmalaTerminal-Pi4-setup.exe', 'ZmalaServer-Installation.pdf',
    'ZmalaServer-Guide.pdf', 'ZmalaServer-Pi4-setup.exe',
    'ZmalaPhone-Installation.pdf', 'ZmalaPhone-Guide.pdf', 'ZmalaPhone.apk',
    LEAFLETS,
    'ZmalaTerminal-Update.tar.gz', 'ZmalaTerminal-Update.json',
)


def validate_leaflet_bundle(path):
    """Accept only both PDF layouts for every terminal locale and printing notes."""
    languages = json.loads((ROOT / 'zmala_terminal/common/shared/terminal-languages.json').read_text(encoding='utf-8'))
    expected = {'PRINTING.txt'} | {
        f'ZmalaTerminal-Leaflet-{code}{suffix}.pdf'
        for code in languages for suffix in ('', '-A4')}
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if len(names) != len(expected) or set(names) != expected:
                raise ValueError('Leaflet bundle must contain exactly all language PDFs and PRINTING.txt')
            for item in archive.infolist():
                if not item.file_size or item.flag_bits & 1:
                    raise ValueError('Leaflet bundle contains an empty or encrypted entry')
                if item.filename.endswith('.pdf'):
                    with archive.open(item) as stream:
                        if stream.read(4) != b'%PDF':
                            raise ValueError('Leaflet bundle contains an invalid PDF')
            if archive.testzip() is not None:
                raise ValueError('Leaflet bundle integrity check failed')
    except (zipfile.BadZipFile, OSError, RuntimeError, EOFError) as error:
        raise ValueError('Invalid leaflet bundle') from error


def collect(dist, apk, output):
    if output.exists():
        raise ValueError('Use a new empty destination; never merge with old release assets')
    if apk.is_dir():
        candidates = list(apk.rglob('ZmalaPhone.apk'))
        if len(candidates) != 1 or candidates[0].is_symlink():
            raise ValueError('Android artifact must contain exactly one ZmalaPhone.apk')
        apk = candidates[0]
    sources = {name: apk if name.endswith('.apk') else
               dist / 'guides' / name if name.endswith('.pdf') else
               dist / 'leaflets' / name if name == LEAFLETS else dist / name for name in ASSETS}
    for name, source in sources.items():
        if not source.is_file() or source.stat().st_size == 0:
            raise ValueError('Missing release input: ' + name)
        signature = source.read_bytes()[:4]
        expected = (b'%PDF' if name.endswith('.pdf') else b'MZ' if name.endswith('.exe') else
                    b'\x1f\x8b' if name.endswith('.tar.gz') else b'{' if name.endswith('.json') else b'PK')
        if not signature.startswith(expected):
            raise ValueError('Invalid release input: ' + name)
    validate_leaflet_bundle(sources[LEAFLETS])
    output.mkdir(parents=True)
    for name, source in sources.items():
        shutil.copy2(source, output / name)
    return list(ASSETS)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist', type=Path, default=ROOT / 'build_tools/dist')
    parser.add_argument('--apk', type=Path, required=True,
                        help='Verified APK or downloaded Android artifact directory containing exactly one APK')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    for name in collect(args.dist, args.apk, args.output):
        print(name)


if __name__ == '__main__':
    main()
