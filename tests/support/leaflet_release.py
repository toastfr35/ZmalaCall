"""Small public leaflet ZIP fixtures for publishing-tool regressions."""
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def leaflet_entries():
    languages = json.loads((ROOT / 'zmala_terminal/common/shared/terminal-languages.json').read_text(encoding='utf-8'))
    return {'PRINTING.txt': b'Print A4 landscape, double-sided, short edge.'} | {
        f'ZmalaTerminal-Leaflet-{code}{suffix}.pdf': b'%PDF fixture'
        for code in languages for suffix in ('', '-A4')}


def write_leaflet_bundle(path, entries=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, 'w') as archive:
        for name, value in (leaflet_entries() if entries is None else entries).items():
            archive.writestr(name, value)
