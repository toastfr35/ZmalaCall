"""Build the four-page terminal leaflet and multilingual release bundle."""
import argparse
import base64
import html
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'docs/leaflet'
FIELDS = {'title', 'blurb', 'scope', 'ready', 'connect', 'equipment', 'connections',
          'setup_title', 'setup_intro', 'setup', 'private', 'operate', 'controls', 'settings_title',
          'settings', 'help'}
LENGTHS = {'equipment': 3, 'connections': 4, 'setup': 5, 'controls': 4, 'settings': 3}


def load_catalogs(source=SOURCE, languages=None):
    """Require exact locale/key parity: never silently ship English fallback."""
    if languages is None:
        languages = json.loads((ROOT / 'zmala_terminal/common/shared/terminal-languages.json').read_text(encoding='utf-8'))
    files = {p.stem: p for p in (source / 'locales').glob('*.json')}
    if set(files) != set(languages):
        raise ValueError(f'Locale mismatch: missing={set(languages) - set(files)}, extra={set(files) - set(languages)}')
    result = {}
    for code, path in files.items():
        data = json.loads(path.read_text(encoding='utf-8'))
        if set(data) != FIELDS:
            raise ValueError(f'{code}: translation keys differ from schema')
        for key, value in data.items():
            if key in LENGTHS:
                if not isinstance(value, list) or len(value) != LENGTHS[key]:
                    raise ValueError(f'{code}/{key}: expected {LENGTHS[key]} items')
                if key != 'equipment' and any(not isinstance(row, list) or len(row) != 2 for row in value):
                    raise ValueError(f'{code}/{key}: expected title and body pairs')
                strings = value if key == 'equipment' else [s for row in value for s in row]
            else:
                strings = [value]
            if any(not isinstance(s, str) or not s.strip() for s in strings):
                raise ValueError(f'{code}/{key}: empty or non-text translation')
        result[code] = data
    return languages, result


def asset(name):
    path = (ROOT / 'docs/branding/PNG/a1-wordmark-light-1024.png'
            if name == 'official-logo.png' else SOURCE / 'assets' / name)
    mime = 'image/svg+xml' if path.suffix == '.svg' else 'image/png'
    return f'data:{mime};base64,' + base64.b64encode(path.read_bytes()).decode('ascii')


def render_html(code, info, copy):
    esc = html.escape
    def picture(name, class_name=''):
        return f'<img class="{class_name}" alt="" src="{asset(name)}">'

    def steps(key):
        return '<ol class="' + key + '">' + ''.join(
            f'<li><h3>{esc(title)}</h3><p>{esc(body)}</p></li>'
            for title, body in copy[key]) + '</ol>'

    def footer(page):
        return f'<footer><span>Zmala · {esc(info["native"])}</span><span dir="ltr">{page} / 4</span></footer>'

    css = (SOURCE / 'layout.css').read_text(encoding='utf-8')
    equipment = ''.join(f'<figure>{picture(name)}<figcaption>{esc(caption)}</figcaption></figure>'
                        for name, caption in zip(('case.svg', 'c10.svg', 'remote.svg'), copy['equipment']))
    return f'''<!doctype html>
<html lang="{esc(code)}" dir="{info['direction']}"><head><meta charset="utf-8">
<title>Zmala · {esc(copy['title'])}</title><style>{css}</style></head><body>
<section class="page cover"><main>
{picture('official-logo.png', 'brand')}
<h1>{esc(copy['title'])}</h1>
{picture('overview.png', 'hero')}
<p class="blurb">{esc(copy['blurb'])}</p>
<p>{esc(copy['scope'])}</p>
<p class="ready">{esc(copy['ready'])}</p>
</main>{footer(1)}</section>
<section class="page"><main>
<div class="eyebrow">01</div><h2>{esc(copy['connect'])}</h2>
<div class="equipment">{equipment}</div>
<div class="ports">{picture('ports.svg')}<div class="markers" dir="ltr">
<span style="left:59.5%">1</span><span style="left:41%">2</span>
<span style="left:8%">3</span><span style="left:25%">4</span>
</div></div>
{steps('connections')}
</main>{footer(2)}</section>
<section class="page"><main>
<div class="eyebrow">02</div><h2>{esc(copy['setup_title'])}</h2>
<p class="setup-intro">{esc(copy['setup_intro'])}</p>
{picture('remote-back.svg', 'pairing')}
{steps('setup')}
<p class="private">{esc(copy['private'])}</p>
</main>{footer(3)}</section>
<section class="page"><main>
<div class="eyebrow">03</div><h2>{esc(copy['operate'])}</h2>
<ul class="controls">{''.join(f'<li><span class="button">{picture(name)}</span><div><h3>{esc(t)}</h3><p>{esc(b)}</p></div></li>' for name, (t,b) in zip(('buttons-arrows.svg', 'button-green.svg', 'button-red.svg', 'button-middle.svg'), copy['controls']))}</ul>
<h2 class="settings-heading">{esc(copy['settings_title'])}</h2>
{steps('settings')}
<p class="help">{esc(copy['help'])}</p>
</main>{footer(4)}</section>
</body></html>'''


def impose(source, destination, direction='ltr'):
    """Two sheetside spreads, with binding following the locale direction."""
    from pypdf import PdfReader, PdfWriter, Transformation
    reader = PdfReader(source)
    if len(reader.pages) != 4:
        raise ValueError(f'Expected four reading pages, got {len(reader.pages)}')
    width, height = 297 / 25.4 * 72, 210 / 25.4 * 72
    writer = PdfWriter()
    pairs = ((0, 3), (2, 1)) if direction == 'rtl' else ((3, 0), (1, 2))
    for pair in pairs:
        sheet = writer.add_blank_page(width, height)
        for slot, index in enumerate(pair):
            page = reader.pages[index]
            scale = min(width / 2 / float(page.mediabox.width), height / float(page.mediabox.height))
            x = slot * width / 2 + (width / 2 - float(page.mediabox.width) * scale) / 2
            y = (height - float(page.mediabox.height) * scale) / 2
            sheet.merge_transformed_page(page, Transformation().scale(scale).translate(x, y))
    writer.add_metadata({'/Title': reader.metadata.title + ' · A4', '/Author': 'Zmala'})
    with destination.open('wb') as output:
        writer.write(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--language', default='en', help='Terminal language code, or all')
    parser.add_argument('--output', type=Path, default=ROOT / 'build_tools/dist/leaflets')
    parser.add_argument('--html-only', action='store_true', help='No Node/browser/PDF dependencies needed')
    parser.add_argument('--node', default='node')
    parser.add_argument('--browser', help='Optional Chromium/Chrome/Edge executable')
    parser.add_argument('--bundle', action='store_true', help='Also create a ZIP of the generated PDFs and printing notes')
    args = parser.parse_args()
    if args.bundle and args.html_only:
        parser.error('--bundle needs PDF output')
    languages, catalogs = load_catalogs()
    selected = list(languages) if args.language == 'all' else [args.language]
    if any(code not in languages for code in selected):
        parser.error('Supported languages: ' + ', '.join(languages) + ', all')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    jobs = []
    for code in selected:
        stem = f'ZmalaTerminal-Leaflet-{code}'
        path = output / (stem + '.html')
        path.write_text(render_html(code, languages[code], catalogs[code]), encoding='utf-8')
        jobs.append({'html': str(path), 'pdf': str(output / (stem + '.pdf'))})
    if not args.html_only:
        command = [args.node, str(Path(__file__).with_name('render.cjs'))]
        if args.browser:
            command += [args.browser]
        subprocess.run(command, input=json.dumps(jobs), text=True, check=True)
        for job in jobs:
            code = Path(job['pdf']).stem.removeprefix('ZmalaTerminal-Leaflet-')
            impose(Path(job['pdf']), Path(job['pdf']).with_stem(Path(job['pdf']).stem + '-A4'), languages[code]['direction'])
        if args.bundle:
            with zipfile.ZipFile(output / 'ZmalaTerminal-Leaflets.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
                archive.write(SOURCE / 'printing.txt', 'PRINTING.txt')
                for job in jobs:
                    path = Path(job['pdf'])
                    for pdf in (path, path.with_stem(path.stem + '-A4')):
                        archive.write(pdf, pdf.name)
    print(f'Generated {len(selected)} language(s) in {output}')


if __name__ == '__main__':
    main()
