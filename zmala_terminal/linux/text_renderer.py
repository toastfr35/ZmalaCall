"""Pango shapes Unicode/bidi text; Cairo and Pillow produce smooth Tk images."""
import io
import tkinter as tk
import cairo
import gi
gi.require_version('Pango', '1.0')
gi.require_version('PangoCairo', '1.0')
from gi.repository import Pango, PangoCairo
from PIL import Image, ImageTk
from zmala_terminal.common.image_bounds import check_file, checked_size
from zmala_terminal.common.render_cache import (RenderCache, portrait_size, photo_bytes, TEXT_BYTES,
                          PORTRAIT_BYTES, SOURCE_BYTES, BACKGROUND_BYTES)


def color_rgb(color):
    return tuple(int(color[i:i+2], 16) / 255 for i in (1, 3, 5))


# @llr LLR-TERM-UI-009
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
        self.cache = RenderCache(200, max_bytes=TEXT_BYTES, size_of=photo_bytes)
        self.portraits = RenderCache(120, max_bytes=PORTRAIT_BYTES, size_of=photo_bytes)
        self.sources = RenderCache(40, max_bytes=SOURCE_BYTES,
                                  size_of=lambda pair: sum(image.width * image.height * 4 for image in pair))
        self.backgrounds = RenderCache(120, max_bytes=BACKGROUND_BYTES,
                                      size_of=lambda image: image.width * image.height * 4)

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
            photo = self.surface_photo(surface)
            self.cache[key] = photo
            return photo
        return self.cache[key]

    def portrait(self, path, size, background, fast=False):
        path, size = str(path), portrait_size(size)
        key = (path, size, background, fast)
        if key not in self.portraits:
            if path not in self.sources:
                check_file(path)
                with Image.open(path) as source:
                    checked_size(*source.size)
                    source.load()
                    image = source.convert('RGBA')
                # Large uploads should not multiply the Pi's memory consumption.
                image.thumbnail((1200, 1200), Image.Resampling.LANCZOS)
                preview = image.copy()
                # Moving cards never exceed 460 px. Flatten alpha once per
                # background, avoiding Pillow's premultiply/resize round trip.
                preview.thumbnail((460, 460), Image.Resampling.LANCZOS)
                self.sources[path] = (image, preview)
                source = image
            else:
                source, preview = self.sources[path]
            if fast:
                background_key = (path, background)
                if background_key not in self.backgrounds:
                    flattened = Image.new('RGBA', preview.size, background)
                    flattened.alpha_composite(preview)
                    source = flattened.convert('RGB')
                    self.backgrounds[background_key] = source
                else:
                    source = self.backgrounds[background_key]
            ratio = size / max(source.size)
            dimensions = tuple(max(1, round(value * ratio)) for value in source.size)
            image = source.resize(dimensions, Image.Resampling.BILINEAR if fast else Image.Resampling.LANCZOS)
            canvas = image
            if not fast:
                canvas = Image.new('RGBA', dimensions, background)
                canvas.alpha_composite(image)
            photo = ImageTk.PhotoImage(canvas, master=self.root)
            self.portraits[key] = photo
            return photo
        return self.portraits[key]

    def close(self):
        self.cache.clear(); self.portraits.clear(); self.sources.clear(); self.backgrounds.clear()
