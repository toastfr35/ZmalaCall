"""Launch one isolated display scenario; keep its mutable profile out of the checkout."""
from pathlib import Path
import runpy
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from zmala_terminal.common import main


def run(path):
    initialize = main.Terminal.initialize_state
    with tempfile.TemporaryDirectory(prefix='zmala-display-rbt-') as directory:
        def initialize_state(app, profile, wifi_mode):
            with patch.object(main, 'ROOT', Path(directory)):
                initialize(app, profile, wifi_mode)
        with patch.object(main.Terminal, 'initialize_state', initialize_state), \
                patch.dict('os.environ', {'ZMALA_USB_POWER': '0', 'ZMALA_ARGON_ONE_FAN': '0',
                           'ZMALA_C20_SETUP': '0', 'ZMALA_LOG_STDERR': '1', 'ZMALA_RUNTIME_DIR': directory}), \
                patch.object(sys, 'argv', [str(path)]):
            runpy.run_path(str(path), run_name='__main__')


if __name__ == '__main__':
    run(Path(sys.argv[1]).resolve())
