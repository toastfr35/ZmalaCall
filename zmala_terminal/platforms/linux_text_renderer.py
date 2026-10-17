"""Pango shapes Unicode/bidi text; Cairo and Pillow produce smooth Tk images."""
import io
import tkinter as tk
import cairo
import gi
gi.require_version('Pango', '1.0')
gi.require_version('PangoCairo', '1.0')
from gi.repository import Pango, PangoCairo
from PIL import Image, ImageTk
from render_cache import RenderCache, portrait_size


def color_rgb(color):
    return tuple(int(color[i:i+2], 16) / 255 for i in (1, 3, 5))


def layout_for(context, text, family, size, width, bold=False):
    layout = PangoCairo.create_layout(context)
    font = Pango.FontDescription()
    font.set_family('Sans' if family == 'TkDefaultFont' else family)
    font.set_size(round(size * Pango.SCALE))
    font.set_weight(Pango.Weight.BOLD if bold else Pango.Weight.NORMAL)
    PangoCairo.context_set_resolution(layout.get_context(), 96)
    layout.set_font_description(font)
    layout.set_text(text, -1)
    layout.set_width(max(1, width) * Pango.SCALE)
    layout.set_wrap(Pango.WrapMode.WORD_CHAR)
    layout.set_alignment(Pango.Alignment.CENTER)
    return layout


class TextRenderer:
    def __init__(self, root):
        self.root = root
        self.cache, self.portraits, self.sources = RenderCache(200), RenderCache(120), {}

    def surface_photo(self, surface):
        output = io.BytesIO()
        surface.write_to_png(output)
        return tk.PhotoImage(master=self.root, data=output.getvalue(), format='PNG')

    def photo(self, text, family, size, background, foreground, width, bold=False, rtl=None):
        if not text:
            return None
        width = max(16, int(width))
        key = (text, family, size, background, foreground, width, bold, rtl)
        if key not in self.cache:
            measurement = cairo.Context(cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1))
            layout = layout_for(measurement, text, family, size, width - 4, bold)
            _, height = layout.get_pixel_size()
            surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height + 4)
            context = cairo.Context(surface)
            context.set_source_rgb(*color_rgb(background)); context.paint()
            context.set_source_rgb(*color_rgb(foreground)); context.move_to(2, 2)
            PangoCairo.update_layout(context, layout)
            PangoCairo.show_layout(context, layout)
            self.cache[key] = self.surface_photo(surface)
        return self.cache[key]

    def portrait(self, path, size, background, fast=False):
        path, size = str(path), portrait_size(size)
        key = (path, size, background, fast)
        if key not in self.portraits:
            if path not in self.sources:
                with Image.open(path) as source:
                    source.load()
                    image = source.convert('RGBA')
                # Large uploads should not multiply the Pi's memory consumption.
                image.thumbnail((1200, 1200), Image.Resampling.LANCZOS)
                if len(self.sources) >= 40:
                    self.sources.clear()
                preview = image.copy()
                # Moving cards never exceed 460 px. Flatten alpha once per
                # background, avoiding Pillow's premultiply/resize round trip.
                preview.thumbnail((460, 460), Image.Resampling.LANCZOS)
                self.sources[path] = (image, preview, RenderCache(4))
            source, preview, backgrounds = self.sources[path]
            if fast:
                if background not in backgrounds:
                    flattened = Image.new('RGBA', preview.size, background)
                    flattened.alpha_composite(preview)
                    backgrounds[background] = flattened.convert('RGB')
                source = backgrounds[background]
            ratio = size / max(source.size)
            dimensions = tuple(max(1, round(value * ratio)) for value in source.size)
            image = source.resize(dimensions, Image.Resampling.BILINEAR if fast else Image.Resampling.LANCZOS)
            canvas = image
            if not fast:
                canvas = Image.new('RGBA', dimensions, background)
                canvas.alpha_composite(image)
            self.portraits[key] = ImageTk.PhotoImage(canvas, master=self.root)
        return self.portraits[key]

    def close(self):
        self.cache.clear(); self.portraits.clear(); self.sources.clear()
