"""Render this application's Unicode text with Windows GDI+ shaping and bidi.

Tk 8.6 remains the window/layout host. No desktop capture or OS input is used.
"""
import ctypes as C
import math
import struct
import tkinter as tk
import unicodedata
import zlib
from render_cache import (RenderCache, portrait_size, photo_bytes, TEXT_BYTES,
                          PORTRAIT_BYTES, SOURCE_BYTES)

P, I, U, F = C.c_void_p, C.c_int, C.c_uint, C.c_float
ARGB = 0x26200A


class Startup(C.Structure):
    _fields_ = [('version', U), ('debug', P), ('no_thread', I), ('no_codecs', I)]


class RectF(C.Structure):
    _fields_ = [('x', F), ('y', F), ('width', F), ('height', F)]


class Rect(C.Structure):
    _fields_ = [('x', I), ('y', I), ('width', I), ('height', I)]


class BitmapData(C.Structure):
    _fields_ = [('width', U), ('height', U), ('stride', I), ('format', I), ('scan', P), ('reserved', C.c_size_t)]


def right_to_left(text):
    return next((unicodedata.bidirectional(c) in ('R', 'AL') for c in text
                 if unicodedata.bidirectional(c) in ('L', 'R', 'AL')), False)


class TextRenderer:
    def __init__(self, root):
        self.root = root
        self.cache = RenderCache(200, max_bytes=TEXT_BYTES, size_of=photo_bytes)
        self.portraits = RenderCache(120, max_bytes=PORTRAIT_BYTES, size_of=photo_bytes)
        self.dll = C.WinDLL('gdiplus')
        signatures = {
            'GdiplusStartup': ([P, P, P], I), 'GdiplusShutdown': ([C.c_size_t], None),
            'GdipCreateBitmapFromScan0': ([I, I, I, I, P, P], I),
            'GdipGetImageGraphicsContext': ([P, P], I), 'GdipDeleteGraphics': ([P], I),
            'GdipDisposeImage': ([P], I), 'GdipGraphicsClear': ([P, U], I),
            'GdipLoadImageFromFile': ([C.c_wchar_p, P], I),
            'GdipGetImageWidth': ([P, P], I), 'GdipGetImageHeight': ([P, P], I),
            'GdipDrawImageRectI': ([P, P, I, I, I, I], I), 'GdipSetInterpolationMode': ([P, I], I),
            'GdipCreateFontFamilyFromName': ([C.c_wchar_p, P, P], I),
            'GdipDeleteFontFamily': ([P], I), 'GdipCreateFont': ([P, F, I, I, P], I),
            'GdipDeleteFont': ([P], I), 'GdipCreateStringFormat': ([I, U, P], I),
            'GdipDeleteStringFormat': ([P], I), 'GdipSetStringFormatAlign': ([P, I], I),
            'GdipMeasureString': ([P, C.c_wchar_p, I, P, P, P, P, P, P], I),
            'GdipCreateSolidFill': ([U, P], I), 'GdipDeleteBrush': ([P], I),
            'GdipSetTextRenderingHint': ([P, I], I),
            'GdipDrawString': ([P, C.c_wchar_p, I, P, P, P, P], I),
            'GdipBitmapLockBits': ([P, P, U, I, P], I), 'GdipBitmapUnlockBits': ([P, P], I),
        }
        for name, (arguments, result) in signatures.items():
            function = getattr(self.dll, name)
            function.argtypes, function.restype = arguments, result
        self.token = C.c_size_t()
        self.check(self.dll.GdiplusStartup(C.byref(self.token), C.byref(Startup(1, None, 0, 0)), None))
        self.sources = RenderCache(40, max_bytes=SOURCE_BYTES,
                                  size_of=lambda entry: entry[1] * entry[2] * 4,
                                  release=lambda entry: self.dll.GdipDisposeImage(entry[0]))

    @staticmethod
    def check(status):
        if status:
            raise RuntimeError(f'Windows text rendering failed ({status})')

    def photo(self, text, family, size, background, foreground, width, bold=False, rtl=None):
        if not text:
            return None
        rtl = right_to_left(text) if rtl is None else rtl
        width = max(16, int(width))
        key = (text, family, size, background, foreground, width, bold, rtl)
        if key in self.cache:
            return self.cache[key]
        d = self.dll
        bitmap, graphics, font_family, font, format_, brush = [P() for _ in range(6)]
        try:
            self.check(d.GdipCreateBitmapFromScan0(1, 1, 0, ARGB, None, C.byref(bitmap)))
            self.check(d.GdipGetImageGraphicsContext(bitmap, C.byref(graphics)))
            self.check(d.GdipCreateFontFamilyFromName(family, None, C.byref(font_family)))
            self.check(d.GdipCreateFont(font_family, size*96/72, int(bold), 2, C.byref(font)))
            self.check(d.GdipCreateStringFormat(int(rtl), 0, C.byref(format_)))
            self.check(d.GdipSetStringFormatAlign(format_, 1))
            layout, measured = RectF(0, 0, width-4, 10000), RectF()
            count = len(text.encode('utf-16-le'))//2
            self.check(d.GdipMeasureString(graphics, text, count, font, C.byref(layout), format_, C.byref(measured), None, None))
            height = max(1, math.ceil(measured.height)+4)
            d.GdipDeleteGraphics(graphics); graphics = P()
            d.GdipDisposeImage(bitmap); bitmap = P()
            self.check(d.GdipCreateBitmapFromScan0(width, height, 0, ARGB, None, C.byref(bitmap)))
            self.check(d.GdipGetImageGraphicsContext(bitmap, C.byref(graphics)))
            self.check(d.GdipGraphicsClear(graphics, 0xff000000|int(background.lstrip('#'), 16)))
            self.check(d.GdipCreateSolidFill(0xff000000|int(foreground.lstrip('#'), 16), C.byref(brush)))
            self.check(d.GdipSetTextRenderingHint(graphics, 4))
            layout = RectF(2, 2, width-4, height-2)
            self.check(d.GdipDrawString(graphics, text, count, font, C.byref(layout), format_, brush))
            image = self.bitmap_photo(bitmap, width, height)
            self.cache[key] = image
            return image
        finally:
            for handle, cleanup in [(brush,d.GdipDeleteBrush),(format_,d.GdipDeleteStringFormat),
                                     (font,d.GdipDeleteFont),(font_family,d.GdipDeleteFontFamily),
                                     (graphics,d.GdipDeleteGraphics),(bitmap,d.GdipDisposeImage)]:
                if handle:
                    cleanup(handle)

    def bitmap_photo(self, bitmap, width, height, transparent=False):
        """Copy locked GDI+ pixels into a Tk-owned image before releasing the native bitmap lock."""
        data = BitmapData()
        self.check(self.dll.GdipBitmapLockBits(bitmap, C.byref(Rect(0, 0, width, height)), 1, ARGB, C.byref(data)))
        try:
            raw = b''.join(C.string_at(data.scan+y*data.stride, width*4) for y in range(height))
            if transparent:
                rgba = bytearray(raw)
                rgba[0::4], rgba[2::4] = raw[2::4], raw[0::4]
                rows = b''.join(b'\0'+rgba[y*width*4:(y+1)*width*4] for y in range(height))
                def chunk(kind, content):
                    return struct.pack('>I', len(content))+kind+content+struct.pack('>I', zlib.crc32(kind+content))
                png = b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR', struct.pack('>2I5B', width, height, 8, 6, 0, 0, 0))
                png += chunk(b'IDAT', zlib.compress(rows))+chunk(b'IEND', b'')
                return tk.PhotoImage(master=self.root, data=png, format='PNG')
            rgb = bytearray(width*height*3)
            rgb[0::3], rgb[1::3], rgb[2::3] = raw[2::4], raw[1::4], raw[0::4]
        finally:
            self.dll.GdipBitmapUnlockBits(bitmap, C.byref(data))
        return tk.PhotoImage(master=self.root, data=f'P6\n{width} {height}\n255\n'.encode()+rgb, format='PPM')

    def portrait(self, path, size, background, fast=False):
        """Resize smoothly to the current animation frame, preserving aspect ratio."""
        path, size = str(path), portrait_size(size)
        key = (path, size, background, fast)
        if key in self.portraits:
            return self.portraits[key]
        if path not in self.sources:
            source, width, height = P(), U(), U()
            self.check(self.dll.GdipLoadImageFromFile(path, C.byref(source)))
            try:
                self.check(self.dll.GdipGetImageWidth(source, C.byref(width)))
                self.check(self.dll.GdipGetImageHeight(source, C.byref(height)))
                width, height = width.value, height.value
                if width <= 0 or height <= 0:
                    raise ValueError('Portrait has invalid dimensions')
                self.sources[path] = (source, width, height)
            except Exception:
                self.dll.GdipDisposeImage(source)
                raise
        else:
            source, width, height = self.sources[path]
        # Oversized sources are used once, then disposed by this render call.
        cached_source = path in self.sources
        ratio = size/max(width, height)
        width, height = max(1,round(width*ratio)), max(1,round(height*ratio))
        bitmap, graphics = P(), P()
        try:
            self.check(self.dll.GdipCreateBitmapFromScan0(width, height, 0, ARGB, None, C.byref(bitmap)))
            self.check(self.dll.GdipGetImageGraphicsContext(bitmap, C.byref(graphics)))
            self.check(self.dll.GdipGraphicsClear(graphics, 0xff000000|int(background.lstrip('#'),16)))
            self.check(self.dll.GdipSetInterpolationMode(graphics, 3 if fast else 7))
            self.check(self.dll.GdipDrawImageRectI(graphics, source, 0, 0, width, height))
            image = self.bitmap_photo(bitmap, width, height)
            self.portraits[key] = image
            return image
        finally:
            if graphics:
                self.dll.GdipDeleteGraphics(graphics)
            if bitmap:
                self.dll.GdipDisposeImage(bitmap)
            if not cached_source:
                self.dll.GdipDisposeImage(source)

    def close(self):
        self.cache.clear()
        self.portraits.clear()
        self.sources.clear()
        if self.token.value:
            self.dll.GdiplusShutdown(self.token)
            self.token.value = 0
