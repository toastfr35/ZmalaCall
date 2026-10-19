"""Private CI inputs, public release notes and fail-closed nine-asset publication."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from build_tools.release.assemble import ASSETS  # noqa: E402


def version_tag():
    text = (ROOT / 'zmala_phone/app/build.gradle').read_text(encoding='utf-8')
    version = re.search(r"versionName '([0-9]+\.[0-9]+\.[0-9]+)'", text).group(1)
    tag = os.environ.get('RELEASE_TAG', '')
    if tag != 'v' + version:
        raise ValueError('Release tag must match the Android version: v' + version)
    return tag


def private_paths():
    temp = Path(os.environ['RUNNER_TEMP']).resolve()
    return temp / 'android-release.p12', temp / 'android-release.json', ROOT / 'zmala_phone/app/google-services.json'


def prepare_signing():
    key, config, firebase = private_paths()
    names = ('ZMALA_ANDROID_KEYSTORE_BASE64', 'ZMALA_ANDROID_SIGNING_JSON', 'ZMALA_FIREBASE_CLIENT_JSON')
    if any(not os.environ.get(name) for name in names):
        raise ValueError('Configure the three Zmala Android Actions secrets before releasing')
    signing = json.loads(os.environ[names[1]])
    for name in ('storePassword', 'keyAlias', 'keyPassword', 'certificateSha256'):
        if not signing.get(name):
            raise ValueError('Incomplete signing configuration')
    client = json.loads(os.environ[names[2]])
    if not any(c.get('client_info', {}).get('android_client_info', {}).get('package_name') == 'org.zmala.phone'
               for c in client.get('client', [])):
        raise ValueError('Firebase configuration does not belong to org.zmala.phone')
    key_bytes = base64.b64decode(os.environ[names[0]], validate=True)
    signing['storeFile'] = str(key)
    for path, content in ((key, key_bytes), (config, json.dumps(signing).encode()),
                          (firebase, json.dumps(client).encode())):
        # Exclusive creation, restrictive mode from the first write, never log contents.
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as stream:
            stream.write(content)
    print('Private release inputs prepared.')


def checked_assets(folder):
    if {p.name for p in folder.iterdir()} != set(ASSETS):
        raise ValueError('Release directory must contain exactly the nine approved assets')
    paths = [folder / name for name in ASSETS]
    if any(p.is_symlink() or not p.is_file() or not p.stat().st_size for p in paths):
        raise ValueError('Invalid release asset')
    return paths


def notes(folder, output):
    tag = version_tag()
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    repo = 'https://github.com/toastfr35/ZmalaCall'
    text = f'''ZmalaCall {tag}: Pi terminal, Pi server and ZmalaPhone.

Download the **Installation.pdf**, **Guide.pdf** and installer for the product you need below.
The two `.exe` files run on a Windows PC and install onto the Pi over wired Ethernet.
The APK installs directly on Android 9 or newer (64-bit ARM phones).

- Pi OS: Raspberry Pi OS Lite 64-bit, Debian 13 Trixie. Terminal: Pi 4 Model B; server: Pi 3 B/B+ or Pi 4 B.
- ZmalaPhone: scan the private App QR supplied by your administrator. Allow notifications for incoming alerts.
- Earlier development APKs use a different signing key. Obtain your setup QR before uninstalling a development copy; future signed releases install as updates.
- Windows installers are unsigned. Android uses the retained ZmalaPhone release certificate.
- Remote calls require the server TLS/TURN configuration; the basic Pi installer does not enable internet access automatically.

Built from [{commit[:12]}]({repo}/tree/{commit}). Both installers pass packaged GUI/headless smoke tests. The Android job runs portable JVM tests, release lint, signature and manifest checks. These checks do not replace physical call testing.

### Source and licenses

No source packages are attached. The exact project source, build scripts and local native corrections are available at [this commit]({repo}/tree/{commit}).
ZmalaPhone uses the AGPL-3.0-or-later Linphone SDK; see [source and dependency notices]({repo}/blob/{commit}/zmala_phone/NOTICE.md) and the [license]({repo}/blob/{commit}/zmala_phone/LICENSE.txt).
The SDK and external component source locations are linked there. GitHub automatically adds its own source ZIP/tar links.

### SHA-256 checksums

```text
'''
    for path in checked_assets(folder):
        text += hashlib.sha256(path.read_bytes()).hexdigest() + '  ' + path.name + '\n'
    output.write_text(text + '```\n', encoding='utf-8')


def publish(folder, notes_file):
    tag = version_tag()
    paths = checked_assets(folder)
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    # Create a draft, upload each allowlisted file, verify names, then publish.
    # Existing releases are never replaced; a failed draft is left for inspection.
    subprocess.run(['gh', 'release', 'create', tag, '--target', commit, '--draft',
                    '--title', 'ZmalaCall ' + tag, '--notes-file', str(notes_file)], cwd=ROOT, check=True)
    subprocess.run(['gh', 'release', 'upload', tag, *map(str, paths)], cwd=ROOT, check=True)
    uploaded = json.loads(subprocess.check_output(
        ['gh', 'release', 'view', tag, '--json', 'assets'], cwd=ROOT, text=True))['assets']
    if {item['name'] for item in uploaded} != set(ASSETS) or any(item['state'] != 'uploaded' for item in uploaded):
        raise ValueError('Uploaded release assets did not match; draft retained')
    subprocess.run(['gh', 'release', 'edit', tag, '--draft=false', '--latest'], cwd=ROOT, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('check-version', 'prepare-signing', 'cleanup-signing', 'notes', 'publish'))
    parser.add_argument('--assets', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--notes', type=Path)
    args = parser.parse_args()
    if args.action == 'check-version':
        print(version_tag())
    elif args.action == 'prepare-signing':
        prepare_signing()
    elif args.action == 'cleanup-signing':
        for path in private_paths():
            path.unlink(missing_ok=True)
    elif args.action == 'notes':
        notes(args.assets, args.output)
    elif args.action == 'publish':
        publish(args.assets, args.notes)


if __name__ == '__main__':
    main()
