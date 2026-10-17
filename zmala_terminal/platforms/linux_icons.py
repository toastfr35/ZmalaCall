"""Cairo draws the shared status geometry with antialiased strokes."""
import math
import cairo
from gi.repository import PangoCairo
from icon_shapes import IconShapes
from platforms.linux_text_renderer import color_rgb, layout_for


class IconRenderer(IconShapes):
    def __init__(self, renderer):
        self.renderer, self.cache = renderer, {}

    def _photo(self, key, width, height, draw, background=None):
        if key in self.cache:
            return self.cache[key]
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        context = cairo.Context(surface)
        if background:
            context.set_source_rgb(*color_rgb(background)); context.paint()
        context.set_line_cap(cairo.LINE_CAP_ROUND)
        context.set_line_join(cairo.LINE_JOIN_ROUND)
        def finish(color, thickness=0):
            context.set_source_rgb(*color_rgb(color))
            if thickness:
                context.set_line_width(thickness); context.stroke()
            else:
                context.fill()
        def line(points, color, thickness):
            context.move_to(*points[0])
            for point in points[1:]:
                context.line_to(*point)
            finish(color, thickness)
        def ellipse(box, color, thickness=0):
            x, y, w, h = box
            context.save(); context.translate(x + w/2, y + h/2)
            context.scale(w/2, h/2); context.arc(0, 0, 1, 0, math.tau)
            context.restore(); finish(color, thickness)
        def rectangle(box, color, thickness):
            context.rectangle(*box); finish(color, thickness)
        def arc(box, start, sweep, color, thickness):
            x, y, w, h = box
            context.save(); context.translate(x+w/2, y+h/2); context.scale(w/2, h/2)
            context.arc(0, 0, 1, math.radians(start), math.radians(start+sweep))
            context.restore(); finish(color, thickness)
        def polygon(points, color):
            context.move_to(*points[0])
            for point in points[1:]:
                context.line_to(*point)
            context.close_path(); finish(color)
        def curve(points, color, thickness):
            context.move_to(*points[0]); context.curve_to(*(v for point in points[1:] for v in point))
            finish(color, thickness)
        def text(value, box, color, size):
            x, y, w, h = box
            # Shared icon font sizes use pixels, Pango uses points.
            layout = layout_for(context, value, 'Noto Sans', size * .75, round(w), True)
            _, height = layout.get_pixel_size()
            context.set_source_rgb(*color_rgb(color)); context.move_to(x, y + (h-height)/2)
            PangoCairo.show_layout(context, layout)
        draw(line, ellipse, rectangle, arc, polygon, curve, text)
        if len(self.cache) >= 40:
            self.cache.clear()
        self.cache[key] = self.renderer.surface_photo(surface)
        return self.cache[key]
