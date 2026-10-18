"""Shared vector geometry for both native graphics backends."""
import math


class IconShapes:
    # @llr TLLR127
    def usb_power(self, powered, background):
        """Compact USB trident; a slash distinguishes off without relying on color."""
        color = '#71ddba' if powered is True else '#8d9db5'
        def draw(line, ellipse, rectangle, arc, polygon, curve, text):
            line([(15, 18), (15, 4)], color, 1.5)
            polygon([(15, 1), (12, 5), (18, 5)], color)
            line([(15, 14), (8, 10), (8, 7)], color, 1.5)
            ellipse((6, 4, 4, 4), color)
            line([(15, 12), (22, 9), (22, 6)], color, 1.5)
            rectangle((20, 3, 4, 4), color, 1.5)
            ellipse((13, 17, 4, 4), color, 1.5)
            if powered is False:
                line([(4, 21), (26, 1)], background, 4)
                line([(4, 21), (26, 1)], color, 1.5)
            elif powered is None:
                text('?', (0, 9, 9, 13), color, 10)
        return self._photo(('usb-power', powered, background), 30, 22, draw, background)

    def rounded_button(self, width, height, color, background):
        """Use the native antialiased renderer for smooth confirmation corners."""
        radius = min(18, height // 4, width // 2)
        def draw(line, ellipse, rectangle, arc, polygon, curve, text):
            polygon([(radius, 0), (width-radius, 0), (width-radius, height), (radius, height)], color)
            polygon([(0, radius), (width, radius), (width, height-radius), (0, height-radius)], color)
            for x in (0, width-2*radius):
                for y in (0, height-2*radius):
                    ellipse((x, y, 2*radius, 2*radius), color)
        return self._photo(('rounded-button', width, height, color, background), width, height, draw, background)

    def battery(self, percentage, background, charger_connected=False):
        color = '#8d9db5' if percentage is None else '#ff6b77' if percentage <= 10 else '#f0bc5e' if percentage <= 20 else '#71ddba'
        def draw(line, ellipse, rectangle, arc, polygon, curve, text):
            rectangle((2, 5, 23, 13), color, 1.5)
            line([(28, 9), (28, 14)], color, 2)
            if charger_connected:
                polygon([(15, 6), (9, 12), (13, 12), (11, 17), (19, 10), (15, 10)], '#f0bc5e')
            elif percentage is None:
                text('?', (3, 4, 20, 15), color, 12)
            elif percentage > 0:
                right = 5 + 17 * min(percentage, 100) / 100
                polygon([(5, 8), (right, 8), (right, 15), (5, 15)], color)
        return self._photo(('battery', percentage, background, charger_connected), 30, 22, draw, background)

    def callback(self, radius, foreground, ink):
        size = math.ceil(radius*2+4)
        unit = radius/20
        def draw(line, ellipse, rectangle, arc, polygon, curve, text):
            def pts(values):return [(size/2+x*unit,size/2+y*unit) for x,y in values]
            ellipse((2,2,size-4,size-4),foreground)
            curve(pts([(4,9),(17,9),(17,-7),(3,-7)]),ink,3*unit)
            line(pts([(3,-7),(-10,-7)]),ink,3*unit)
            line(pts([(-3,-14),(-10,-7),(-3,0)]),ink,3*unit)
        return self._photo(('callback',radius,foreground,ink),size,size,draw)

    def bluetooth(self, size, color, background, connected):
        def draw(line, ellipse, rectangle, arc, polygon, curve, text):
            def pts(values):return [(x*size/30,y*size/30) for x,y in values]
            line(pts([(15,3),(15,27),(23,20),(7,8)]),color,2)
            line(pts([(7,22),(23,10),(15,3)]),color,2)
            if connected is False:
                line(pts([(3,27),(27,3)]),background,5)
                line(pts([(3,27),(27,3)]),color,2)
        return self._photo(('bluetooth',size,color,background,connected),size,size,draw,background)

    def missed_call(self, radius, foreground, ink, count=0):
        size = math.ceil(radius*2+4)
        unit = radius/22
        top = 8*unit if count else 0
        width, height = math.ceil(size+(16*unit if count else 0)), math.ceil(size+top)
        center_x, center_y = size/2, size/2+top
        def draw(line, ellipse, rectangle, arc, polygon, curve, text):
            ellipse((2,2+top,size-4,size-4),foreground)
            def at(x,y):return center_x+x*unit,center_y+y*unit
            # A solid white receiver, with generous rounded earpieces.
            curve([at(-8,-6),at(-9,1),at(-1,9),at(6,8)],ink,6.5*unit)
            line([at(-9,-10),at(-7,-5)],ink,8*unit)
            line([at(5,7),at(10,9)],ink,8*unit)
            if count:
                # Both the corner notification and individual contacts show counts.
                box = (size-13*unit, unit, 26*unit, 26*unit)
                ellipse(box, '#191c23')
                ellipse(box, '#ffffff', 1.5*unit)
                label = str(count) if count <= 99 else '99+'
                font_size = (18 if count < 10 else 14 if count <= 99 else 11)*unit
                text(label, box, '#ffffff', font_size)
        return self._photo(('missed',radius,foreground,ink,count),width,height,draw)

    def connectivity(self, width, height, colors, background):
        # Keep the existing compact terminal -> Wi-Fi -> server arrangement.
        scale = min(width/252,height/45)
        def draw(line, ellipse, rectangle, arc, polygon, curve, text):
            def pts(values):return [(x*scale,y*scale) for x,y in values]
            def box(x,y,w,h):return tuple(value*scale for value in (x,y,w,h))
            thickness = 2
            rectangle(box(16,14,22,16),colors[0],thickness)
            line(pts([(27,30),(27,35)]),colors[0],thickness)
            line(pts([(20,35),(34,35)]),colors[0],thickness)
            for radius in (9,16,23):
                arc(box(121-radius,36-radius,2*radius,2*radius),225,90,colors[1],thickness)
            ellipse(box(119,34,4,4),colors[1])
            for y in (13,25):
                rectangle(box(205,y,25,8),colors[2],thickness)
                ellipse(box(208,y+3,2,2),colors[2])
            for start,end,color in [(48,87,colors[1]),(155,191,colors[2])]:
                line(pts([(start,25),(end-6,25)]),color,thickness)
                polygon(pts([(end,25),(end-8,21),(end-8,29)]),color)
        return self._photo(('network',width,height,*colors,background),width,height,draw,background)
