"""Build and verify a signed Android APK. Never creates or publishes signing keys."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]


def run(args, env, capture=False):
    return subprocess.run([str(arg) for arg in args], cwd=ROOT, env=env, check=True,
                          text=True, encoding='utf-8', capture_output=capture)


def verify_manifest(xml):
    manifest = ET.fromstring(xml)
    android = '{http://schemas.android.com/apk/res/android}'
    app = manifest.find('application')
    if manifest.get('package') != 'org.zmala.phone' or app is None:
        raise ValueError('Wrong application in release APK')
    if app.get(android + 'debuggable', 'false') != 'false':
        raise ValueError('Release APK is debuggable')
    if app.get(android + 'testOnly', 'false') != 'false':
        raise ValueError('Release APK is test-only')
    if app.get(android + 'allowBackup') != 'false':
        raise ValueError('Release APK enables app-data backup')
    return manifest.get(android + 'versionName'), manifest.get(android + 'versionCode')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--signing', type=Path,
                        default=Path.home() / '.zmala/signing/android-release.json')
    args = parser.parse_args()
    signing_file = args.signing.resolve()
    if signing_file.is_relative_to(ROOT):
        parser.error('Keep signing credentials outside the checkout')
    signing = json.loads(signing_file.read_text(encoding='utf-8'))
    for name in ('storeFile', 'storePassword', 'keyAlias', 'keyPassword', 'certificateSha256'):
        if not signing.get(name):
            parser.error('Incomplete private signing configuration: ' + name)
    if Path(signing['storeFile']).resolve().is_relative_to(ROOT):
        parser.error('Keep the keystore outside the checkout')
    env = os.environ.copy()
    env['ZMALA_RELEASE_SIGNING'] = str(signing_file)
    sdk = Path(env['ANDROID_HOME'])
    suffix = '.bat' if os.name == 'nt' else ''
    gradle = ROOT / 'zmala_phone' / ('gradlew.bat' if os.name == 'nt' else 'gradlew')
    run([gradle, '-p', 'zmala_phone', '--no-daemon', ':app:testDebugUnitTest',
         ':app:lintRelease', ':app:assembleRelease'], env)
    apk = ROOT / 'zmala_phone/app/build/outputs/apk/release/app-release.apk'
    tools = sdk / 'build-tools/37.0.0'
    signature = run([tools / ('apksigner' + suffix), 'verify', '--verbose',
                     '--print-certs', apk], env, True).stdout
    fingerprint = signing['certificateSha256'].lower().replace(':', '')
    fingerprints = re.findall(r'certificate SHA-256 digest: ([0-9a-f]+)', signature)
    if not fingerprints or set(fingerprints) != {fingerprint} or 'Number of signers: 1' not in signature:
        raise ValueError('Unexpected APK signing certificate')
    run([tools / ('zipalign.exe' if os.name == 'nt' else 'zipalign'),
         '-c', '-P', '16', '4', apk], env, True)
    manifest = run([sdk / 'cmdline-tools/latest/bin' / ('apkanalyzer' + suffix),
                    'manifest', 'print', apk], env, True).stdout
    version, code = verify_manifest(manifest)
    destination = ROOT / 'build_tools/dist' / ('ZmalaPhone-' + version)
    destination.mkdir(parents=True, exist_ok=True)
    output = destination / ('ZmalaPhone-' + version + '.apk')
    shutil.copy2(apk, output)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    (destination / 'SHA256SUMS.txt').write_text(digest + '  ' + output.name + '\n', encoding='utf-8')
    (destination / 'SIGNATURE.txt').write_text(signature, encoding='utf-8')
    for filename in ('LICENSE.txt', 'NOTICE.md'):
        shutil.copy2(ROOT / 'zmala_phone' / filename, destination / filename)
    for filename in ('server_prep.docx', 'terminal_config.docx'):
        shutil.copy2(ROOT / 'docs' / filename, destination / filename)
    print(f'Verified release {version} (code {code}): {output}')
    print('SHA-256: ' + digest)
    print('Signing certificate SHA-256: ' + fingerprint)
    print('No upload or publication performed.')


if __name__ == '__main__':
    main()
