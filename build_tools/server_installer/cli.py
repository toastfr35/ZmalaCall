"""Headless deployment with durable logs and explicit installation consent."""
import argparse
from datetime import datetime
import os
from pathlib import Path
import sys
import traceback
from build_tools.server_installer.backend import Deployment, verify_payload


def resources():
    return Path(sys._MEIPASS) if getattr(sys, 'frozen', False) else Path(__file__).parents[1]/'dist'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--headless', action='store_true', required=True)
    parser.add_argument('--host', default='zmalaserver.local')
    parser.add_argument('--yes', action='store_true')
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--data-dir', type=Path, help='Optional existing server data directory to import')
    parser.add_argument('--smoke-test', type=Path)
    parser.add_argument('--log', type=Path)
    args = parser.parse_args(argv)
    log_path = args.log or Path(os.environ.get('LOCALAPPDATA', str(Path.home())))/'ZmalaCall/ServerInstaller'/(
        datetime.now().strftime('%Y%m%d-%H%M%S')+'.log')
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open('w', encoding='utf-8') as log:
        def emit(message):
            log.write(message)
            log.flush()
            if sys.stdout:
                sys.stdout.write(message)
                sys.stdout.flush()
        target = None
        try:
            if not (args.yes or args.check_only or args.smoke_test):
                emit('Installation requires --yes. Use --check-only for a read-only check.\n')
                return 2
            if args.smoke_test and (args.yes or args.check_only):
                emit('Smoke test cannot be combined with installation or target checks.\n')
                return 2
            archive = resources()/'ZmalaCall-Server-rpi.tar.gz'
            verify_payload(archive)
            if args.smoke_test:
                args.smoke_test.write_text('Headless mode; bundled server package checksum verified.\n')
                return 0
            target = Deployment(args.host, emit)
            target.check()
            if not args.check_only:
                target.install(archive, args.data_dir)
            return 0
        except Exception:
            emit('FAILED\n'+traceback.format_exc())
            return 1
        finally:
            if target:
                target.close()
