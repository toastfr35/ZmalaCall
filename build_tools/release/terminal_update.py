"""Build/sign application-only updates. The private key is a release-job input only."""
import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import urllib.request
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from build_tools.release.github_release import android_version  # noqa: E402
from zmala_terminal.linux.update_package import (  # noqa: E402
    allowed_path, canonical, verify_manifest, verify_package, MAX_PACKAGE, MAX_EXPANDED, MAX_FILE, MAX_ENTRIES,
)

COMPATIBILITY = {'architecture': 'aarch64', 'os': 'trixie', 'sdk': '5.3.105',
                 'updater': 1, 'data': 1, 'host': 3}
KEY_ID = 'terminal-release-2026-01'
UPSTREAM = {
    'turn_tcp.cpp': '95c98be983d7d547c88569438b8e7094309c989d4f4ea7b815a47036a425ac31',
    'turn_tcp.h': '77590e754ae896fee4414885d114d99b229333623cd180cfdc8d2438ab600ade',
}
EXTRA = ('build-media.sh', 'build-turn.py', 'kiosk-session.py', 'launcher.py',
         'tv-plugin-self-test.py', 'tv-plugin-self-test.sh', 'tv_plugin_self_test.py',
         'tv_test_camera.py', 'tv_test_card.py', 'tv_test_processes.py', 'pair-samsung-tv.py')
NATIVE_TESTS = ('tests/terminal/LLT/turn_parser.cpp', 'tests/terminal/LLT/turn_socket_io.cpp',
                'tests/support/native/turn-write-cases.h')
TEXT = {'.py', '.sh', '.json', '.c', '.cpp', '.h', '.patch', '.txt', '.md', '.svg', '.conf', '.rules'}


def upstream_sources():
    result = {}
    for name, expected in UPSTREAM.items():
        url = 'https://raw.githubusercontent.com/BelledonneCommunications/mediastreamer2/5.3.105/src/voip/'+name
        with urllib.request.urlopen(url, timeout=30) as response:
            data = response.read(2*1024*1024+1)
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError('Unexpected pinned native source')
        result[name] = data
    return result


def package(root, output, upstream, tracked=None):
    if tracked is None:
        tracked = subprocess.check_output(['git', 'ls-files', '-z', '--', 'zmala_terminal/common',
                                          'zmala_terminal/linux'], cwd=root).decode().split('\0')
    names = sorted({name for name in tracked if name and allowed_path(name)
                    and Path(name).suffix not in ('.so', '.o', '.pyc')}
                   | {'build_tools/linux/'+name for name in EXTRA} | set(NATIVE_TESTS))
    entries = {}
    for name in names:
        path = root/name
        if path.is_symlink() or not path.is_file() or not allowed_path(name):
            raise ValueError('Invalid application source: '+name)
        content = path.read_bytes()
        if path.suffix in TEXT:
            content = content.replace(b'\r\n', b'\n')
        entries[name] = content
    for name, expected in UPSTREAM.items():
        data = upstream[name]
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError('Unexpected pinned native source')
        entries['zmala_terminal/linux/native/upstream/'+name] = data
    if (len(entries) > MAX_ENTRIES or sum(map(len, entries.values())) > MAX_EXPANDED
            or any(len(data) > MAX_FILE for data in entries.values())):
        raise ValueError('Application payload exceeds terminal limits')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, 'w:gz', format=tarfile.USTAR_FORMAT) as archive:
        for name, data in sorted(entries.items()):
            member = tarfile.TarInfo(name)
            member.mode = 0o644
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    if output.stat().st_size > MAX_PACKAGE:
        raise ValueError('Compressed application payload exceeds terminal limit')


def sign(payload, private, public_keys):
    key = serialization.load_pem_private_key(private, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError('Expected Ed25519 release key')
    public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    if public_keys.get(KEY_ID) != public:
        raise ValueError('Release key does not match installed public trust')
    return canonical({'payload': payload, 'key_id': KEY_ID,
                      'signature': base64.b64encode(key.sign(canonical(payload))).decode()})


def keys(root):
    return {name: base64.b64decode(value, validate=True)
            for name, value in json.loads((root/'build_tools/linux/update-keys.json').read_text()).items()}


def verify(root, folder):
    version, sequence = android_version((root/'zmala_phone/app/build.gradle').read_text())
    manifest = verify_manifest((folder/'ZmalaTerminal-Update.json').read_bytes(), keys(root), COMPATIBILITY, 0)
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    if (manifest['version'], manifest['sequence'], manifest['commit']) != (version, sequence, commit):
        raise ValueError('Update does not identify the current release commit')
    verify_package(folder/'ZmalaTerminal-Update.tar.gz', manifest)
    with tarfile.open(folder/'ZmalaTerminal-Update.tar.gz', 'r:gz') as archive:
        members = archive.getmembers()
        if (not members or len(members) > MAX_ENTRIES
                or len({member.name for member in members}) != len(members)
                or sum(member.size for member in members) > MAX_EXPANDED
                or any(not member.isfile() or not allowed_path(member.name)
                       or not 0 <= member.size <= MAX_FILE for member in members)):
            raise ValueError('Unsafe application update archive')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('build', 'verify'))
    parser.add_argument('--output', type=Path, default=ROOT/'build_tools/dist')
    args = parser.parse_args()
    if args.action == 'build':
        private = os.environ.get('ZMALA_TERMINAL_UPDATE_KEY', '').encode()
        if not private:
            raise ValueError('Configure the terminal update release signing secret')
        version, sequence = android_version((ROOT/'zmala_phone/app/build.gradle').read_text())
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        package_file = args.output/'ZmalaTerminal-Update.tar.gz'
        package(ROOT, package_file, upstream_sources())
        payload = {'schema': 1, 'version': version, 'sequence': sequence, 'commit': commit,
                   'compatibility': COMPATIBILITY,
                   'package': {'size': package_file.stat().st_size,
                               'sha256': hashlib.sha256(package_file.read_bytes()).hexdigest(),
                               'url': 'https://github.com/toastfr35/ZmalaCall/releases/download/v'+version+'/ZmalaTerminal-Update.tar.gz'}}
        (args.output/'ZmalaTerminal-Update.json').write_bytes(sign(payload, private, keys(ROOT)))
    verify(ROOT, args.output)
    print('Terminal application update signature, identity and payload verified.')


if __name__ == '__main__':
    main()
