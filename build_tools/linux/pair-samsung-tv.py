"""Pair a Samsung TV for live-TV restoration; approve its access prompt once."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from zmala_terminal.linux.tv_plugins.samsung.driver import DEFAULT_CONFIG, connect, save_config  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('host', help='TV IP address (reserve it in the router)')
    parser.add_argument('--config', type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    remote = None
    try:
        # Explicit pairing trusts the TV at the supplied IP and saves its
        # certificate. Normal terminal operation always checks that pin.
        print('Approve ZmalaCall on the TV if an access prompt appears.', flush=True)
        remote, config = connect(args.host, timeout=30)
        save_config(args.config, config)
        print('TV paired; private credentials saved to', args.config)
    except Exception as error:
        print('Pairing failed:', type(error).__name__, file=sys.stderr)
        return 1
    finally:
        if remote:
            remote.close(timeout=0)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
