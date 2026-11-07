"""Retain committed application sources and integrity-pinned, script-free JS inputs.

This is build tooling. It never reads a user's npm configuration, runs package
scripts, changes installed applications, or accepts live enrollment/credentials.
"""
import base64
import ast
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
import urllib.parse
import urllib.request

from zmala_system.host_layout import ROLES
from . import package_lock, project, root_build

MAX_FILE = 32*1024**2
MAX_TOTAL = 256*1024**2
MAX_FILES = 50000
MARKER = 'ZMALA-APPLICATIONS.json'
TEXT = {'.py', '.sh', '.js', '.cjs', '.json', '.service', '.conf', '.rules', '.txt',
        '.c', '.cpp', '.h', '.md', '.svg', '.patch', '.html', '.css', '.ts', '.gradle'}


def path_name(value):
    """Keep archive names relative and unambiguous on Linux and Windows hosts."""
    path = PurePosixPath(value)
    if (not value or path.is_absolute() or path.as_posix() != value or '..' in path.parts
            or '\\' in value or '\0' in value or len(value.encode()) > 4096
            or any(':' in part or part.rstrip(' .') != part for part in path.parts)):
        # A POSIX-relative name can still be a Windows drive/alternate stream;
        # trailing dots/spaces can alias a different path on Windows as well.
        raise ValueError('Unsafe application input path')
    return path


def read_tar(path, prefix=None):
    """Validate an entire bounded file-only input before writing any member."""
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_TOTAL+MAX_FILES*1024:
        raise ValueError('Expected a bounded regular application archive')
    records, total, seen = {}, 0, set()
    with tarfile.open(path, 'r:*') as archive:
        for member in archive:
            name = member.name.rstrip('/')
            path_name(name)
            if name in seen or len(seen) >= MAX_FILES:
                raise ValueError('Duplicate or excessive application archive members')
            seen.add(name)
            if member.isdir():
                continue
            if not member.isfile() or not 0 <= member.size <= MAX_FILE:
                raise ValueError('Application inputs must contain bounded regular files only')
            if prefix:
                if not name.startswith(prefix+'/'):
                    raise ValueError('Unexpected dependency archive prefix')
                name = name[len(prefix)+1:]
            path_name(name)
            total += member.size
            if total > MAX_TOTAL:
                raise ValueError('Expanded application input exceeds budget')
            records[name] = (archive.extractfile(member).read(), member.mode & 0o111 != 0)
    for name in records:
        if any(str(parent) in records for parent in PurePosixPath(name).parents):
            raise ValueError('Application file is also an archive parent')
    return records


def write_files(root, records):
    for name, (body, executable) in sorted(records.items()):
        target = root/name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(body)
        target.chmod(0o755 if executable else 0o644)


def source_paths(role):
    if role not in ROLES:
        raise ValueError('Unsupported application role')
    paths = ['build_tools/linux', 'zmala_phone/app/build.gradle']
    if role in ('terminal', 'combined'):
        paths += ['zmala_terminal/common', 'zmala_terminal/linux',
                  'tests/terminal/LLT/turn_parser.cpp', 'tests/terminal/LLT/turn_socket_io.cpp',
                  'tests/support/native/turn-write-cases.h']
    if role in ('server', 'combined'):
        paths += ['zmala_server', 'build_tools/build-admin.cjs', 'build_tools/convert-photo.py',
                  'build_tools/assets/installation-connections.png']
        if role == 'server':
            paths += ['zmala_terminal/common/shared/terminal-languages.json',
                      'zmala_terminal/common/assets/gentle-chime.wav',
                      'zmala_terminal/common/assets/presenter-pairing.png']
    return paths


def npm_entries(lock):
    if lock.get('lockfileVersion') != 3 or not isinstance(lock.get('packages'), dict):
        raise ValueError('Expected the reviewed npm v3 package lock')
    entries = []
    for name, value in lock['packages'].items():
        if name in ('', 'vendor/sip'):
            continue
        path_name(name)
        if not name.startswith('node_modules/') or any(value.get(k) for k in
                ('dev', 'optional', 'hasInstallScript', 'os', 'cpu')):
            raise ValueError('Unqualified npm dependency kind')
        if value.get('link'):
            if name != 'node_modules/sip' or value.get('resolved') != 'vendor/sip':
                raise ValueError('Unqualified local npm dependency')
            continue
        uri, integrity = value.get('resolved', ''), value.get('integrity', '')
        parsed = urllib.parse.urlsplit(uri)
        if (parsed.scheme != 'https' or parsed.netloc != 'registry.npmjs.org'
                or parsed.query or parsed.fragment or not parsed.path.endswith('.tgz')
                or not re.fullmatch(r'sha512-[A-Za-z0-9+/]+={0,2}', integrity)):
            raise ValueError('npm dependency needs a pinned public registry archive and SHA-512')
        expected = base64.b64decode(integrity[7:], validate=True)
        if len(expected) != 64:
            raise ValueError('Invalid npm archive integrity length')
        entries.append((name, uri, expected))
    if not 0 < len(entries) < 200:
        raise ValueError('Unexpected npm dependency count')
    return entries


def acquire_dependency(entry, cache, opener=urllib.request.urlopen):
    name, uri, expected = entry
    path = cache/(hashlib.sha256(uri.encode()).hexdigest()+'.tgz')
    digest, count = hashlib.sha512(), 0
    with opener(uri, timeout=60) as response, path.open('xb') as stream:
        if response.geturl() != uri:
            raise ValueError('Unexpected npm archive redirect')
        while block := response.read(1024**2):
            count += len(block)
            if count > MAX_FILE:
                raise ValueError('npm archive download exceeds budget')
            digest.update(block)
            stream.write(block)
    if digest.digest() != expected:
        raise ValueError('npm archive differs from package-lock integrity')
    return name, path


def turn_sources(script, cache, opener=urllib.request.urlopen):
    """Retain the existing builder's pinned SDK sources before network isolation."""
    tree = ast.parse(script.decode('utf-8'))
    assignments = [node for node in tree.body if isinstance(node, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id == 'HASHES' for target in node.targets)]
    if len(assignments) != 1 or b"!= '5.3.105'" not in script:
        raise ValueError('Requalify application intake for the changed TURN builder')
    hashes = ast.literal_eval(assignments[0].value)
    if (set(hashes) != {'turn_tcp.cpp', 'turn_tcp.h'}
            or any(not re.fullmatch('[a-f0-9]{64}', value) for value in hashes.values())):
        raise ValueError('Unexpected pinned TURN source inventory')
    result = {}
    cache.mkdir()
    for name, expected in hashes.items():
        uri = 'https://raw.githubusercontent.com/BelledonneCommunications/mediastreamer2/5.3.105/src/voip/'+name
        with opener(uri, timeout=60) as response:
            if response.geturl() != uri:
                raise ValueError('Unexpected TURN source redirect')
            body = response.read(1024**2+1)
        if len(body) > 1024**2 or hashlib.sha256(body).hexdigest() != expected:
            raise ValueError('TURN source differs from its pinned digest')
        (cache/name).write_bytes(body)
        result['zmala_terminal/linux/native/upstream/'+name] = (body, False)
    return result


def emit(role, output, commit='HEAD'):
    """Snapshot Git blobs, not worktree/private files; retain every external archive."""
    paths = source_paths(role)
    source_commit = subprocess.check_output(['git', 'rev-parse', '--verify', '--end-of-options', commit+'^{commit}'],
                                            cwd=project.ROOT, text=True).strip()
    if not re.fullmatch('[a-f0-9]{40}', source_commit):
        raise ValueError('Expected a complete source commit')
    output = Path(output).absolute()
    if output.exists():
        raise ValueError('Use a new application-input directory')
    output.mkdir(parents=True)
    original = output/'git-source.tar'
    with original.open('xb') as stream:
        subprocess.run(['git', 'archive', '--format=tar', source_commit, '--', *paths],
                       cwd=project.ROOT, stdout=stream, check=True, timeout=60)
    records = read_tar(original)
    for name, (body, executable) in list(records.items()):
        if any(part in ('data', 'node_modules', '.git', '.env', '.npmrc', '__pycache__')
               for part in PurePosixPath(name).parts) or name.endswith(('.so', '.node', '.keystore', '.jks')):
            raise ValueError('Source snapshot contains private/generated input: '+name)
        if PurePosixPath(name).suffix in TEXT:
            records[name] = body.replace(b'\r\n', b'\n'), executable
    gradle = records.pop('zmala_phone/app/build.gradle')[0].decode()
    version = re.search(r"versionName '([^']+)'", gradle)[1]
    sequence = int(re.search(r'versionCode (\d+)', gradle)[1])
    records['build_tools/linux/release-info.json'] = (json.dumps(
        {'version': version, 'sequence': sequence, 'commit': source_commit}, sort_keys=True).encode(), False)
    if role in ('terminal', 'combined'):
        retained_turn = turn_sources(records['build_tools/linux/build-turn.py'][0], output/'turn-source')
        for name, contents in retained_turn.items():
            if name in records and records[name] != contents:
                raise ValueError('Conflicting retained TURN input')
            records[name] = contents
    cache = output/'npm-archives'
    cache.mkdir()
    retained = []
    if role in ('server', 'combined'):
        lock = json.loads(records['zmala_server/package-lock.json'][0])
        with ThreadPoolExecutor(max_workers=6) as pool:
            downloads = list(pool.map(lambda entry: acquire_dependency(entry, cache), npm_entries(lock)))
        for name, archive in downloads:
            dependency = read_tar(archive, prefix='package')
            package = json.loads(dependency['package.json'][0])
            if any(key in package.get('scripts', {}) for key in ('preinstall', 'install', 'postinstall')):
                raise ValueError('Dependency requires unqualified install scripts')
            for path, contents in dependency.items():
                if path.endswith('.node') or contents[0].startswith(b'\x7fELF'):
                    raise ValueError('Unqualified native npm dependency')
                target = 'zmala_server/'+name+'/'+path
                if target in records:
                    raise ValueError('Dependency/source collision')
                records[target] = contents
            retained.append({'path': name, 'archive': archive.name,
                             'sha256': package_lock.digest(archive), 'bytes': archive.stat().st_size})
        vendor = 'zmala_server/vendor/sip/'
        for name, contents in list(records.items()):
            if name.startswith(vendor):
                records['zmala_server/node_modules/sip/'+name[len(vendor):]] = contents
    if len(records) > MAX_FILES or sum(len(body) for body, _ in records.values()) > MAX_TOTAL:
        raise ValueError('Combined application tree exceeds its budget')
    manifest = {'schema': 1, 'role': role, 'source_commit': source_commit, 'version': version,
                'sequence': sequence, 'npm_archives': retained, 'package_scripts_executed': False,
                'files': {name: {'sha256': hashlib.sha256(body).hexdigest(), 'bytes': len(body),
                                 'mode': 0o755 if executable else 0o644}
                          for name, (body, executable) in sorted(records.items())}}
    records[MARKER] = ((json.dumps(manifest, sort_keys=True, indent=2)+'\n').encode(), False)
    archive_path = output/'applications.tar'
    with tarfile.open(archive_path, 'w') as archive:
        for name, (body, executable) in sorted(records.items()):
            member = tarfile.TarInfo(name)
            member.mode, member.size = 0o755 if executable else 0o644, len(body)
            member.mtime = int(root_build.SOURCE_DATE_EPOCH)
            archive.addfile(member, io.BytesIO(body))
    result = {'schema': 1, 'role': role, 'source_commit': source_commit, 'version': version,
              'applications_sha256': package_lock.digest(archive_path),
              'files': len(records)-1, 'npm_archives': len(retained),
              'package_scripts_executed': False, 'native_code_built': False,
              'production_qualified': False}
    (output/'READY.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    return result


def verify(source, expected, role):
    source = Path(source)
    if (source.is_symlink() or not source.is_file() or source.stat().st_size > MAX_TOTAL+MAX_FILES*1024
            or not re.fullmatch('[a-f0-9]{64}', expected) or package_lock.digest(source) != expected):
        raise ValueError('Application input digest differs from its reviewed record')
    records = read_tar(source)
    manifest = json.loads(records.pop(MARKER)[0])
    if (manifest.get('schema') != 1 or manifest.get('role') != role or role not in ROLES
            or manifest.get('package_scripts_executed') is not False
            or set(manifest['files']) != set(records)):
        raise ValueError('Application role or file inventory differs')
    for name, (body, executable) in records.items():
        if manifest['files'][name] != {'sha256': hashlib.sha256(body).hexdigest(),
                                      'bytes': len(body), 'mode': 0o755 if executable else 0o644}:
            raise ValueError('Application contents differ from their retained manifest')
    return records, manifest
