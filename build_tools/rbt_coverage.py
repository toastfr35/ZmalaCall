"""Measure LLT execution, independently of planned requirement traceability.

Only tests/{server,terminal}/LLT are discovered. Unexecuted authored sources stay
in the denominator. HLT, ad-hoc, fixtures and dependencies cannot add hits.
"""
from __future__ import annotations

import argparse
from html import escape
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'tests/coverage/LLT'


def inventory(component):
    from requirements import audit
    report = audit(ROOT)
    prefix = 'LLR-SRV-' if component == 'server' else 'LLR-TERM-'
    return {name: [uid for uid in ids if uid.startswith(prefix)]
            for name, ids in report['source_coverage'].items()
            if any(uid.startswith(prefix) for uid in ids)}


def python_run(component):
    import coverage
    files = [name for name in inventory(component) if name.endswith('.py')]
    destination = OUTPUT/component/'python'
    destination.mkdir(parents=True, exist_ok=True)
    cov = coverage.Coverage(data_file=str(destination/'.coverage'), config_file=False,
                            branch=True, include=[str(ROOT/name) for name in files])
    # Do not hide defensive paths or main entrypoints with implicit exclusions.
    cov.set_option('report:exclude_lines', [])
    cov.start()
    sys.path.insert(0, str(ROOT))
    suite = unittest.defaultTestLoader.discover(str(ROOT/'tests'/component/'LLT'),
                                               pattern='test_*.py', top_level_dir=str(ROOT))
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    cov.stop()
    cov.save()
    paths = [str(ROOT/name) for name in files]
    cov.json_report(morfs=paths, outfile=str(destination/'coverage.json'))
    cov.html_report(morfs=paths, directory=str(destination/'html'), title=f'{component} LLT Python')
    cov.xml_report(morfs=paths, outfile=str(destination/'coverage.xml'))
    (destination/'execution.json').write_text(json.dumps({
        'tests': result.testsRun, 'skips': len(result.skipped),
        'failures': len(result.failures), 'errors': len(result.errors),
        'platform': platform.platform(),
    }, indent=2)+'\n', encoding='utf-8')
    return 0 if result.wasSuccessful() else 1


def run(command, log, env=None):
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open('w', encoding='utf-8') as stream:
        result = subprocess.run(command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
    print(f'{log.relative_to(ROOT)}: exit {result.returncode}', flush=True)
    return result.returncode


def python_metrics(file):
    data = json.loads(file.read_text(encoding='utf-8'))
    totals = data['totals']
    functions = [value for entry in data['files'].values()
                 for name, value in entry['functions'].items() if name]
    # Function entry means at least one executable body statement was reached;
    # the def/class declaration being executed is not a function invocation.
    functions = [f for f in functions if f['summary']['num_statements']]
    return {'statements': [totals['covered_lines'], totals['num_statements']],
            'functions': [sum(bool(f['executed_lines']) for f in functions), len(functions)]}


def js_metrics(file):
    data = json.loads(file.read_text(encoding='utf-8'))['total']
    return {key: [data[key]['covered'], data[key]['total']] for key in ('statements', 'functions')}


def summarize(results):
    rows, measurements, unmeasured, gaps = [], {}, {}, []
    results = dict(results)
    for component in ('server', 'terminal'):
        sources = inventory(component)
        # Declarations, static styles and JSON are not executable statements.
        native_file = OUTPUT/component/'native/summary.json'
        native = json.loads(native_file.read_text(encoding='utf-8')) if native_file.exists() else None
        native_files = set(native['files']) if native else set()
        # Headers contain declarations, not separate translation units. Any
        # executable header bodies are reported by gcov at their original path.
        unsupported = [p for p in sources if Path(p).suffix in {'.c', '.sh', '.script'} and p not in native_files]
        unmeasured[component] = unsupported
        for language in ('javascript', 'python', 'native'):
            folder = OUTPUT/component/language
            report = folder/({'javascript':'coverage-summary.json', 'python':'coverage.json', 'native':'summary.json'}[language])
            if not report.exists():
                if language == 'python' or (language == 'javascript' and component == 'server'):
                    results[f'{component}/{language}-missing-report'] = 1
                continue
            metrics = native['measurements'] if language == 'native' else js_metrics(report) if language == 'javascript' else python_metrics(report)
            execution = folder/'execution.json'
            environment = platform.platform()
            if language == 'native':
                environment = native.get('platform', 'Linux native compiler run')
            elif execution.exists():
                evidence = json.loads(execution.read_text(encoding='utf-8'))
                environment = evidence['platform']
                results[f'{component}/{language}'] = int(bool(evidence['failures'] or evidence['errors']))
            measurements[f'{component}/{language}'] = metrics
            values = []
            for key in ('functions', 'statements'):
                hit, total = metrics[key]
                values.append(f'{hit}/{total} ({100*hit/total:.2f}%)' if total else 'No executable code')
            link = f'{component}/{language}/' + ('html/index.html' if language == 'python' else 'index.html')
            rows.append(f'<tr><td><a href="{link}">{component} — {language}</a><br><small>{escape(environment)}</small></td>' +
                        ''.join(f'<td>{value}</td>' for value in values) + '</tr>')
            if language == 'python':
                data = json.loads(report.read_text(encoding='utf-8'))
                for name, item in data['files'].items():
                    path = name.replace('\\', '/')
                    gaps.append({'component': component, 'path': path,
                                 'requirements': sources.get(path, []),
                                 'missing_statements': len(item['missing_lines']),
                                 'missing_lines': item['missing_lines'],
                                 'missing_functions': [name for name, f in item['functions'].items()
                                                       if name and f['summary']['num_statements'] and not f['executed_lines']]})
            elif language == 'javascript':
                data = json.loads((folder/'coverage-final.json').read_text(encoding='utf-8'))
                for name, item in data.items():
                    path = Path(name).relative_to(ROOT).as_posix()
                    gaps.append({'component': component, 'path': path, 'requirements': sources.get(path, []),
                        'missing_statements': sum(count == 0 for count in item['s'].values()),
                        'missing_lines': sorted({item['statementMap'][key]['start']['line'] for key, count in item['s'].items() if not count}),
                        'missing_functions': [f"{item['fnMap'][key]['name']}:{item['fnMap'][key]['loc']['start']['line']}" for key, count in item['f'].items() if not count]})
            else:
                for path, item in native['files'].items():
                    missing = [int(n) for n, count in item['lines'].items() if not count]
                    gaps.append({'component': component, 'path': path, 'requirements': sources.get(path, []),
                                 'missing_statements': len(missing), 'missing_lines': sorted(missing),
                                 'missing_functions': [name for name, count in item['functions'].items() if not count]})
        (OUTPUT/component/'inventory.json').write_text(json.dumps(sources, indent=2)+'\n', encoding='utf-8')
    target_met = bool(measurements) and not any(results.values()) and not any(unmeasured.values()) and all(
        hit == total for metrics in measurements.values() for hit, total in metrics.values())
    summary = {'suite': 'LLT only', 'target_percent': 100, 'target_met': target_met,
               'platform': platform.platform(), 'commands': results, 'measurements': measurements,
               'unmeasured_executable_sources': unmeasured}
    (OUTPUT/'summary.json').write_text(json.dumps(summary, indent=2)+'\n', encoding='utf-8')
    gaps.sort(key=lambda row: row['missing_statements'], reverse=True)
    (OUTPUT/'gaps.json').write_text(json.dumps(gaps, indent=2)+'\n', encoding='utf-8')
    gap_rows = ''.join('<tr><td>'+escape(row['path'])+'</td><td>'+str(row['missing_statements'])+
                       '</td><td>'+str(len(row['missing_functions']))+'</td></tr>' for row in gaps[:20])
    missing = ''.join(f'<h3>{component}</h3><ul>'+''.join(f'<li><code>{escape(p)}</code></li>' for p in paths)+'</ul>'
                      for component, paths in unmeasured.items())
    (OUTPUT/'index.html').write_text('''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Zmala LLT coverage</title>
<style>body{font:16px system-ui;margin:2rem auto;max-width:1100px;padding:0 1rem;color:#182434}
table{border-collapse:collapse;width:100%;table-layout:fixed}td,th{text-align:left;padding:1rem;border-bottom:1px solid #ccd;overflow-wrap:anywhere}
th:first-child{width:54%}@media(max-width:600px){body{margin:1rem auto}td,th{padding:.55rem .3rem;font-size:14px}th:first-child{width:44%}}
a{color:#145db1}code{overflow-wrap:anywhere}.notice{background:#fff1cf;padding:1rem}</style>
<h1>Requirement-based LLT coverage</h1><p>Target: 100% functions and statements, independently for each component.</p>
<p class="notice">''' + ('Target reached.' if target_met else 'Target NOT reached.') + '''
 HLTs and ad-hoc tests contribute no coverage. Unimported files count as uncovered.
 Coverage measures execution, not assertion quality or full requirement compliance.</p>
<table><thead><tr><th>Component / report</th><th>Functions</th><th>Statements</th></tr></thead><tbody>'''+''.join(rows)+'''</tbody></table>
<p>JavaScript uses Istanbul statement/function counters, including VM and browser execution.
Python uses coverage.py executable-line statements and named function regions; a function is reached when its body executes.
Native C uses gcov executable lines and function entry counters, including zero-hit translation units.
These language metrics are shown separately rather than combined into a misleading percentage.
Report source includes Pi runtime and requirement-mapped host configuration; installers and packaging are excluded. See each component's inventory.json.</p>
<p>Local platform: '''+escape(platform.platform())+'''. Execution logs and Python skip counts are retained alongside the reports.
Type declarations, static configuration, styles and data have no executable counters.
Upstream vendor code, generated bundles and Windows terminal code are outside the authored Pi baseline.</p>
<h2>Largest measured gaps</h2><p><a href="gaps.json">All missing lines/functions with LLR references</a></p>
<table><tr><th>Source</th><th>Missing statements</th><th>Unreached functions</th></tr>'''+gap_rows+'''</table>
<h2>Executable sources not measured by this run</h2><p>These cannot be treated as covered or excluded to achieve 100%.
Native C needs a compiler-instrumented Linux run; shell/Plymouth scripts need separate instrumentation.</p>'''+missing+
'''<p><a href="summary.json">Machine-readable results</a></p></html>''', encoding='utf-8')
    print(json.dumps(summary['measurements'], indent=2))
    print('Report:', OUTPUT/'index.html')
    return target_met


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', choices=('server', 'terminal'), help=argparse.SUPPRESS)
    parser.add_argument('--check', action='store_true', help='Fail unless every metric reaches 100% and every executable source is measured.')
    parser.add_argument('--report-only', action='store_true', help='Rebuild the index after importing a native or Linux report; do not rerun tests.')
    args = parser.parse_args()
    if args.python:
        return python_run(args.python)
    if args.report_only:
        results = json.loads((OUTPUT/'summary.json').read_text(encoding='utf-8'))['commands']
        target_met = summarize(results)
        return 1 if any(results.values()) or (args.check and not target_met) else 0
    from requirements import audit
    audit(ROOT)  # Broken/missing requirement test plans invalidate the run.
    if not OUTPUT.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError('Coverage output must remain inside the checkout')
    OUTPUT.mkdir(parents=True, exist_ok=True)
    # Fail rather than mix old evidence into a new run.
    import shutil
    for component in ('server', 'terminal'):
        folder = OUTPUT/component
        if folder.exists():
            if folder.is_symlink() or not folder.resolve().is_relative_to(OUTPUT.resolve()):
                raise ValueError('Unsafe coverage output directory')
            shutil.rmtree(folder)
        folder.mkdir()
    results = {}
    results['build-admin'] = run(['node', 'build_tools/build-admin.cjs'], OUTPUT/'build.log')
    raw = OUTPUT/'server/javascript/raw'
    env = os.environ | {'ZMALA_COVERAGE_DIR': str(raw), 'ZMALA_COVERAGE_PRELOAD': '1'}
    # Node --test subprocesses inherit execArgv, so every LLT gets the hook.
    files = sorted(str(p.relative_to(ROOT)) for p in (ROOT/'tests/server/LLT').glob('*.test.js'))
    results['server/javascript'] = run(['node', '--require', str(ROOT/'build_tools/coverage-js.cjs'),
                                      '--test', *files], OUTPUT/'server/javascript/execution.log', env)
    report_env = os.environ | {'ZMALA_COVERAGE_DIR': str(raw), 'ZMALA_COVERAGE_PRELOAD': '0'}
    results['javascript-report'] = run(['node', 'build_tools/coverage-js.cjs'], OUTPUT/'server/javascript/report.log', report_env)
    for component in ('server', 'terminal'):
        results[f'{component}/python'] = run([sys.executable, __file__, '--python', component], OUTPUT/component/'python/execution.log')
    target_met = summarize(results)
    return 1 if any(results.values()) or (args.check and not target_met) else 0


if __name__ == '__main__':
    raise SystemExit(main())
