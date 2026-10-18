"""Package shared source/assets and Linux scripts, excluding credentials and DLLs."""
import argparse
import io
import hashlib
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[2]
TEXT_SUFFIXES = {'.sh', '.txt', '.conf', '.service', '.rules', '.plymouth', '.script',
                 '.py', '.json', '.c', '.h', '.md', '.svg'}


def package(destination=None):
    """Ship one C20 release; native plugins are compiled by its Pi installer."""
    destination = Path(destination or ROOT / 'build_tools/dist/ZmalaCall-Terminal-rpi.tar.gz')
    destination.parent.mkdir(parents=True, exist_ok=True)
    checksums = []
    with tarfile.open(destination, 'w:gz') as archive:
        for base in (ROOT / 'zmala_terminal/common', ROOT / 'zmala_terminal/linux', ROOT / 'build_tools/linux'):
            for path in sorted(base.rglob('*')):
                if not path.is_file() or any(part in ('data', '__pycache__', 'framing-runtime', 'models')
                                             for part in path.relative_to(ROOT).parts):
                    continue
                if path.suffix in ('.so', '.o'):
                    continue  # native experiments are built on the target Pi
                # Test screenshots/results are generated artifacts, not source.
                if 'tests' in path.parts and path.suffix not in ('.py', '.json'):
                    continue
                info = archive.gettarinfo(str(path), arcname=path.relative_to(ROOT).as_posix())
                info.mode = 0o755 if path.suffix == '.sh' else 0o644
                info.uid = info.gid = 0
                info.uname = info.gname = 'root'
                # Windows CI checks text out as CRLF. Linux consumers such as
                # xargs retain CR in package names; normalize configs and lists
                # as well as scripts, before computing the release manifest.
                content = path.read_bytes()
                if path.suffix in TEXT_SUFFIXES:
                    content = content.replace(b'\r\n', b'\n')
                info.size = len(content)
                archive.addfile(info, io.BytesIO(content))
                checksums.append(hashlib.sha256(content).hexdigest() + '  ' + info.name)
        for name in ('general.md', 'server.md', 'terminal.md'):
            archive.add(ROOT / 'docs' / name, arcname='docs/' + name)
            checksums.append(hashlib.sha256((ROOT / 'docs' / name).read_bytes()).hexdigest() + '  docs/' + name)
        diagram = ROOT / 'build_tools/assets/installation-connections.png'
        archive.add(diagram, arcname='build_tools/assets/installation-connections.png')
        checksums.append(hashlib.sha256(diagram.read_bytes()).hexdigest()
                         + '  build_tools/assets/installation-connections.png')
        wrapper = b'#!/bin/sh\nset -eu\ncd -- "$(dirname -- "$0")"\nexec sh build_tools/linux/install-kiosk.sh "$@"\n'
        info = tarfile.TarInfo('install.sh')
        info.mode = 0o755
        info.size = len(wrapper)
        archive.addfile(info, io.BytesIO(wrapper))
        checksums.append(hashlib.sha256(wrapper).hexdigest() + '  install.sh')
        manifest = ('\n'.join(checksums) + '\n').encode()
        info = tarfile.TarInfo('SHA256SUMS')
        info.mode = 0o644
        info.size = len(manifest)
        archive.addfile(info, io.BytesIO(manifest))
    destination.with_name(destination.name + '.sha256').write_text(
        hashlib.sha256(destination.read_bytes()).hexdigest() + '  ' + destination.name + '\n')
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    print(package(args.output))
