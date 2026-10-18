"""Manage only the named disposable Compose project, never the installed Pis."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
REPORTS = ROOT / 'tests/coverage/network-lab'


def compose(*args, check=True, timeout=120):
    files = ['-f', str(HERE/'compose.yml')]
    if os.environ.get('ZMALA_LAB_TLS') == '1':
        files += ['-f', str(HERE/'tls.yml')]
    result = subprocess.run(['docker', 'compose', *files, *args],
                            capture_output=True, text=True, timeout=timeout)
    if check and result.returncode:
        raise RuntimeError('Lab command failed: '+(result.stderr or result.stdout)[-4000:])
    return result


def execute(service, *args, check=True, timeout=25):
    return compose('exec', '-T', service, *args, check=check, timeout=timeout)


def rpc(identity, action, **values):
    code = '''import json,sys,urllib.request
r=urllib.request.Request('http://127.0.0.1:9090',data=sys.argv[1].encode(),headers={'Content-Type':'application/json'})
print(urllib.request.urlopen(r,timeout=18).read().decode())'''
    result = execute('terminal-'+identity, 'python3', '-c', code, json.dumps({'action': action, **values}))
    value = json.loads(result.stdout)
    if 'error' in value:
        raise RuntimeError(value['error'])
    return value


def build():
    # Explicit source allowlist: never send local server state, SDK downloads or accounts to Docker.
    with tempfile.TemporaryDirectory(prefix='zmala-network-build-') as directory:
        context = Path(directory)
        excluded = shutil.ignore_patterns('node_modules', 'data', '__pycache__', 'account-pictures',
                                         'framing-runtime', 'turn-runtime', 'models', '*.log', '*.so', '*.pyc',
                                         '.env', '.env.*', '*.pem', '*.key', '*.p12', '*.pfx', 'password.txt')
        for name in ('zmala_server', 'zmala_terminal/common', 'zmala_terminal/linux', 'tests/support/network_lab'):
            shutil.copytree(ROOT/name, context/name, ignore=excluded)
        for name in ('build_tools/build-admin.cjs', 'build_tools/convert-photo.py',
                     'build_tools/linux/build-media.sh', 'tests/terminal/LLT/turn_parser.cpp', 'build_tools/linux/build-turn.py'):
            destination = context/name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes((ROOT/name).read_bytes().replace(b'\r\n', b'\n'))
        shutil.copy(HERE/'Dockerfile', context/'Dockerfile')
        subprocess.run(['docker', 'build', '-t', 'zmala-network-lab:local', str(context)], check=True)


def bridge_rules(remove=False):
    # Allow Ethernet frames within each lab bridge to reach our router even when
    # their IP destination is outside that subnet. Cross-bridge/host egress stays blocked.
    for name in ('home-a', 'home-b', 'server-lan', 'internet'):
        inspected = subprocess.run(['docker', 'network', 'inspect', 'zmala-network-lab_'+name],
                                   capture_output=True, text=True)
        if remove and inspected.returncode:
            continue
        inspected.check_returncode()
        network = json.loads(inspected.stdout)[0]
        bridge = 'br-'+network['Id'][:12]
        rule = ['DOCKER-USER', '-i', bridge, '-o', bridge, '-m', 'comment',
                '--comment', 'zmala-network-lab', '-j', 'ACCEPT']
        exists = subprocess.run(['iptables', '-C', *rule], capture_output=True).returncode == 0
        if remove and exists:
            subprocess.run(['iptables', '-D', *rule], check=True)
        elif not remove and not exists:
            subprocess.run(['iptables', '-I', *rule], check=True)


def up():
    result = compose('up', '-d')
    bridge_rules()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['build', 'up', 'down', 'status', 'logs'])
    args = parser.parse_args()
    if args.action == 'build':
        build()
        return
    arguments = {'up': ['up', '-d'], 'down': ['down', '--volumes', '--remove-orphans'],
                 'status': ['ps', '-a'], 'logs': ['logs', '--no-color', '--tail', '100']}[args.action]
    if args.action == 'down':
        bridge_rules(remove=True)
    result = up() if args.action == 'up' else compose(*arguments)
    print(result.stdout + result.stderr)


if __name__ == '__main__':
    main()
