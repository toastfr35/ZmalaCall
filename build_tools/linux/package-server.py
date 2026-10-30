"""Build a credential-free server release; migration data travels separately."""
import hashlib
import io
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ('install-server.sh', 'server-launch.py', 'check-server.py',
           'install-low-wear.sh', 'low-wear-journal.conf', 'low-wear-swap.conf',
           'install-ssh-guard.sh', 'ssh-guard.py', 'zmalacall-ssh-guard.service',
           'zmalacall-server.service', 'server-ssh.py', 'developer-access.py',
           'install-developer-access.py', 'developer-lan-guard.py')


def package(destination=None):
    destination = Path(destination or ROOT / 'build_tools/dist/ZmalaCall-Server-rpi.tar.gz')
    destination.parent.mkdir(parents=True, exist_ok=True)
    paths = [p for p in (ROOT / 'zmala_server').rglob('*') if p.is_file()
             and not any(part in ('data', 'node_modules', 'tests', '__pycache__')
                         for part in p.relative_to(ROOT / 'zmala_server').parts)]
    paths += [ROOT / 'build_tools/linux' / name for name in SCRIPTS]
    paths += [ROOT / 'build_tools' / name for name in ('build-admin.cjs', 'convert-photo.py')]
    paths += [ROOT / 'zmala_terminal/common/shared/terminal-languages.json']
    paths += [ROOT / 'zmala_terminal/common/assets/gentle-chime.wav']
    paths += [ROOT / 'docs' / name for name in ('general.md', 'server.md', 'terminal.md')]
    paths += [ROOT / 'build_tools/assets/installation-connections.png',
              ROOT / 'zmala_terminal/common/assets/presenter-pairing.png']
    checksums = []
    with tarfile.open(destination, 'w:gz') as archive:
        def add(name, data, mode=0o644):
            item = tarfile.TarInfo(name)
            item.size, item.mode = len(data), mode
            archive.addfile(item, io.BytesIO(data))
            checksums.append(hashlib.sha256(data).hexdigest() + '  ' + name)
        for path in sorted(paths):
            data = path.read_bytes()
            if path.suffix in ('.py', '.sh', '.js', '.cjs', '.json', '.service', '.conf', '.css', '.html', '.ts', '.md', '.svg'):
                data = data.replace(b'\r\n', b'\n')
            add(path.relative_to(ROOT).as_posix(), data, 0o755 if path.suffix == '.sh' else 0o644)
        add('install.sh', b'#!/bin/sh\nset -eu\ncd -- "$(dirname -- "$0")"\nexec sh build_tools/linux/install-server.sh "$@"\n', 0o755)
        add('SHA256SUMS', ('\n'.join(checksums)+'\n').encode())
    destination.with_name(destination.name+'.sha256').write_text(
        hashlib.sha256(destination.read_bytes()).hexdigest()+'  '+destination.name+'\n')
    return destination


if __name__ == '__main__':
    print(package())
