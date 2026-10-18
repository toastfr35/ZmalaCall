"""Merge gcov counters from LLT binaries and zero-hit baseline objects."""
import gzip
from html import escape
import json
from pathlib import Path
import platform
import sys


def collect(root, build):
    files = {}
    for path in build.glob('*.gcov.json.gz'):
        data = json.loads(gzip.decompress(path.read_bytes()))
        for entry in data['files']:
            file = Path(entry['file'])
            if not file.is_absolute():
                file = Path(data['current_working_directory'])/file
            file = file.resolve()
            if not file.is_relative_to(root/'zmala_terminal/linux/media'):
                continue
            name = file.relative_to(root).as_posix()
            target = files.setdefault(name, {'lines': {}, 'functions': {}})
            for line in entry['lines']:
                number = str(line['line_number'])
                target['lines'][number] = target['lines'].get(number, 0) + line['count']
            for fn in entry['functions']:
                key = f"{fn['start_line']}:{fn['name']}"
                target['functions'][key] = target['functions'].get(key, 0) + fn['execution_count']
    return files


def write(root, build, output):
    files = collect(root.resolve(), build)
    if not files:
        raise ValueError('No authored native counters found')
    metrics = {key: [sum(v > 0 for f in files.values() for v in f[field].values()),
                     sum(len(f[field]) for f in files.values())]
               for key, field in [('statements', 'lines'), ('functions', 'functions')]}
    (output/'summary.json').write_text(json.dumps({'measurements': metrics, 'files': files,
        'platform': platform.platform(),
        'metric': 'gcov executable lines and function execution counts; LLT only'}, indent=2)+'\n', encoding='utf-8')
    rows = []
    for name, entry in sorted(files.items()):
        anchor = name.replace('/', '_')+'.html'
        content = []
        for number, line in enumerate((root/name).read_text(encoding='utf-8').splitlines(), 1):
            hits = entry['lines'].get(str(number))
            color = '#ffdada' if hits == 0 else '#ddffdd' if hits else 'white'
            content.append(f'<div style="background:{color}">{number:4} {escape(line)}</div>')
        (output/anchor).write_text('<meta charset="utf-8"><a href="index.html">Index</a><pre>'+''.join(content)+'</pre>', encoding='utf-8')
        row = [f'<a href="{anchor}">{escape(name)}</a>']
        for field in ('functions', 'lines'):
            counts = entry[field]
            row.append(f'{sum(v > 0 for v in counts.values())}/{len(counts)}')
        rows.append('<tr>'+''.join(f'<td>{v}</td>' for v in row)+'</tr>')
    (output/'index.html').write_text('<meta charset="utf-8"><title>Native LLT coverage</title>'
        '<style>body{font:16px system-ui;margin:2rem}td,th{padding:1rem;text-align:left;overflow-wrap:anywhere}table{width:100%;table-layout:fixed}</style>'
        '<h1>Terminal native C — LLT only</h1><p>gcov executable lines and function entry counters. '
        'Zero-hit baseline objects include untested translation units.</p>'
        '<table><tr><th>Source</th><th>Functions</th><th>Executable lines</th></tr>'+''.join(rows)+'</table>', encoding='utf-8')
    print(json.dumps(metrics))


if __name__ == '__main__':
    write(*(Path(value) for value in sys.argv[1:]))
