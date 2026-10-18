"""Remove disposable checkout artifacts without touching data or dependencies."""
import argparse
import os
from pathlib import Path
import shutil
import stat
import subprocess


ROOT = Path(__file__).resolve().parents[1]
CACHES = {'__pycache__', '.ruff_cache', '.pytest_cache', '.mypy_cache'}
OUTPUTS = {'tmp', 'build_tools/tmp', 'build_tools/dist', 'build_tools/.npm-cache',
           'requirements/output'}
PRESERVE = {'.git', '.venv', 'venv', 'node_modules', 'data', '.codex-remote-attachments',
            'runtime', 'framing-runtime', 'account-pictures'}


def linked(path):
    # Python 3.11 lacks Path.is_junction(); reparse attributes also cover junctions.
    attributes = getattr(path.lstat(), 'st_file_attributes', 0)
    return path.is_symlink() or bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def candidates(root):
    """Do not descend into dependencies, runtime data or directory links."""
    for directory, dirs, files in os.walk(root, followlinks=False):
        parent = Path(directory)
        for name in list(dirs):
            path = parent / name
            if linked(path) or name in PRESERVE:
                dirs.remove(name)
            elif name in CACHES or path.relative_to(root).as_posix() in OUTPUTS:
                dirs.remove(name)
                yield path
        for name in files:
            path = parent / name
            if path.suffix in {'.pyc', '.pyo'} and not linked(path):
                yield path


def clean(root, dry_run=False):
    root = root.resolve()
    # Refuse to remove source files even if someone tracks a cache/output path.
    result = subprocess.run(['git', 'ls-files', '-z', '--cached'], cwd=root,
                            check=True, stdout=subprocess.PIPE)
    tracked = {os.fsdecode(name).replace('\\', '/') for name in result.stdout.split(b'\0') if name}
    removed = 0
    for path in candidates(root):
        relative = path.relative_to(root).as_posix()
        if any(name == relative or name.startswith(relative + '/') for name in tracked):
            print(f'Keep {relative} (contains tracked files)')
            continue
        if linked(path) or not path.resolve().is_relative_to(root):
            raise ValueError(f'Refusing to clean outside checkout: {relative}')
        print(f'{"Would remove" if dry_run else "Remove"} {relative}')
        if not dry_run:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
        removed += 1
    print(f'{removed} disposable paths {"found" if dry_run else "removed"}.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true', help='List paths without deleting them.')
    clean(ROOT, parser.parse_args().dry_run)
