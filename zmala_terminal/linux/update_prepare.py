"""Prepare immutable application slots using only already installed host dependencies."""
import json
import os
from pathlib import Path
import pwd
import shutil
import stat
import subprocess
import uuid
from zmala_terminal.linux.update_package import extract_package, verify_package, MAX_EXPANDED
from zmala_terminal.linux.update_transaction import RecoveryError, sync_directory

class StorageUnavailable(RecoveryError):
    pass


BUILD_FILES = ('build-media.sh', 'build-turn.py')
RUNTIME_FILES = ('kiosk-session.py', 'launcher.py', 'tv-plugin-self-test.py',
                 'tv-plugin-self-test.sh', 'tv_plugin_self_test.py', 'tv_test_camera.py',
                 'tv_test_card.py', 'tv_test_processes.py', 'pair-samsung-tv.py')


def freeze(root):
    for directory, _, files in os.walk(root, topdown=False, followlinks=False):
        for name in files:
            path = Path(directory)/name
            if path.is_symlink():
                continue
            os.chown(path, 0, 0)
            path.chmod(0o755 if path.suffix == '.sh' or path.stat().st_mode & 0o111 else 0o644)
            with path.open('rb') as stream:
                os.fsync(stream.fileno())
        os.chown(directory, 0, 0)
        Path(directory).chmod(0o755)
        sync_directory(directory)


def validate_built_tree(root):
    """An unprivileged compiler must not leave root-followed links or devices."""
    for directory, directories, files in os.walk(root, followlinks=False):
        for name in directories + files:
            info = (Path(directory)/name).lstat()
            if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
                raise RecoveryError('Unsupported prepared entry')
            if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
                raise RecoveryError('Linked prepared file')


# @llr LLR-TERM-MAINT-030
def probe_release(stage, builder, run):
    """Exercise the real native core against disposable data and no hardware/network."""
    probe = '''import pathlib,sys,ctypes,time
root=pathlib.Path(sys.argv[1]);sys.path.insert(0,str(root))
for path in (root/'zmala_terminal').rglob('*.py'):compile(path.read_bytes(),str(path),'exec')
for name in ('zmala_terminal/linux/media/video/libzmala_video.so','zmala_terminal/linux/media/audio/libzmala_speech_audio.so','zmala_terminal/linux/turn-runtime/turn-fix.so'):ctypes.CDLL(str(root/name))
from zmala_terminal.common.engine import Engine
engine=Engine({},lambda *args:None,lambda *args:None,profile='updater-probe',defer_media=True)
try:
    for _ in range(10):engine.iterate();time.sleep(.05)
finally:engine.close()
'''
    run(['systemd-run', '--wait', '--collect', '--pipe',
         '--unit=zmalacall-update-check-'+uuid.uuid4().hex, '--uid='+builder,
         '--property=PrivateNetwork=yes', '--property=PrivateDevices=yes',
         '--property=PrivateTmp=yes', '--property=ProtectHome=yes',
         '--property=ProtectSystem=strict', '--property=NoNewPrivileges=yes',
         '--property=ReadWritePaths='+str(stage), '--property=MemoryMax=512M',
         '--property=RuntimeMaxSec=60', '/usr/bin/python3', '-c', probe, str(stage)],
        check=True, capture_output=True, text=True, timeout=90)


# @llr LLR-TERM-MAINT-030
def prepare_release(transactions, manifest, package, config, run=subprocess.run):
    verify_package(package, manifest)
    confirmed = transactions.read('confirmed')
    if not confirmed:
        raise RecoveryError('No confirmed release')
    working = transactions.slot(confirmed['slot'])
    identity = 'r' + str(manifest['sequence']) + '-' + manifest['package']['sha256'][:16]
    target = transactions.slots/identity
    if target.is_symlink():
        raise RecoveryError("Unsafe candidate slot")
    if target.exists():
        record = json.loads((target/'update-release.json').read_text())
        if record.get('digest') != manifest['package']['sha256']:
            raise RecoveryError('Conflicting candidate slot')
        transactions.prepare(identity)
        return identity
    runtime_size = sum(path.stat().st_size for name in ('framing-runtime', 'models')
                       for path in (working/'zmala_terminal/linux/media'/name).rglob('*')
                       if path.is_file() and not path.is_symlink())
    if shutil.disk_usage(transactions.root).free < MAX_EXPANDED + runtime_size + 512*1024*1024:
        raise StorageUnavailable('Insufficient update storage')
    stage = transactions.root/('.preparing-' + uuid.uuid4().hex)
    try:
        extract_package(package, stage)
        helpers = stage/'build_tools/linux'
        helpers.mkdir(parents=True, exist_ok=True)
        for name in RUNTIME_FILES:
            source = working/'build_tools/linux'/name
            if not (helpers/name).exists() and source.is_file():
                shutil.copy2(source, helpers/name)
        for name in ('framing-runtime', 'models'):
            source = working/'zmala_terminal/linux/media'/name
            if source.is_dir():
                shutil.copytree(source, stage/'zmala_terminal/linux/media'/name, symlinks=False)
        if not (helpers/'kiosk-session.py').is_file() or not (helpers/'launcher.py').is_file():
            raise RecoveryError('Missing application launcher')
        builder = pwd.getpwnam(config.get('builder', 'zmalaupdate'))
        if builder.pw_uid == 0:
            raise RecoveryError('Builder must be unprivileged')
        for directory, _, files in os.walk(stage):
            os.chown(directory, builder.pw_uid, builder.pw_gid)
            for name in files:
                os.chown(Path(directory)/name, builder.pw_uid, builder.pw_gid)
        commands = [('/bin/sh', str(helpers/'build-media.sh')),
                    ('/usr/bin/python3', str(helpers/'build-turn.py'))]
        for command in commands:
            unit = 'zmalacall-update-build-' + uuid.uuid4().hex
            run(['systemd-run', '--wait', '--collect', '--pipe', '--unit='+unit,
                 '--uid='+builder.pw_name, '--property=PrivateNetwork=yes',
                 '--property=PrivateTmp=yes', '--property=PrivateDevices=yes',
                 '--property=ProtectHome=yes', '--property=ProtectSystem=strict',
                 '--property=NoNewPrivileges=yes', '--property=RestrictSUIDSGID=yes',
                 '--property=ReadWritePaths='+str(stage), '--property=MemoryMax=768M',
                 '--property=RuntimeMaxSec=300', '--property=Nice=10',
                 '--property=CPUWeight=10', '--property=IOWeight=10',
                 '/usr/bin/env', 'ZMALA_OFFLINE_BUILD=1', *command],
                check=True, capture_output=True, text=True, timeout=330)
        data = stage/'zmala_terminal/data'
        if data.exists() or data.is_symlink():
            raise RecoveryError('Payload contains persistent state')
        data.mkdir(mode=0o700)
        os.chown(data, builder.pw_uid, builder.pw_gid)
        probe_release(stage, builder.pw_name, run)
        validate_built_tree(stage)
        shutil.rmtree(data)
        data.symlink_to(config.get('data', '/var/lib/zmalacall'), target_is_directory=True)
        record = {'owned_by_updater': 1, 'version': manifest['version'],
                  'sequence': manifest['sequence'], 'digest': manifest['package']['sha256']}
        (stage/'update-release.json').write_text(json.dumps(record), encoding='utf-8')
        freeze(stage)
        os.replace(stage, target)
        sync_directory(transactions.slots)
        sync_directory(transactions.root)
        transactions.prepare(identity)
        return identity
    finally:
        if stage.exists() and not stage.is_symlink() and stage.parent.resolve() == transactions.root.resolve():
            shutil.rmtree(stage)
