"""Small fault-injection audit; never contributes hits to RBT coverage.

Each mutation is compiled in a child process only. Production files are never
rewritten. A failing test must report an assertion failure, not an import/parser
error, before it counts as detecting the injected fault. This is a bounded sample,
not an exhaustive mutation score.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
OUTPUT = ROOT / 'tests/coverage/review'
CASES = [
    ('photo-byte-boundary', 'node', 'zmala_server/backup-storage.js',
     'bytes > 47 * 1024 * 1024', 'bytes >= 47 * 1024 * 1024',
     'tests/server/LLT/backup-components.test.js'),
    ('photo-count-limit', 'node', 'zmala_server/backup-storage.js',
     'files.size >= 1004', 'files.size > 1004',
     'tests/server/LLT/backup-components.test.js'),
    ('restore-unknown-path', 'node', 'zmala_server/backup-storage.js',
     "if (!FILES.includes(name) && !PHOTO.test(name))", 'if (false)',
     'tests/server/LLT/backup-components.test.js'),
    ('restore-pending-guard', 'node', 'zmala_server/backup-storage.js',
     "if (fs.existsSync(path.join(recovery, 'pending.json')))", 'if (false)',
     'tests/server/LLT/backup-components.test.js'),
    ('usb-wake-level', 'python', 'zmala_terminal/linux/c20_volume.py',
     '            request(_desired)\n\n\ndef request', '            request(100)\n\n\ndef request',
     'tests.terminal.LLT.test_volume_control'),
    ('volume-direction', 'python', 'zmala_terminal/common/volume_control.py',
     'self.remainder -= dy', 'self.remainder += dy',
     'tests.terminal.LLT.test_volume_control'),
]
NODE = r"""
const Module = require('node:module'), path = require('node:path');
const original = Module.prototype._compile;
Module.prototype._compile = function(source, file) {
  if (path.resolve(file) === path.resolve(process.env.REVIEW_TARGET)) {
    const from = process.env.REVIEW_FROM, to = process.env.REVIEW_TO;
    if (source.split(from).length !== 2) throw Error('Mutation anchor is not unique');
    source = source.replace(from, to);
  }
  return original.call(this, source, file);
};
"""
PYTHON = r"""
import importlib, os, pathlib, sys, unittest
module = importlib.import_module(os.environ['REVIEW_TARGET'].replace('/', '.')[:-3])
source = pathlib.Path(module.__file__).read_text(encoding='utf-8')
before, after = os.environ['REVIEW_FROM'], os.environ['REVIEW_TO']
assert source.count(before) == 1, 'Mutation anchor is not unique'
exec(compile(source.replace(before, after), module.__file__, 'exec'), module.__dict__)
result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromName(sys.argv[1]))
sys.exit(0 if result.wasSuccessful() else 1)
"""


def execute(command, env):
    result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True,
                            encoding='utf-8', errors='replace', timeout=60)
    return result.returncode, result.stdout + result.stderr


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    results = []
    with tempfile.TemporaryDirectory() as temporary:
        preload = Path(temporary) / 'mutate.cjs'
        preload.write_text(NODE, encoding='utf-8')
        baselines = set()
        for name, language, source, before, after, suite in CASES:
            env = {k: v for k, v in os.environ.items() if not k.startswith('ZMALA_COVERAGE_')}
            baseline = ['node', '--test', suite] if language == 'node' else [sys.executable, '-m', 'unittest', suite]
            if suite not in baselines:
                code, output = execute(baseline, env)
                if code:
                    raise RuntimeError(f'Baseline failed for {suite}:\n{output}')
                baselines.add(suite)
            env.update(REVIEW_TARGET=source, REVIEW_FROM=before, REVIEW_TO=after)
            command = (['node', '--require', str(preload), '--test', suite] if language == 'node'
                       else [sys.executable, '-c', PYTHON, suite])
            code, output = execute(command, env)
            detected = code != 0 and ('AssertionError' in output or 'ERR_ASSERTION' in output)
            status = 'detected' if detected else 'survived' if code == 0 else 'invalid-run'
            (OUTPUT / f'{name}.log').write_text(output, encoding='utf-8')
            results.append({'name': name, 'source': source, 'suite': suite, 'status': status})
            print(f'{name}: {status}', flush=True)
    (OUTPUT/'mutations.json').write_text(json.dumps(results, indent=2)+'\n', encoding='utf-8')
    return 0 if all(r['status'] == 'detected' for r in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
