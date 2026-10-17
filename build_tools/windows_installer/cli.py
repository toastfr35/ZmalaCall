"""Unattended installer with explicit consent, durable logs and exit codes."""
import argparse
from datetime import datetime
import os
from pathlib import Path
import sys
import traceback

from backend import Deployment, verify_payload


def resources():
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[1] / 'dist'


class UsageError(Exception):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise UsageError(message)


def main(argv=None):
    parser = Parser(description=__doc__)
    parser.add_argument('--headless', action='store_true', required=True)
    parser.add_argument('--host', default='zmala.local', help='Pi network address or Ethernet IP')
    parser.add_argument('--yes', action='store_true', help='Confirm installation and automatic reboot')
    parser.add_argument('--check-only', action='store_true', help='Check the Pi without installing')
    parser.add_argument('--log', type=Path, help='Write a UTF-8 log to this file')
    parser.add_argument('--smoke-test', type=Path, help='Verify the packaged payload without contacting a Pi')
    default_logs = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'ZmalaCall/Installer/logs'
    default_path = default_logs / ('headless-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.log')
    args = None
    parse_error = None
    try:
        args = parser.parse_args(argv)
    except UsageError as error:
        parse_error = str(error)
    except SystemExit as result:
        return result.code
    log_path = args.log if args and args.log else default_path
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log = log_path.open('w', encoding='utf-8')
    except OSError as error:
        if sys.stderr:
            sys.stderr.write(f'Cannot create installer log: {error}\n')
        return 1  # Never install if the outcome cannot be recorded.
    target = None
    with log:
        def emit(message):
            log.write(message)
            log.flush()
            # PyInstaller's windowed EXE has no standard streams. File logging
            # remains available to scheduled tasks and Start-Process -Wait.
            if sys.stdout:
                try:
                    sys.stdout.write(message)
                    sys.stdout.flush()
                except (OSError, UnicodeError):
                    pass
        emit(f'Zmala terminal setup - headless\nLog: {log_path.resolve()}\n')
        try:
            if parse_error:
                raise UsageError(parse_error)
            if args.smoke_test and (args.yes or args.check_only):
                raise UsageError('--smoke-test cannot be combined with --yes or --check-only')
            if not (args.yes or args.check_only or args.smoke_test):
                raise UsageError('Installation requires --yes. Use --check-only for a read-only check.')
            archive = resources() / 'ZmalaCall-Terminal-rpi.tar.gz'
            verify_payload(archive)
            if args.smoke_test:
                result = 'Headless mode; bundled package checksum verified.\n'
                args.smoke_test.write_text(result, encoding='utf-8')
                emit(result)
                return 0
            target = Deployment(args.host, emit)
            info = target.check()
            emit(f"Verified target: {info['model']} at {info['ssh_address']}\n")
            if args.check_only:
                emit('CHECK PASSED. No installation performed.\n')
                return 0
            emit('Installation and reboot confirmed by --yes. Argon fan setup is automatic.\n')
            target.install(archive, True)
            emit('SUCCESS. Installation and post-reboot verification passed.\n')
            return 0
        except UsageError as error:
            emit(f'USAGE ERROR: {error}\n')
            return 2
        except KeyboardInterrupt:
            emit('INTERRUPTED. An installation already started on the Pi may still be running.\n')
            return 130
        except Exception:
            emit('FAILED.\n' + traceback.format_exc())
            return 1
        finally:
            if target is not None:
                target.close()


if __name__ == '__main__':
    sys.exit(main())
