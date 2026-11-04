"""Development image tools. No command flashes a card or updates a live host."""
import argparse
import json
from pathlib import Path
import subprocess

from . import inspect_disk, inspect_root, package_lock, project, sources


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('check', help='Validate checked-in source pins and role package intent')
    fetch = sub.add_parser('fetch', help='Download and hash-check a pinned source into a new cache tree')
    fetch.add_argument('source', choices=('imagegen', 'backend_audit'))
    fetch.add_argument('--cache', required=True, type=Path)
    probe = sub.add_parser('probe-config', help='Emit a development-only minimal boot configuration')
    probe.add_argument('role', choices=('terminal', 'server'))
    probe.add_argument('--output', required=True, type=Path)
    inspect = sub.add_parser('inspect-root', help='Read an already unpacked offline root')
    inspect.add_argument('root', type=Path)
    disk = sub.add_parser('inspect-disk', help='Validate an offline probe image partition table')
    disk.add_argument('image', type=Path)
    disk.add_argument('--sector-size', choices=(512, 4096), type=int, default=512)
    lock = sub.add_parser('lock-packages', help='Download and retain an authenticated dependency closure (Linux)')
    lock.add_argument('role', choices=('terminal', 'server'))
    lock.add_argument('--output', type=Path, required=True)
    lock.add_argument('--debian-keyring', type=Path, required=True)
    lock.add_argument('--raspberrypi-keyring', type=Path, required=True)
    verify = sub.add_parser('verify-packages', help='Verify retained archives against a trusted lock digest')
    verify.add_argument('folder', type=Path)
    verify.add_argument('--expected-lock-sha256', required=True)
    args = parser.parse_args()
    try:
        if args.command == 'check':
            sources.pins()
            locks = project.package_locks()
            for role in project.profiles()['roles']:
                print(role+': '+str(len(project.packages(role)))+' requested packages; '
                      +str(locks['roles'][role]['archives'])+' locked dependency archives')
            print('Source pins, profiles and intent locks valid; no image is qualified.')
        elif args.command == 'fetch':
            print(sources.acquire(args.source, args.cache))
        elif args.command == 'probe-config':
            print(project.emit_lab(args.role, args.output))
        elif args.command == 'inspect-disk':
            print(json.dumps(inspect_disk.audit(args.image, args.sector_size), indent=2))
        elif args.command == 'lock-packages':
            result = package_lock.intake(project.packages(args.role), args.output,
                                         args.debian_keyring, args.raspberrypi_keyring)
            print(str(len(result['packages']))+' package archives retained; lock SHA-256: '
                  +package_lock.digest(args.output/'packages.lock.json'))
        elif args.command == 'verify-packages':
            result = package_lock.verify(args.folder, args.expected_lock_sha256)
            print(str(len(result['packages']))+' retained package archives verified.')
        else:
            result = inspect_root.audit(args.root)
            print(json.dumps(result, indent=2))
            return 1 if result['violations'] else 0
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        parser.error('Isolated package tool failed; retain its incomplete cache for diagnosis. No lock was accepted.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
