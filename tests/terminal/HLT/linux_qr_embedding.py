# @test T-HLT-007
# @requirements HLR-TERM-SETUP-020, HLR-TERM-UI-012
# @environment native-display
# @plan Start the real QR worker with a synthetic green image inside a red-header window; resize repeatedly, assert camera pixels stay in the viewport and the header remains unobscured, then verify worker termination.
# Measure the mint guide pixels inside the letterboxed preview at every size; require a centred square with visible corners and an unchanged camera centre.
# @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

"""Real Linux QR worker containment/resizing test; run with xvfb-run, no camera."""
from pathlib import Path
import sys
import tempfile
import time
import tkinter as tk
from unittest.mock import patch
from PIL import Image, ImageGrab

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from zmala_terminal.common.qr_scanner import QRScanner
from zmala_terminal.common import qr_scanner

root = tk.Tk()
root.geometry('900x620+100+60')
header = tk.Frame(root, height=64, bg='#ff0000')
header.pack(fill='x')
frame = tk.Frame(root, bg='#0d121c')
frame.pack(fill='both', expand=True, padx=40, pady=20)
root.update()
try:
    with tempfile.TemporaryDirectory() as directory, patch.object(qr_scanner, 'journal_logging', return_value=True):
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
                        viewport=screen.crop((frame.winfo_rootx(),frame.winfo_rooty(),
                            frame.winfo_rootx()+frame.winfo_width(),frame.winfo_rooty()+frame.winfo_height()))
                        # Inspect actual worker pixels after asynchronous resize.
                        guide=Image.new('1',viewport.size)
                        guide.putdata([pixel==(131,223,197) for pixel in viewport.getdata()])
                        box=guide.getbbox()
                        guides_good = bool(box and
                            abs((box[0]+box[2])/2-frame.winfo_width()/2)<=2 and
                            abs((box[1]+box[3])/2-frame.winfo_height()/2)<=2)
                        good = head == (255, 0, 0) and camera == (0, 255, 0) and guides_good
                        if good:
                            break
                    assert good, ('QR preview/header or centred guides did not settle',box,size)
                    assert box, 'QR positioning guides are missing'
                    left,top,right,bottom=box
                    assert abs((left+right)/2-frame.winfo_width()/2)<=2, ('guide horizontal centre',box)
                    assert abs((top+bottom)/2-frame.winfo_height()/2)<=2, ('guide vertical centre',box)
                    assert abs((right-left)-(bottom-top))<=1, ('guide square',box)
                    assert 0<left<right<frame.winfo_width() and 0<top<bottom<frame.winfo_height(), ('guide clipped',box)
            finally:
                scanner.close()
            assert scanner.process.poll() is not None
            root.update()
    print('QR worker embedding passed: visible header/preview, resizing, three restarts.')
finally:
    root.destroy()
