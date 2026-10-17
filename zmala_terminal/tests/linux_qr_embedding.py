"""Real Linux QR worker containment/resizing test; run with xvfb-run, no camera."""
from pathlib import Path
import sys
import tempfile
import time
import tkinter as tk
from PIL import Image, ImageGrab

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qr_scanner import QRScanner

root = tk.Tk()
root.geometry('900x620+100+60')
header = tk.Frame(root, height=64, bg='#ff0000')
header.pack(fill='x')
frame = tk.Frame(root, bg='#0d121c')
frame.pack(fill='both', expand=True, padx=40, pady=20)
root.update()
try:
    with tempfile.TemporaryDirectory() as directory:
        picture = Path(directory) / 'camera.png'
        Image.new('RGB', (640, 480), '#00ff00').save(picture)
        for _ in range(3):
            scanner = QRScanner(lambda value: None, frame.winfo_id(), 'qr-embedding-test',
                                camera='StaticImage: Static picture', static_picture=picture)
            try:
                for size in ('900x620', '1280x720', '800x600'):
                    root.geometry(size + '+100+60')
                    deadline = time.monotonic() + 8
                    good = False
                    while time.monotonic() < deadline:
                        root.update()
                        scanner.iterate()
                        time.sleep(.1)
                        screen = ImageGrab.grab()
                        head = screen.getpixel((header.winfo_rootx()+10, header.winfo_rooty()+10))
                        camera = screen.getpixel((frame.winfo_rootx()+frame.winfo_width()//2,
                                                  frame.winfo_rooty()+frame.winfo_height()//2))
                        good = head == (255, 0, 0) and camera == (0, 255, 0)
                        if good:
                            break
                    assert good, 'QR worker obscured the header or clipped its camera preview'
            finally:
                scanner.close()
            assert scanner.process.poll() is not None
            root.update()
    print('QR worker embedding passed: visible header/preview, resizing, three restarts.')
finally:
    root.destroy()
