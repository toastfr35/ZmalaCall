"""Run standalone display HLTs that unittest discovery does not collect."""
import os
from pathlib import Path
import subprocess
import sys

from test_trace import read_plan

ROOT = Path(__file__).resolve().parents[1]


def scenarios(root):
    for path in sorted((root/'tests/terminal/HLT').glob('*.py')):
        if path.name == '__init__.py' or path.name.startswith('test_'):
            continue  # Already collected by unittest.
        plan = read_plan(path)
        if plan['environment'] == 'display':
            yield path, plan['test']


def main():
    if sys.platform == 'linux' and not os.environ.get('DISPLAY'):
        raise SystemExit('Display HLT requires DISPLAY; run with xvfb-run -a.')
    for path, identifier in scenarios(ROOT):
        print(f'{identifier}: {path.name}', flush=True)
        subprocess.run([sys.executable, str(ROOT/'tests/support/terminal/run_display.py'), str(path)],
                       cwd=ROOT, check=True, timeout=900)


if __name__ == '__main__':
    main()
