"""One executable, with GUI confirmation or explicit headless consent."""
from pathlib import Path
import sys

if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def main():
    if '--headless' in sys.argv:
        from build_tools.server_installer.cli import main as run
    else:
        from build_tools.server_installer.app import main as run
    return run()


if __name__ == '__main__':
    sys.exit(main())
