"""Publish Doorstop source records as linked, CommonMark-compatible docs."""
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
EXECUTABLE = ROOT/'build_tools/runtime/doorstop/Scripts/doorstop.exe'
REPORTS = {'ZMC': ('product_requirements.md', 'Product requirements'),
           'TERM': ('terminal_requirements.md', 'Terminal requirements'),
           'SERV': ('server_requirements.md', 'Server requirements')}
HEADING = re.compile(r'^(#+) (.+?) \{#([^}]+)\}$', re.MULTILINE)

with tempfile.TemporaryDirectory(prefix='requirements-', dir=ROOT/'build_tools/tmp') as directory:
    subprocess.run([str(EXECUTABLE), 'publish', 'all', directory, '--markdown', '--project', str(ROOT)], check=True)
    for prefix, (filename, title) in REPORTS.items():
        content = (Path(directory)/f'{prefix}.md').read_text(encoding='utf-8')
        headings = list(HEADING.finditer(content))
        if not headings:
            raise RuntimeError(f'No published requirements in {prefix}')
        content = content[headings[0].start():]
        contents = '\n'.join(f'- [{heading.group(2)}](#{heading.group(3)})' for heading in headings)
        content = HEADING.sub(lambda match: f'<a id="{match.group(3)}"></a>\n\n## {match.group(2)}', content)
        for doc_prefix, (doc_filename, _) in REPORTS.items():
            content = content.replace(f']({doc_prefix}.md', f']({doc_filename}')
        def normalize_link(match):
            identifiers = re.findall(r'(?:ZMC|TERM|SERV)\d{3}', match.group(2), re.IGNORECASE)
            return f']({match.group(1)}#{identifiers[-1].upper()})' if identifiers else match.group(0)
        content = re.sub(r'\]\(([^)#]+)#([^)]*)\)', normalize_link, content)
        intro = (f'# {title}\n\nGenerated from [Doorstop {prefix} records](requirements/'
                 f'{dict(ZMC="product", TERM="terminal", SERV="server")[prefix]}/). '
                 'Edit the YAML records, then run `build_tools/publish-requirements.ps1`.\n\n'
                 f'{contents}\n\n')
        (ROOT/'docs'/filename).write_text(intro+content, encoding='utf-8')
        print(f'Published docs/{filename}')

for filename, _ in REPORTS.values():
    report = ROOT/'docs'/filename
    for target in re.findall(r'\]\(([^)]+)\)', report.read_text(encoding='utf-8')):
        path, _, anchor = target.partition('#')
        linked = report.parent/path if path else report
        if not linked.exists():
            raise RuntimeError(f'Broken report link: {filename} -> {target}')
        if anchor and f'id="{anchor}"' not in linked.read_text(encoding='utf-8'):
            raise RuntimeError(f'Broken report anchor: {filename} -> {target}')
print('All generated requirement links and anchors resolve.')
