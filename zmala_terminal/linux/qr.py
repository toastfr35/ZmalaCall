"""Isolated V4L2 camera preview and ZBar QR decoding, embedded in the Tk surface.

The parent receives decoded text over the existing JSON pipe. Images and camera
drivers stay in this worker process, preserving crash isolation on both OSes.
"""
import ctypes as C
import ctypes.util
import time
import tkinter as tk
import cv2
from PIL import Image, ImageTk


class QRDecoder:
    def __init__(self):
        self.dll = C.CDLL(ctypes.util.find_library('zbar'))
        signatures = {
            'image_scanner_create': (C.c_void_p, []),
            'image_scanner_destroy': (None, [C.c_void_p]),
            'image_scanner_set_config': (C.c_int, [C.c_void_p, C.c_int, C.c_int, C.c_int]),
            'image_create': (C.c_void_p, []), 'image_destroy': (None, [C.c_void_p]),
            'image_set_format': (None, [C.c_void_p, C.c_ulong]),
            'image_set_size': (None, [C.c_void_p, C.c_uint, C.c_uint]),
            'image_set_data': (None, [C.c_void_p, C.c_void_p, C.c_ulong, C.c_void_p]),
            'scan_image': (C.c_int, [C.c_void_p, C.c_void_p]),
            'image_first_symbol': (C.c_void_p, [C.c_void_p]),
            'symbol_next': (C.c_void_p, [C.c_void_p]),
            'symbol_get_data': (C.c_void_p, [C.c_void_p]),
            'symbol_get_data_length': (C.c_uint, [C.c_void_p]),
        }
        for name, (result, arguments) in signatures.items():
            function = getattr(self.dll, 'zbar_' + name)
            function.restype, function.argtypes = result, arguments
        self.scanner = self.dll.zbar_image_scanner_create()
        self.dll.zbar_image_scanner_set_config(self.scanner, 0, 0, 0)
        self.dll.zbar_image_scanner_set_config(self.scanner, 64, 0, 1)  # QR only

    def decode(self, frame):
        """Borrow the NumPy grayscale buffer for this synchronous scan; copy symbols before destroying the image."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        image = self.dll.zbar_image_create()
        try:
            self.dll.zbar_image_set_format(image, int.from_bytes(b'Y800', 'little'))
            self.dll.zbar_image_set_size(image, gray.shape[1], gray.shape[0])
            self.dll.zbar_image_set_data(image, gray.ctypes.data, gray.nbytes, None)
            self.dll.zbar_scan_image(self.scanner, image)
            symbol = self.dll.zbar_image_first_symbol(image)
            while symbol:
                length = self.dll.zbar_symbol_get_data_length(symbol)
                if 0 < length <= 8192:
                    yield C.string_at(self.dll.zbar_symbol_get_data(symbol), length).decode('utf-8')
                symbol = self.dll.zbar_symbol_next(symbol)
        finally:
            self.dll.zbar_image_destroy(image)

    def close(self):
        if self.scanner:
            self.dll.zbar_image_scanner_destroy(self.scanner)
            self.scanner = None


class NativeQRScanner:
    # @llr LLR-TERM-SETUP-027
    def __init__(self, on_qr, video_window=0, profile='terminal', camera=None):
        self.on_qr, self.capture, self.picture = on_qr, None, None
        self.last_qr, self.next_frame, self.next_decode = ('', 0), 0, 0
        self.decoder, self.root = None, None
        self.x11, self.display, self.parent = None, None, video_window
        try:
            self.decoder = QRDecoder()
            self.root = tk.Tk()
            self.root.overrideredirect(True)
            self.root.configure(bg='#0d121c')
            self.label = tk.Label(self.root, bg='#0d121c', borderwidth=0)
            self.label.pack(fill='both', expand=True)
            self.root.geometry('640x480')
            self.root.update()
            if video_window:
                self._embed(video_window)
            if camera != 'StaticImage: Static picture':
                device = camera or '/dev/video0'
                if device.startswith(('V4L2:', 'ZmalaMJPEG:')):
                    device = device.split(':', 1)[1].strip()
                self.capture = cv2.VideoCapture(device, cv2.CAP_V4L2)
                self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                self.capture.set(cv2.CAP_PROP_FPS, 15)
                if not self.capture.isOpened():
                    raise RuntimeError('No V4L2 webcam is available for QR setup')
        except Exception:
            self.close()
            raise

    def _embed(self, window):
        self.x11 = C.CDLL(ctypes.util.find_library('X11'))
        self.x11.XOpenDisplay.argtypes, self.x11.XOpenDisplay.restype = [C.c_char_p], C.c_void_p
        self.x11.XReparentWindow.argtypes = [C.c_void_p, C.c_ulong, C.c_ulong, C.c_int, C.c_int]
        self.x11.XQueryTree.argtypes = [C.c_void_p, C.c_ulong, C.POINTER(C.c_ulong),
            C.POINTER(C.c_ulong), C.POINTER(C.POINTER(C.c_ulong)), C.POINTER(C.c_uint)]
        self.x11.XFree.argtypes = [C.c_void_p]
        self.x11.XFlush.argtypes = [C.c_void_p]
        self.x11.XCloseDisplay.argtypes = [C.c_void_p]
        self.x11.XGetGeometry.argtypes = [C.c_void_p, C.c_ulong, C.POINTER(C.c_ulong),
            C.POINTER(C.c_int), C.POINTER(C.c_int), *([C.POINTER(C.c_uint)] * 4)]
        self.display = self.x11.XOpenDisplay(None)
        if not self.display:
            raise RuntimeError('An X11 display (or XWayland) is required for QR preview')
        # Tk's public widget ID is inside a separate toplevel wrapper. Moving
        # only that widget leaves its blank wrapper over the main application.
        # Embed the whole toplevel so geometry updates and cleanup stay together.
        # wm_frame() reports the inner ID for override-redirect windows on
        # some Tk versions. Query X11 for its actual parent instead.
        top, wrapper = C.c_ulong(), C.c_ulong()
        children, count = C.POINTER(C.c_ulong)(), C.c_uint()
        if not self.x11.XQueryTree(self.display, self.root.winfo_id(), C.byref(top),
                                  C.byref(wrapper), C.byref(children), C.byref(count)):
            raise RuntimeError('Could not locate the QR preview wrapper')
        if children:
            self.x11.XFree(children)
        self.x11.XReparentWindow(self.display, wrapper.value, window, 0, 0)
        self.x11.XFlush(self.display)

    def set_static_picture(self, image):
        self.picture = cv2.imread(str(image))
        if self.picture is None:
            raise RuntimeError('The QR test image is unavailable')

    def iterate(self):
        self.root.update()
        now = time.monotonic()
        if now < self.next_frame:
            return
        self.next_frame = now + .1
        frame = self.picture
        if self.capture is not None:
            ok, frame = self.capture.read()
            if not ok:
                raise RuntimeError('Camera stopped delivering frames')
        if frame is None:
            return
        width, height = 640, 480
        if self.display:
            parent, x, y = C.c_ulong(), C.c_int(), C.c_int()
            w, h, border, depth = [C.c_uint() for _ in range(4)]
            self.x11.XGetGeometry(self.display, self.parent, C.byref(parent), C.byref(x), C.byref(y),
                                 C.byref(w), C.byref(h), C.byref(border), C.byref(depth))
            width, height = max(1, w.value), max(1, h.value)
            self.root.geometry(f'{width}x{height}+0+0')
        image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        image.thumbnail((width, height), Image.Resampling.BILINEAR)
        self.photo = ImageTk.PhotoImage(image, master=self.root)
        self.label.configure(image=self.photo)
        if now >= self.next_decode:
            self.next_decode = now + .4
            for value in self.decoder.decode(frame):
                if value != self.last_qr[0] or now - self.last_qr[1] >= 3:
                    self.last_qr = (value, now)
                    self.on_qr(value)

    def close(self):
        if self.capture is not None:
            self.capture.release(); self.capture = None
        if self.decoder:
            self.decoder.close(); self.decoder = None
        if self.display:
            self.x11.XCloseDisplay(self.display); self.display = None
        if self.root:
            self.root.destroy(); self.root = None
