"""Native QR readback through the camera worker, and UI crash containment."""
import json
from pathlib import Path
import subprocess
import sys
import time
import tkinter as tk
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT.parent))
from zmala_terminal.common import main as main
from zmala_terminal.common.qr_scanner import QRScanner

manifest = json.loads(Path(sys.argv[1]).resolve().read_text(encoding='utf-8'))
root = tk.Tk()
root.title('ZmalaCall camera worker verification')
frame = tk.Frame(root, width=640, height=480)
frame.pack()
root.update()
try:
    for item in manifest:
        decoded = []
        scanner = QRScanner(decoded.append, frame.winfo_id(), 'qr-process-verification',
                            camera='StaticImage: Static picture', static_picture=item['image'])
        try:
            deadline = time.monotonic() + (30 if sys.platform.startswith('linux') else 12)
            while decoded.count(item['payload']) < 2 and time.monotonic() < deadline:
                root.update()
                scanner.iterate()
                time.sleep(.02)
            assert decoded.count(item['payload']) >= 2, 'Worker did not read/re-arm its QR decoder'
            print('Camera worker readback passed:', Path(item['image']).name)
        finally:
            scanner.close()
        assert scanner.process.poll() is not None, 'Closing the scanner left its camera worker alive'
finally:
    root.destroy()

# Simulate an uncatchable native crash after camera startup. The real parent
# scanner sees the dead process; Tk must stay on the Wi-Fi setup screen.
real_popen = subprocess.Popen
def crash_worker(arguments, **options):
    assert Path(arguments[1]).name == 'qr_worker.py'
    return real_popen([arguments[0], '-c', 'import os,time;time.sleep(.3);os._exit(75)'], **options)

app = None
with patch('zmala_terminal.common.qr_scanner.subprocess.Popen', side_effect=crash_worker):
    try:
        app = main.Terminal(profile='qr-crash-verification', unconfigured=True)
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            app.root.update()
            time.sleep(.02)
        assert app.root.winfo_exists() and not app.closed, 'Native camera failure closed the terminal'
        assert app.setup_stage == 'wifi', 'Camera failure changed enrollment stage'
        assert app.scanner is None and app.setup_error_until > time.monotonic(), 'Camera failure was not handled with a retry'
        print('Camera crash containment passed: terminal stays open at Wi-Fi QR setup')
    finally:
        if app:
            app.close()
