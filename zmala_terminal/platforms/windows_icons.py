"""Smooth Windows graphics for small terminal status icons at their actual size."""
import ctypes as C
from platforms.windows_text_renderer import P, I, U, F, ARGB, RectF
from icon_shapes import IconShapes


class PointF(C.Structure):
    _fields_ = [('x', F), ('y', F)]


class IconRenderer(IconShapes):
    def __init__(self, renderer):
        self.renderer, self.cache = renderer, {}
        self.dll = renderer.dll
        signatures = {
            'GdipSetSmoothingMode': ([P,I], I), 'GdipSetPixelOffsetMode': ([P,I], I),
            'GdipScaleWorldTransform': ([P,F,F,I], I),
            'GdipCreatePen1': ([U,F,I,P], I), 'GdipDeletePen': ([P], I),
            'GdipSetPenStartCap': ([P,I], I), 'GdipSetPenEndCap': ([P,I], I),
            'GdipSetPenLineJoin': ([P,I], I),
            'GdipDrawLines': ([P,P,P,I], I), 'GdipDrawBezier': ([P,P]+[F]*8, I),
            'GdipFillPolygon': ([P,P,P,I,I], I),
            'GdipFillEllipse': ([P,P,F,F,F,F], I), 'GdipDrawEllipse': ([P,P,F,F,F,F], I),
            'GdipDrawRectangle': ([P,P,F,F,F,F], I), 'GdipDrawArc': ([P,P]+[F]*6, I),
            'GdipSetStringFormatLineAlign': ([P,I], I),
        }
        for name, (arguments, result) in signatures.items():
            function = getattr(self.dll, name)
            function.argtypes, function.restype = arguments, result

    def _photo(self, key, width, height, draw, background=None):
        if key in self.cache:
            return self.cache[key]
        d, check = self.dll, self.renderer.check
        source, graphics, target, target_graphics = [P() for _ in range(4)]
        pens, brushes = {}, {}
        def brush(color):
            if color not in brushes:
                handle = P()
                check(d.GdipCreateSolidFill(0xff000000|int(color.lstrip('#'),16), C.byref(handle)))
                brushes[color] = handle
            return brushes[color]
        def pen(color, thickness):
            identity = (color, thickness)
            if identity not in pens:
                handle = P()
                # World units scale stroke widths with the supersampled drawing.
                check(d.GdipCreatePen1(0xff000000|int(color.lstrip('#'),16), thickness, 0, C.byref(handle)))
                pens[identity] = handle
                check(d.GdipSetPenStartCap(handle, 2));check(d.GdipSetPenEndCap(handle, 2))
                check(d.GdipSetPenLineJoin(handle, 2))
            return pens[identity]
        def points(values):
            return (PointF*len(values))(*(PointF(x,y) for x,y in values))
        def line(values, color, thickness):
            check(d.GdipDrawLines(graphics, pen(color,thickness), points(values), len(values)))
        def ellipse(box, color, thickness=0):
            function = d.GdipDrawEllipse if thickness else d.GdipFillEllipse
            check(function(graphics, pen(color,thickness) if thickness else brush(color), *box))
        def rectangle(box, color, thickness):
            check(d.GdipDrawRectangle(graphics, pen(color,thickness), *box))
        def arc(box, start, sweep, color, thickness):
            check(d.GdipDrawArc(graphics, pen(color,thickness), *box, start, sweep))
        def polygon(values, color):
            check(d.GdipFillPolygon(graphics, brush(color), points(values), len(values), 0))
        def curve(values, color, thickness):
            check(d.GdipDrawBezier(graphics, pen(color,thickness), *(coordinate for point in values for coordinate in point)))
        def text(value, box, color, size):
            family, font, format_ = P(), P(), P()
            try:
                check(d.GdipCreateFontFamilyFromName('Segoe UI', None, C.byref(family)))
                check(d.GdipCreateFont(family, size, 1, 0, C.byref(font)))
                check(d.GdipCreateStringFormat(0, 0, C.byref(format_)))
                check(d.GdipSetStringFormatAlign(format_, 1))
                check(d.GdipSetStringFormatLineAlign(format_, 1))
                check(d.GdipSetTextRenderingHint(graphics, 4))
                check(d.GdipDrawString(graphics, value, len(value), font, C.byref(RectF(*box)), format_, brush(color)))
            finally:
                for handle, dispose in [(format_, d.GdipDeleteStringFormat), (font, d.GdipDeleteFont), (family, d.GdipDeleteFontFamily)]:
                    if handle:dispose(handle)
        try:
            # Draw at four times the final size; preserve alpha on portrait badges.
            check(d.GdipCreateBitmapFromScan0(width*4, height*4, 0, ARGB, None, C.byref(source)))
            check(d.GdipGetImageGraphicsContext(source, C.byref(graphics)))
            clear = 0 if background is None else 0xff000000|int(background.lstrip('#'),16)
            check(d.GdipGraphicsClear(graphics, clear))
            check(d.GdipSetSmoothingMode(graphics, 4))
            check(d.GdipScaleWorldTransform(graphics, 4, 4, 0))
            draw(line, ellipse, rectangle, arc, polygon, curve, text)
            check(d.GdipCreateBitmapFromScan0(width, height, 0, ARGB, None, C.byref(target)))
            check(d.GdipGetImageGraphicsContext(target, C.byref(target_graphics)))
            check(d.GdipGraphicsClear(target_graphics, clear))
            check(d.GdipSetInterpolationMode(target_graphics, 7))
            check(d.GdipSetPixelOffsetMode(target_graphics, 4))
            check(d.GdipDrawImageRectI(target_graphics, source, 0, 0, width, height))
            photo = self.renderer.bitmap_photo(target, width, height, transparent=background is None)
            if len(self.cache) >= 40:
                self.cache.clear()
            self.cache[key] = photo
            return photo
        finally:
            for handle in pens.values():d.GdipDeletePen(handle)
            for handle in brushes.values():d.GdipDeleteBrush(handle)
            for handle in [graphics,target_graphics]:
                if handle:d.GdipDeleteGraphics(handle)
            for handle in [source,target]:
                if handle:d.GdipDisposeImage(handle)

