"""Exercise the actual SDK QR decoder against generated/printed QR images."""
import argparse
import json
from pathlib import Path
import sys
import time
import tkinter as tk
ROOT = (Path(__file__).resolve().parents[3] / 'zmala_terminal')
sys.path.insert(0, str(ROOT.parent))
from zmala_terminal.common.engine import NativeQRScanner

parser = argparse.ArgumentParser()
parser.add_argument('manifest', type=Path)
args = parser.parse_args()
manifest = json.loads(args.manifest.resolve().read_text(encoding='utf-8'))
root = tk.Tk()
root.title('ZmalaCall QR verification')
frame = tk.Frame(root, width=640, height=480, bg='#0d121c')
frame.pack()
root.update()
decoded = []
scanner = NativeQRScanner(decoded.append, frame.winfo_id(), 'qr-verification', camera='StaticImage: Static picture')
try:
    for item in manifest:
        decoded.clear()
        scanner.set_static_picture(item['image'])
        # This used to abort inside ms_filter_unlink for physical-camera format
        # changes. Exercise the same QR-aware graph rebuild repeatedly.
        for _ in range(3):
            scanner.preview_bridge.zmala_qr_refresh(scanner.preview)
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline and item['payload'] not in decoded:
            root.update()
            scanner.iterate()
            time.sleep(.02)
        assert item['payload'] in decoded, f"QR decoder failed: {Path(item['image']).name}; decoded={decoded!r}"
        print('QR readback passed:', Path(item['image']).name)
finally:
    scanner.close()
    root.destroy()
