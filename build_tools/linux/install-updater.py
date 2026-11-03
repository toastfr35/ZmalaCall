"""One-time/manual installer bootstrap; automatic releases never execute this file."""
import argparse
import json
import os
from pathlib import Path
import platform
import pwd
import re
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
MODULES = ('update_transaction', 'update_package', 'update_supervisor', 'update_runtime',
           'update_download', 'update_prepare', 'update_service', 'update_screen', 'update_snapshot', 'update_server')


def command(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=60).stdout.strip()


def release_info(source):
    record = source/'build_tools/linux/release-info.json'
    if record.is_file():
        value = json.loads(record.read_text())
    else:
        # Developer checkout installation uses the same committed version policy.
        gradle = (source/'zmala_phone/app/build.gradle').read_text()
        value = {'version': re.search(r"versionName '([^']+)'", gradle)[1],
                 'sequence': int(re.search(r'versionCode (\d+)', gradle)[1]),
                 'commit': command('git', '-C', str(source), 'rev-parse', 'HEAD')}
    if (not re.fullmatch(r'\d+\.\d+\.\d+', value['version'])
            or type(value['sequence']) is not int or value['sequence'] <= 0
            or not re.fullmatch('[a-f0-9]{40}', value['commit'])):
        raise ValueError('Invalid packaged release identity')
    return value


def write_json(path, value):
    temporary = path.with_suffix('.next')
    with temporary.open('w') as stream:
        json.dump(value, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.chmod(0o644)
    os.replace(temporary, path)


def install(source, user, layout=Path('/'), run=command):
    if os.geteuid() != 0 or pwd.getpwnam(user).pw_uid == 0:
        raise ValueError('Run as root with an unprivileged terminal user')
    if not re.fullmatch('[a-z_][a-z0-9_-]{0,31}', user):
        raise ValueError('Invalid terminal user')
    info = release_info(source)
    run('python3', str(source/'build_tools/linux/install-terminal-host.py'), '--source', str(source))
    if run('systemctl', 'show', '--value', '-p', 'LoadState', 'zmalacall-updater.service') != 'not-found':
        run('systemctl', 'stop', 'zmalacall-updater.service')
    stable = layout/'usr/local/lib/zmalacall-updater'
    stable.mkdir(mode=0o755, parents=True, exist_ok=True)
    version = stable/('install-'+uuid.uuid4().hex)
    library = version/'zmala_terminal/linux'
    library.mkdir(parents=True)
    for path in (version/'zmala_terminal/__init__.py', library/'__init__.py'):
        path.write_text('')
    for module in MODULES:
        shutil.copyfile(source/'zmala_terminal/linux'/(module+'.py'), library/(module+'.py'))
    for directory, _, files in os.walk(version):
        Path(directory).chmod(0o755)
        for name in files:
            (Path(directory)/name).chmod(0o644)
    sys.path.insert(0, str(version))
    from zmala_terminal.linux.update_transaction import Transactions, sync_directory
    from zmala_terminal.linux.update_prepare import freeze
    freeze(version)
    temporary = stable/'current.next'
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(version)
    os.replace(temporary, stable/'current')
    sync_directory(stable)
    root = layout/'opt/zmalacall-updates'
    root.mkdir(mode=0o755, exist_ok=True)
    tx = Transactions(root)
    root.chmod(0o755)
    tx.slots.chmod(0o755)
    try:
        pwd.getpwnam('zmalaupdate')
    except KeyError:
        run('useradd', '--system', '--no-create-home', '--shell', '/usr/sbin/nologin', 'zmalaupdate')
    configuration = layout/'etc/zmalacall'
    configuration.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source/'build_tools/linux/update-keys.json', configuration/'update-keys.json')
    (configuration/'update-keys.json').chmod(0o644)
    release = {}
    for line in (layout/'etc/os-release').read_text().splitlines():
        if '=' in line:
            key, value = line.split('=', 1)
            release[key] = value.strip('"')
    sdk = run('dpkg-query', '-W', '-f=${Version}', 'libmediastreamer2-14').split('+')[0].split(':')[-1]
    config = {'user': user, 'builder': 'zmalaupdate', 'root': str(root),
              'keys': str(configuration/'update-keys.json'), 'data': '/var/lib/zmalacall',
              'data_checkpoints': '/var/lib/zmalacall-update-data',
              'compatibility': {'architecture': platform.machine(), 'os': release.get('VERSION_CODENAME'),
                                'sdk': sdk, 'updater': 1, 'data': 1, 'host': 3}}
    write_json(configuration/'updater.json', config)
    run('systemctl', 'stop', 'zmalacall-terminal.service')
    installed = (layout/'opt/zmalacall/current').resolve(strict=True)
    identity = 'bootstrap-'+uuid.uuid4().hex
    slot = tx.slots/identity
    shutil.copytree(installed, slot, symlinks=True)
    write_json(slot/'update-release.json', dict(info, digest='bootstrap', owned_by_updater=1))
    freeze(slot)
    previous = tx.read('confirmed')
    tx.write('confirmed', {'slot': identity, 'previous': previous.get('slot') if previous else None,
                           'transaction': 'manual-'+uuid.uuid4().hex})
    tx.select(identity)
    tx.write('pending', {'state': 'confirmed', 'transaction': 'manual'})
    alias = layout/'opt/zmalacall/current.next'
    alias.unlink(missing_ok=True)
    alias.symlink_to(root/'current')
    os.replace(alias, layout/'opt/zmalacall/current')
    sync_directory(layout/'opt/zmalacall')
    for name in ('zmalacall-update-recover.service', 'zmalacall-updater.service', 'zmalacall-update-screen.service'):
        content = (source/'build_tools/linux'/name).read_text().replace('@USER@', user)
        (layout/'etc/systemd/system'/name).write_text(content)
    for name in ('zmalacall-display.service', 'zmalacall-pairing.service',
                 'zmalacall-compositor.service', 'zmalacall-cec.service'):
        content = (source/'build_tools/linux'/name).read_text().replace('@USER@', user)
        (layout/'etc/systemd/system'/name).write_text(content)
    dropin = layout/'etc/systemd/system/zmalacall-terminal.service.d'
    dropin.mkdir(exist_ok=True)
    (dropin/'updater.conf').write_text('[Unit]\nRequires=zmalacall-update-recover.service\nAfter=zmalacall-update-recover.service\n')
    sync_directory(configuration)
    sync_directory(layout/'etc/systemd/system')
    run('systemctl', 'daemon-reload')
    run('systemctl', 'enable', 'zmalacall-updater.service')
    run('systemctl', 'start', 'zmalacall-terminal.service')
    run('systemctl', 'start', 'zmalacall-updater.service')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT)
    parser.add_argument('--user', required=True)
    arguments = parser.parse_args()
    install(arguments.source, arguments.user)
