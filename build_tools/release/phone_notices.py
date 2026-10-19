"""Refresh packaged license texts from pinned public SDK source repositories."""
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import json
from pathlib import Path
import subprocess
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
LEGAL_NAMES = {'license', 'license.txt', 'license.md', 'copying', 'copying.txt',
               'notice', 'notice.txt', 'copyright', 'copying.lesser', 'patents'}


def git(repo, *args):
    return subprocess.run(['git', '-C', str(repo), *args], check=True,
                          capture_output=True, timeout=180).stdout


def decode(content):
    try:
        return content.decode('utf-8')
    except UnicodeDecodeError:
        return content.decode('latin-1')


def module_notices(module):
    path = module['path']
    repo = ROOT / 'build_tools/tmp/license-sources' / path
    if not repo.exists():
        repo.mkdir(parents=True)
        git(repo, 'init', '--bare')
    present = subprocess.run(['git', '-C', str(repo), 'cat-file', '-e', module['commit']],
                             capture_output=True).returncode == 0
    if not present:
        git(repo, 'fetch', '--depth=1', '--filter=blob:none', module['repository'], module['commit'])
    paths = git(repo, 'ls-tree', '-r', '--name-only', module['commit']).decode().splitlines()
    names = [p for p in paths if Path(p).name.lower() in LEGAL_NAMES]
    if not names and path == 'external/bv16-floatingpoint':
        header = git(repo, 'show', module['commit'] + ':bv16/bv16cnst.h').decode()
        return [(path + '/bv16/bv16cnst.h (license header)', '\n'.join(header.splitlines()[:21]))]
    if not names and path == 'external/sqlite3':
        header = git(repo, 'show', module['commit'] + ':sqlite3.c').decode()
        return [(path + '/sqlite3.c (public-domain dedication)', header[:header.index('*/') + 2])]
    if not names:
        raise ValueError('Review missing license text for ' + path)
    bundle = git(repo, 'archive', module['commit'], *names)
    result = []
    with tarfile.open(fileobj=BytesIO(bundle)) as archive:
        for member in archive:
            if member.isfile():
                result.append((path + '/' + member.name, decode(archive.extractfile(member).read())))
    print(path + ': ' + str(len(result)) + ' notices')
    return result


def main():
    manifest = json.loads((ROOT / 'zmala_phone/SDK-SOURCES.json').read_text(encoding='utf-8'))
    texts = []
    for name in manifest['sdk_license_files']:
        url = ('https://raw.githubusercontent.com/BelledonneCommunications/linphone-sdk/'
               + manifest['sdk_commit'] + '/' + name)
        with urllib.request.urlopen(url, timeout=30) as response:
            texts.append((name, decode(response.read())))
    with ThreadPoolExecutor(max_workers=6) as pool:
        for result in pool.map(module_notices, manifest['submodules']):
            texts.extend(result)
    output = ROOT / 'zmala_phone/app/src/main/assets/licenses'
    output.mkdir(parents=True, exist_ok=True)
    body = ('Linphone SDK 5.5.32 and external-component license texts.\n'
            'This inventory includes optional components; not every component is enabled.\n'
            'Exact repositories and revisions: zmala_phone/SDK-SOURCES.json in the project source.\n\n')
    for name, text in texts:
        body += '=' * 72 + '\n' + name + '\n' + '=' * 72 + '\n' + text + '\n\n'
    # Normalize source line endings; preserve the actual notice text.
    body = '\n'.join(line.expandtabs().rstrip() for line in body.splitlines()).rstrip() + '\n'
    (output / 'LINPHONE-NOTICES.txt').write_text(body, encoding='utf-8', newline='\n')
    (output / 'AGPL-3.0.txt').write_bytes((ROOT / 'zmala_phone/LICENSE.txt').read_bytes())
    (output / 'NOTICE.txt').write_bytes((ROOT / 'zmala_phone/NOTICE.md').read_bytes())
    (output / 'SDK-SOURCES.json').write_bytes((ROOT / 'zmala_phone/SDK-SOURCES.json').read_bytes())
    with urllib.request.urlopen('https://www.apache.org/licenses/LICENSE-2.0.txt', timeout=30) as response:
        (output / 'APACHE-2.0.txt').write_bytes(response.read())
    print('Packaged ' + str(len(texts)) + ' pinned source notices.')


if __name__ == '__main__':
    main()
