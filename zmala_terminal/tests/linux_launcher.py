"""Check managed Linux launch/stop and duplicate-instance protection on a display."""
import argparse
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
scripts = ROOT / 'build_tools/linux'
data = ROOT / 'zmala_terminal/data'
parser = argparse.ArgumentParser()
parser.add_argument('--bootstrap', required=True)
args = parser.parse_args()


def run(script, *arguments, check=True):
    return subprocess.run(['sh', str(scripts / script), *arguments],
                          capture_output=True, text=True, check=check, timeout=15)


for profile, launcher, options in [
    ('linux-launcher-test', 'start-terminal.sh', ['--bootstrap', args.bootstrap]),
    ('linux-launcher-qr-test', 'start-terminal-unconfigured.sh', []),
]:
    try:
        print(run(launcher, '--profile', profile, *options).stdout.strip())
        time.sleep(3)
        record = data / f'{profile}.pid.json'
        value = json.loads(record.read_text())
        assert Path(f'/proc/{value["pid"]}').exists()
        duplicate = run(launcher, '--profile', profile, *options, check=False)
        assert duplicate.returncode != 0, 'Duplicate profile was allowed'
        print(run('stop-terminal.sh', '--profile', profile).stdout.strip())
        assert not record.exists()
        # A managed run is reaped by init, but may briefly remain as a zombie.
        stat = Path(f'/proc/{value["pid"]}/stat')
        assert not stat.exists() or stat.read_text().rsplit(')', 1)[1].split()[0] == 'Z'
    finally:
        run('stop-terminal.sh', '--profile', profile)
print('Configured/unconfigured Linux launch, duplicate lock and stop passed.')
