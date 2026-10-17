"""Choose the unattended path before importing any GUI code."""
import sys


def main():
    if '--headless' in sys.argv[1:]:
        from cli import main as run
        return run()
    from app import main as run
    return run()


if __name__ == '__main__':
    sys.exit(main())
