"""Stable automatic application updater. No OS/package-manager operations exist here."""
import argparse
import base64
import fcntl
import json
import logging
import os
from pathlib import Path
import platform
import random
import re
import shutil
import stat
import time
from zmala_terminal.linux.update_download import latest_manifest, download
from zmala_terminal.linux.update_package import verify_manifest
from zmala_terminal.linux.update_prepare import prepare_release, StorageUnavailable
from zmala_terminal.linux.update_runtime import Runtime
from zmala_terminal.linux.update_supervisor import TrialSupervisor
from zmala_terminal.linux.update_transaction import Transactions, RecoveryError

CONFIG = '/etc/zmalacall/updater.json'


def trusted_json(path, limit=65536):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, 'r', encoding='utf-8') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022 or info.st_size > limit:
            raise RecoveryError('Untrusted updater configuration')
        value = json.loads(stream.read(limit+1))
    if not isinstance(value, dict):
        raise RecoveryError('Invalid updater configuration')
    return value


def confirmed_release(transactions):
    confirmed = transactions.read('confirmed')
    if not confirmed:
        raise RecoveryError('No confirmed release')
    return trusted_json(transactions.slot(confirmed.get('slot'))/'update-release.json')


def verify_host(config, run):
    release = {}
    for line in Path('/etc/os-release').read_text().splitlines():
        if '=' in line:
            key, value = line.split('=', 1)
            release[key] = value.strip('"')
    sdk = run(['dpkg-query', '-W', '-f=${Version}', 'libmediastreamer2-14']).stdout
    sdk = sdk.split('+')[0].split(':')[-1]
    expected = {'architecture': platform.machine(), 'os': release.get('VERSION_CODENAME'),
                'sdk': sdk, 'updater': 1, 'data': 1, 'host': 1}
    if expected != config['compatibility']:
        raise RecoveryError('Host compatibility changed; installer maintenance required')


# @llr LLR-TERM-MAINT-030
class UpdateService:
    def __init__(self, config, transactions=None, runtime=None):
        self.config = config
        self.transactions = transactions or Transactions(config['root'])
        self.runtime = runtime or Runtime(config, self.transactions)
        self.keys = {name: base64.b64decode(value, validate=True)
                     for name, value in trusted_json(config['keys']).items()}
        if not self.keys or any(len(value) != 32 for value in self.keys.values()):
            raise RecoveryError('No trusted release key')
        self.next_check = time.monotonic() + random.uniform(15, 60)
        self.next_claim = 0
        self.next_report = 0
        self.available = None
        self.last_error = None

    def quarantine(self, digest):
        value = self.transactions.read('quarantine') or {'digests': []}
        value['digests'] = list(dict.fromkeys([*value.get('digests', []), digest]))[-50:]
        self.transactions.write('quarantine', value)

    def quarantined(self, digest):
        value = self.transactions.read('quarantine') or {'digests': []}
        return digest in value.get('digests', [])

    def collect(self):
        confirmed = self.transactions.read('confirmed') or {}
        pending = self.transactions.read('pending') or {}
        keep = {confirmed.get('slot'), confirmed.get('previous')}
        if pending.get('state') in ('ready', 'trial'):
            keep.add(pending.get('candidate'))
        for slot in self.transactions.slots.iterdir():
            if slot.name in keep or slot.is_symlink() or not slot.is_dir():
                continue
            try:
                metadata = trusted_json(slot/'update-release.json')
                if metadata.get('owned_by_updater') != 1:
                    continue
                if slot.parent.resolve() == self.transactions.slots.resolve():
                    shutil.rmtree(slot)
            except (OSError, ValueError, RecoveryError):
                continue
        cache = self.transactions.root/'cache'
        if cache.exists():
            for package in cache.glob('*.tar.gz'):
                if package.is_file() and not package.is_symlink():
                    package.unlink()

    def startup(self):
        # Build helpers are separate systemd cgroups; reap interrupted helpers
        # before removing their private incomplete directories.
        try:
            self.runtime.command(['systemctl', 'stop', 'zmalacall-update-build-*.service', 'zmalacall-update-check-*.service'])
        except Exception:
            pass
        for entry in self.transactions.root.iterdir():
            if (re.fullmatch(r'\.preparing-[a-f0-9]{32}', entry.name) and entry.is_dir()
                    and not entry.is_symlink() and entry.parent.resolve() == self.transactions.root.resolve()):
                shutil.rmtree(entry)
        prior = None
        try:
            prior = trusted_json(self.runtime.request, 8192)
        except (OSError, ValueError, RecoveryError):
            pass
        recovered = self.runtime.recover()
        if prior and prior.get('phase') in ('rollback', 'checking', 'updating', 'recovery_failed') and not recovered:
            self.runtime.nonce = prior['nonce']
            self.runtime.language = prior.get('language', 'en')
            self.runtime.preserve_sleep = prior.get('preserve_sleep') is True
            self.runtime.display('checking')
            recovered = True
        pending = self.transactions.read('pending')
        if pending and pending.get('state') == 'quarantined':
            slot = self.transactions.slot(pending['candidate'])
            metadata = trusted_json(slot/'update-release.json')
            self.quarantine(metadata['digest'])
        if recovered:
            if not TrialSupervisor(self.transactions, self.runtime).healthy():
                self.runtime.display('recovery_failed')
                raise RecoveryError('Recovery application is not ready')
            self.runtime.finish(self.runtime.nonce)
        self.collect()

    def check(self):
        verify_host(self.config, self.runtime.command)
        envelope = latest_manifest()
        if envelope is None:
            return
        installed = confirmed_release(self.transactions)
        # Old/current feeds are normal, not repeated installation attempts.
        try:
            raw = json.loads(envelope)
            if raw.get('payload', {}).get('sequence', -1) <= installed['sequence']:
                return
        except (ValueError, TypeError, AttributeError):
            raise RecoveryError('Invalid update feed') from None
        manifest = verify_manifest(envelope, self.keys, self.config['compatibility'], installed['sequence'])
        digest = manifest['package']['sha256']
        if self.quarantined(digest):
            return
        self.available = manifest['version']
        pending = self.transactions.read('pending')
        if pending and pending.get('state') in ('ready', 'trial'):
            return
        package = download(manifest, self.transactions.root/'cache', self.runtime.publish)
        attempt = self.transactions.read('preparing')
        count = attempt.get('attempts', 0)+1 if attempt and attempt.get('digest') == digest else 1
        if count > 2:
            self.quarantine(digest)
            raise RecoveryError('Preparation repeatedly interrupted')
        self.transactions.write('preparing', {'digest': digest, 'attempts': count})
        try:
            prepare_release(self.transactions, manifest, package, self.config)
            self.transactions.write('preparing', {'digest': digest, 'attempts': 0})
            self.last_error = None
        except StorageUnavailable:
            self.last_error = "insufficient_space"
            raise
        except Exception:
            self.quarantine(digest)
            self.last_error = 'preparation_failed'
            raise

    def tick(self):
        now = time.monotonic()
        self.runtime.publish()
        pending = self.transactions.read('pending')
        if pending and pending.get('state') == 'ready' and now >= self.next_claim:
            self.next_claim = now + 30
            result = TrialSupervisor(self.transactions, self.runtime).activate()
            if result == 'rolled_back':
                metadata = trusted_json(self.transactions.slot(pending['candidate'])/'update-release.json')
                self.quarantine(metadata['digest'])
                self.last_error = 'candidate_failed'
            if result != 'waiting':
                self.collect()
        if now >= self.next_check:
            self.next_check = now + random.uniform(270, 330)
            try:
                self.check()
            except Exception as error:
                # Network exceptions may contain private server/CDN URLs. Report
                # only a bounded category; keep the confirmed application running.
                self.last_error = self.last_error or 'update_unavailable'
                logging.warning('Application update check failed (%s)', type(error).__name__)


def boot_recover(config):
    transactions = Transactions(config['root'])
    pending = None
    try:
        pending = transactions.read('pending')
    except RecoveryError:
        pass
    transactions.recover()
    runtime = Runtime(config, transactions)
    runtime.restore_data()
    if pending and pending.get('state') == 'trial':
        runtime.language = pending.get('language', 'en')
        runtime.preserve_sleep = pending.get('preserve_sleep') is True
        runtime.phase = 'rollback'
    runtime.publish()


# @llr LLR-TERM-MAINT-030
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=('run', 'recover'))
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise RecoveryError('Updater service requires root')
    config = trusted_json(CONFIG)
    if args.operation == 'recover':
        boot_recover(config)
        return
    with open('/run/lock/zmalacall-update.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        service = UpdateService(config)
        service.startup()
        while True:
            service.tick()
            time.sleep(1)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main()
