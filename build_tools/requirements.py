"""Validate the implementation baseline and publish an offline Doorstop report.

File coverage detects unmapped modules; it is not proof of behavioral completeness
or test success. Normative text lives only in Doorstop, never in this script.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from html import escape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit

from requirements_trace import audit_traces
from test_trace import audit_tests, write_test_report

ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = {
    'PROD': ('product', None),
    'SHLR': ('server/hlr', 'PROD'),
    'SLLR': ('server/llr', 'SHLR'),
    'THLR': ('terminal/hlr', 'PROD'),
    'TLLR': ('terminal/llr', 'THLR'),
}
SOURCE_ROOTS = (
    'zmala_server', 'zmala_terminal/common', 'zmala_terminal/linux',
    'build_tools/linux', 'build_tools/windows_installer', 'build_tools/server_installer',
)
SOURCE_SUFFIXES = {'.py', '.js', '.ts', '.c', '.h', '.css', '.html', '.json', '.sh',
                   '.service', '.conf', '.rules', '.script', '.plymouth'}
EXCLUSIONS = {
    'zmala_server/web/admin.js': 'Generated bundle; authored admin modules are mapped.',
    'zmala_server/web/admin.css': 'Generated bundle; authored stylesheets are mapped.',
    'zmala_server/package.json': 'Dependency/build metadata, not an application behavior.',
    'zmala_server/package-lock.json': 'Dependency lockfile.',
    'zmala_server/tsconfig.json': 'Static type-check configuration.',
    'zmala_server/tsconfig.admin.json': 'Static type-check configuration.',
    'zmala_server/assets/test-portraits/accounts.json': 'Synthetic demo fixture, not live accounts.',
}


def source_inventory(root: Path) -> tuple[list[str], dict[str, str]]:
    """Inventory authored runtime, shared contracts and Pi deployment sources."""
    included, excluded = [], {}
    for relative in SOURCE_ROOTS:
        for path in sorted((root / relative).rglob('*')):
            if not path.is_file() or path.suffix not in SOURCE_SUFFIXES:
                continue
            parts = path.relative_to(root).parts
            if any(part in {'node_modules', '__pycache__', 'data', 'framing-runtime', 'models'} for part in parts):
                continue  # Private, downloaded or generated runtime files are never inventoried.
            name = path.relative_to(root).as_posix()
            reason = EXCLUSIONS.get(name)
            if 'tests' in parts or path.name.startswith(('test-', 'probe-')):
                reason = 'Verification/probe implementation; referenced checks do not imply a passed result.'
            elif 'vendor' in parts:
                reason = 'Third-party stack; application-facing bounds are mapped in SIP requirements.'
            elif path.name == '__init__.py':
                reason = 'Package marker without runtime behavior.'
            if reason:
                excluded[name] = reason
            else:
                included.append(name)
    return sorted(included), dict(sorted(excluded.items()))


def audit(root: Path) -> dict:
    import yaml  # Supplied by the pinned Doorstop tool environment.

    errors, records = [], {}
    actual = {p.parent.relative_to(root / 'requirements').as_posix()
              for p in (root / 'requirements').rglob('.doorstop.yml')
              if 'output' not in p.relative_to(root / 'requirements').parts}
    expected = {folder for folder, _ in DOCUMENTS.values()}
    if actual != expected:
        errors.append(f'Doorstop document folders differ: {sorted(actual ^ expected)}')
    for prefix, (folder, parent) in DOCUMENTS.items():
        directory = root / 'requirements' / folder
        config = yaml.safe_load((directory / '.doorstop.yml').read_text(encoding='utf-8'))
        if config['settings'].get('prefix') != prefix or config['settings'].get('parent') != parent:
            errors.append(f'{prefix}: incorrect document prefix/parent')
        for path in sorted(directory.glob('*.yml')):
            if path.name.startswith('.'):
                continue
            data = yaml.safe_load(path.read_text(encoding='utf-8'))
            uid = path.stem
            if not re.fullmatch(prefix + r'\d{3}', uid):
                errors.append(f'{uid}: unexpected record ID')
            if uid in records:
                errors.append(f'{uid}: duplicate ID')
            records[uid] = data | {'prefix': prefix}
    referenced, children = defaultdict(set), Counter()
    for uid, item in records.items():
        prefix = item['prefix']
        if not item.get('active') or not item.get('normative') or item.get('derived'):
            errors.append(f'{uid}: baseline items must be active, normative and parent-linked')
        for key in ('header', 'text', 'area', 'verification'):
            if not isinstance(item.get(key), str) or not item[key].strip():
                errors.append(f'{uid}: missing {key}')
        if 'shall' not in item.get('text', '').lower():
            errors.append(f'{uid}: no normative statement')
        if item.get('scope') not in {'Core', 'Optional', 'Experimental'}:
            errors.append(f'{uid}: unknown scope')
        parents = [next(iter(link)) if isinstance(link, dict) else link for link in item.get('links', [])]
        expected_parent = DOCUMENTS[prefix][1]
        if bool(parents) != bool(expected_parent):
            errors.append(f'{uid}: incorrect root/parent links')
        for parent in parents:
            if parent not in records or records[parent]['prefix'] != expected_parent:
                errors.append(f'{uid}: invalid parent {parent}')
            children[parent] += 1
        references = item.get('references', [])
        if prefix in ('SLLR', 'TLLR') and not references:
            errors.append(f'{uid}: LLR has no implementation references')
        has_source = False
        for ref in references:
            name = ref.get('path', '')
            path = (root / name).resolve()
            if not path.is_relative_to(root.resolve()) or not path.is_file():
                errors.append(f'{uid}: missing/unsafe reference {name}')
            if name.startswith('zmala_terminal/windows/'):
                errors.append(f'{uid}: Windows terminal is outside this baseline')
            if prefix in ('SLLR', 'TLLR'):
                referenced[name].add(uid)
                has_source |= not name.startswith('tests/') and '/tests/' not in name and '/test-' not in name
        if prefix in ('SLLR', 'TLLR') and not has_source:
            errors.append(f'{uid}: tests alone do not identify implementation')
    for uid, item in records.items():
        if item['prefix'] in ('PROD', 'SHLR', 'THLR') and not children[uid]:
            errors.append(f'{uid}: no lower-level requirement')
    included, excluded = source_inventory(root)
    uncovered = sorted(set(included) - set(referenced))
    errors += [f'Unmapped implementation: {name}' for name in uncovered]
    # Also inspect explicitly referenced local patches/helpers outside the normal
    # inventory. Test evidence and generated bundles cannot satisfy code tracing.
    trace_files = set(included) | {name for name in referenced
        if not name.startswith('tests/') and '/tests/' not in name and not Path(name).name.startswith(('test-', 'probe-'))
        and not name.startswith('zmala_terminal/windows/') and name not in EXCLUSIONS}
    try:
        traces = audit_traces(root, records, sorted(trace_files), referenced)
    except ValueError as error:
        errors.append(str(error))
    try:
        test_trace = audit_tests(root, records)
    except ValueError as error:
        errors.append(str(error))
    if errors:
        raise ValueError('\n'.join(errors))
    return {
        'counts': dict(Counter(item['prefix'] for item in records.values())),
        'source_coverage': {name: sorted(referenced[name]) for name in included},
        'code_traces': traces,
        'test_trace': test_trace,
        'exclusions': excluded,
        'qualification': 'Source mapping and structural validation are not test results or human approval.',
    }


def run_doorstop(root: Path, *args: str) -> None:
    # Native Path spelling matters for Doorstop's Windows reference resolver.
    subprocess.run([sys.executable, '-c',
                    'from doorstop.cli.main import main; raise SystemExit(main())',
                    *args, '--project', str(root.resolve())], check=True, cwd=root)


def write_coverage(output: Path, report: dict) -> None:
    rows = []
    for name, ids in report['source_coverage'].items():
        links = ' '.join(f'<a href="documents/{re.sub(r"[0-9]", "", uid)}.html#{uid}">{uid}</a>' for uid in ids)
        rows.append(f'<tr><td class="source-path"><code>{escape(name)}</code></td><td class="source-links">{links}</td></tr>')
    exclusions = ''.join(f'<li><code>{escape(name)}</code> — {escape(reason)}</li>'
                         for name, reason in report['exclusions'].items())
    counts = ' · '.join(f'{escape(prefix)} {count}' for prefix, count in report['counts'].items())
    traces = []
    for uid, locations in report['code_traces'].items():
        link = f'documents/{uid[:4]}.html#{uid}'
        source = '<br>'.join(f'<code>{escape(entry["path"])}:{entry["line"]}</code>' for entry in locations)
        traces.append(f'<tr id="trace-{uid}"><td><a href="{link}">{uid}</a></td><td>{source}</td></tr>')
    html = f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Source coverage · ZmalaCall</title>
<link rel="stylesheet" href="template/zmala.css"><script src="template/zmala.js" defer></script></head><body>
<a class="skip" href="#main">Skip to content</a><header class="topbar"><a class="brand" href="index.html"><span class="brand-mark">Z</span> ZmalaCall <span class="brand-label">Engineering</span></a><nav aria-label="Report"><a href="index.html">Overview</a><a href="traceability.html">Traceability</a><a href="coverage.html" aria-current="page">Source coverage</a></nav></header>
<main id="main" style="margin:auto"><p class="eyebrow">Implementation inventory</p><h1>Source coverage</h1>
<p>{len(rows)} authored source files mapped to LLRs · {counts}</p>
<p><a href="tests.html">Requirement-based test plans and coverage gaps</a></p>
<p class="notice">{escape(report['qualification'])} A mapped file can still contain behavior needing a more detailed requirement; review the code and verification instructions together.</p>
<p>Scope: Linux server, shared/Pi terminal runtime and Pi deployment tools (including Windows installer front ends). Windows terminal runtime, repository development tooling and third-party internals are excluded.</p>
<div class="filter"><label for="search">Find a file or requirement</label><input id="search" type="search" placeholder="Module path or LLR ID"><output id="match-count" aria-live="polite"></output><a href="coverage.json" download>Download inventory JSON</a></div>
<h2>Code comment anchors</h2><p>{len(traces)} LLRs traced to standalone <code>@llr</code> comments. Line numbers refer to the source revision used for this build; shared behavior can have several anchors.</p>
<div class="matrix" tabindex="0" aria-label="Scrollable code trace table"><table><thead><tr><th scope="col">LLR</th><th scope="col">Code location</th></tr></thead><tbody>{''.join(traces)}</tbody></table></div>
<h2>File reference inventory</h2>
<div class="matrix" tabindex="0" aria-label="Scrollable source coverage table"><table><thead><tr><th scope="col">Implementation file</th><th scope="col">Mapped LLRs</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<details class="evidence"><summary>Excluded inventory files and reasons · {len(report['exclusions'])}</summary><ul>{exclusions}</ul></details>
<footer>Generated from Doorstop references · <a href="#main">Back to top</a></footer></main></body></html>'''
    (output / 'coverage.html').write_text(html, encoding='utf-8')
    (output / 'coverage.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')


class ReportPage(HTMLParser):
    """Collect actual HTML targets, avoiding regex-based markup validation."""

    def __init__(self, text: str):
        super().__init__()
        self.ids: set[str] = set()
        self.links: list[str] = []
        self.duplicates: list[str] = []
        self.feed(text)

    def handle_starttag(self, tag: str, attrs: list) -> None:
        values = dict(attrs)
        if uid := values.get('id'):
            if uid in self.ids:
                self.duplicates.append(uid)
            self.ids.add(uid)
        for attribute in ('href', 'src'):
            if values.get(attribute):
                self.links.append(values[attribute])


def check_report(output: Path, counts: dict) -> None:
    """Reject broken navigation, missing items and external asset dependencies."""
    pages = {p.resolve(): ReportPage(p.read_text(encoding='utf-8'))
             for p in [output / 'index.html', output / 'traceability.html', output / 'coverage.html', output / 'tests.html',
                       *(output / 'documents' / (prefix + '.html') for prefix in DOCUMENTS)]}
    for path, page in pages.items():
        if page.duplicates:
            raise ValueError(f'{path.name}: duplicate anchors {page.duplicates}')
        if path.stem in counts:
            ids = [uid for uid in page.ids if re.fullmatch(path.stem + r'\d{3}', uid)]
            if len(ids) != counts[path.stem]:
                raise ValueError(f'{path.name}: incomplete rendered requirements')
        for link in page.links:
            url = urlsplit(link)
            if url.scheme or url.netloc:
                raise ValueError(f'{path.name}: report must work offline: {link}')
            target = (path.parent / unquote(url.path)).resolve() if url.path else path
            if not target.is_relative_to(output.resolve()) or not target.is_file():
                raise ValueError(f'{path.name}: missing/unsafe report link {link}')
            if url.fragment and (target not in pages or unquote(url.fragment) not in pages[target].ids):
                raise ValueError(f'{path.name}: missing anchor {link}')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Validate only; do not publish')
    args = parser.parse_args()
    try:
        report = audit(ROOT)
        run_doorstop(ROOT, '--no-reformat', '--error-all', '--no-review-check')
        print(f"Baseline: {report['counts']}; {len(report['source_coverage'])} source files mapped; "
              f"{len(report['code_traces'])} LLRs anchored in code.")
        test_trace = report['test_trace']
        print(f"Test plans: {len(test_trace['tests'])}; unmapped requirements: "
              + ', '.join(f'{prefix} {len(ids)}' for prefix, ids in test_trace['unmapped'].items()))
        if not args.check:
            output = ROOT / 'requirements' / 'output'
            # Only obsolete generated document pages are removed. No recursive workspace deletion.
            for page in (output / 'documents').glob('*.html'):
                if page.stem not in DOCUMENTS:
                    page.unlink()
            run_doorstop(ROOT, 'publish', 'all', str(output), '--html', '--template', 'zmala')
            write_coverage(output, report)
            write_test_report(output, report['test_trace'])
            check_report(output, report['counts'])
            print(f"Report: {output / 'index.html'}")
        return 0
    except (ImportError, ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f'Requirements failed: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
