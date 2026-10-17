"""Enable temporary Python debug logging on the installed terminal without restart."""
import argparse
from pathlib import Path
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('minutes', type=int, nargs='?', default=10, help='0 to disable; maximum 60')
    args = parser.parse_args()
    if not 0 <= args.minutes <= 60:
        parser.error('Choose 0 to 60 minutes')
    runtime = Path('/run/zmalacall')
    if not runtime.is_dir():
        parser.error('The installed terminal is not running')
    temporary = runtime / 'debug-until.tmp'
    temporary.write_text(str(time.monotonic() + args.minutes * 60))
    temporary.chmod(0o644)
    temporary.replace(runtime / 'debug-until')
    print(f'Debug logging enabled for {args.minutes} minutes.' if args.minutes else 'Debug logging disabled.')
    print('View: sudo journalctl -u zmalacall-terminal -f')


if __name__ == '__main__':
    main()
