"""Signed application manifests and bounded extraction; never execute package hooks."""
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import tarfile
from urllib.parse import urlsplit
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from zmala_terminal.linux.update_transaction import RecoveryError, sync_directory

MAX_PACKAGE = 256 * 1024 * 1024
MAX_EXPANDED = 512 * 1024 * 1024
MAX_FILE = 64 * 1024 * 1024
MAX_ENTRIES = 5000


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RecoveryError('Duplicate manifest field')
        result[key] = value
    return result


# @llr LLR-TERM-MAINT-024
def verify_manifest(data, keys, compatibility, installed_sequence):
    if len(data) > 65536:
        raise RecoveryError('Manifest too large')
    try:
        envelope = json.loads(data, object_pairs_hook=unique_object)
        payload = envelope['payload']
        key = keys[envelope['key_id']]
        signature = base64.b64decode(envelope['signature'], validate=True)
        Ed25519PublicKey.from_public_bytes(key).verify(signature, canonical(payload))
        if payload['schema'] != 1 or payload['compatibility'] != compatibility:
            raise RecoveryError('Incompatible release')
        sequence = payload['sequence']
        if type(sequence) is not int or sequence <= installed_sequence:
            raise RecoveryError('Release is not newer')
        if not re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', payload['version']):
            raise RecoveryError('Invalid version')
        if not re.fullmatch(r'[0-9a-f]{40}', payload['commit']):
            raise RecoveryError('Invalid commit')
        package = payload['package']
        if type(package['size']) is not int or not 0 < package['size'] <= MAX_PACKAGE:
            raise RecoveryError('Invalid package size')
        if not re.fullmatch(r'[a-f0-9]{64}', package['sha256']):
            raise RecoveryError('Invalid package hash')
        url = urlsplit(package['url'])
        expected = '/toastfr35/ZmalaCall/releases/download/v' + payload['version'] + '/ZmalaTerminal-Update.tar.gz'
        if url.scheme != 'https' or url.netloc != 'github.com' or url.path != expected or url.query or url.fragment:
            raise RecoveryError('Invalid package address')
        return payload
    except RecoveryError:
        raise
    except Exception as error:
        raise RecoveryError('Untrusted update manifest') from error


# @llr LLR-TERM-MAINT-024
def verify_package(path, manifest):
    path = Path(path)
    if path.is_symlink() or path.stat().st_size != manifest['package']['size']:
        raise RecoveryError('Package size mismatch')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    if digest.hexdigest() != manifest['package']['sha256']:
        raise RecoveryError('Package hash mismatch')


def allowed_path(name):
    path = PurePosixPath(name)
    if not name or '\\' in name or path.is_absolute() or any(part in ('', '.', '..') for part in name.split('/')):
        return False
    if any(part.startswith('.') or part in ('data', 'models', 'framing-runtime', 'turn-runtime', '__pycache__', 'floorplan') for part in path.parts):
        return False
    return (name.startswith(('zmala_terminal/common/', 'zmala_terminal/linux/'))
            or name == 'build_tools/linux/build-media.sh')


# @llr LLR-TERM-MAINT-024
def extract_package(package, destination):
    """Destination is a new private directory, removed by the caller on failure.

    Validate the entire archive first. Manually create regular files; tar metadata,
    ownership, modes, links and extraction hooks never reach the filesystem.
    """
    destination = Path(destination)
    destination.mkdir(mode=0o700, parents=False, exist_ok=False)
    with tarfile.open(package, 'r:gz') as archive:
        entries = []
        seen = set()
        total = 0
        for member in archive:
            if len(entries) >= MAX_ENTRIES or not member.isfile() or not allowed_path(member.name):
                raise RecoveryError('Unsafe update archive')
            if member.name in seen or member.size < 0 or member.size > MAX_FILE:
                raise RecoveryError('Invalid update entry')
            seen.add(member.name)
            total += member.size
            if total > MAX_EXPANDED:
                raise RecoveryError('Expanded update too large')
            entries.append(member)
        if not entries:
            raise RecoveryError('Empty update archive')
        for member in entries:
            target = destination / member.name
            target.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                raise RecoveryError('Unreadable update entry')
            with source, target.open('xb') as output:
                remaining = member.size
                while remaining:
                    block = source.read(min(1024 * 1024, remaining))
                    if not block:
                        raise RecoveryError('Truncated update entry')
                    output.write(block)
                    remaining -= len(block)
                output.flush()
                os.fchmod(output.fileno(), 0o644)
                os.fsync(output.fileno())
        # Child entries must become durable before their parent links.
        for directory, _, _ in os.walk(destination, topdown=False):
            sync_directory(directory)
    sync_directory(destination.parent)
