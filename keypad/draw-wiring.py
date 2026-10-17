"""Generate editable SVG wiring sheets; uses only the Python standard library.

Pins are logical Nano pin labels, not breadboard positions. The MOSFET symbols
label electrical terminals explicitly because package pin order varies by part.
"""
from html import escape
from pathlib import Path
import argparse

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--mosfet', action='store_true', help='Draw the optional higher-current lamp drivers')
USE_MOSFET = parser.parse_args().mosfet
HEIGHT = 1260 if USE_MOSFET else 1120
GROUND_Y = 1105 if USE_MOSFET else 965

ROOT = Path(__file__).resolve().parent
parts = []
BLUE, RED, GROUND, LAMP = '#2463a0', '#bd3434', '#435060', '#b45d10'


def text(x, y, value, size=18, fill='#182431', anchor='start', weight='400'):
    parts.append(f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}" '
                 f'text-anchor="{anchor}" font-weight="{weight}">{escape(value)}</text>')


def wire(points, color=GROUND, width=3):
    points = ' '.join(f'{x},{y}' for x, y in points)
    parts.append(f'<polyline points="{points}" fill="none" stroke="{color}" '
                 f'stroke-width="{width}" stroke-linejoin="round"/>')


def box(x, y, w, h, fill='white', stroke='#b9c6d2', radius=8):
    parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" '
                 f'fill="{fill}" stroke="{stroke}" stroke-width="2"/>')


def dot(x, y, color=GROUND, radius=4):
    parts.append(f'<circle cx="{x}" cy="{y}" r="{radius}" fill="{color}"/>')


def terminal(x, y, color=GROUND):
    parts.append(f'<circle cx="{x}" cy="{y}" r="4" fill="white" '
                 f'stroke="{color}" stroke-width="2"/>')


def ground(x, y):
    wire([(x, y), (x, y + 10)])
    for width, offset in [(24, 10), (16, 17), (8, 24)]:
        wire([(x - width / 2, y + offset), (x + width / 2, y + offset)], width=2)


parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="1480" height="{HEIGHT}" '
             f'viewBox="0 0 1480 {HEIGHT}" role="img" aria-labelledby="title desc">')
parts.append('<title id="title">ZmalaCall Nano keypad wiring</title>')
driver_description = 'MOSFET drivers' if USE_MOSFET else '1 kilohm resistors directly from GPIO'
parts.append('<desc id="desc">Four normally-open switches on D2 to D5, and four '
             f'LEDs controlled by {driver_description} on D6 to D9. USB supplies '
             'serial data and power. All grounds connect to Nano GND.</desc>')
parts.append(f'<rect width="1480" height="{HEIGHT}" fill="white"/>')
parts.append('<g font-family="Arial, Helvetica, sans-serif">')
text(50, 62, 'ZmalaCall · USB serial keypad', 34, weight='700')
text(50, 100, 'Classic 5 V Arduino Nano / ATmega328P · four arcade switches + four LEDs', 22)
text(50, 135, 'Logical net labels: connect D2–D9 to the matching Nano pins. All GND symbols are the same connection.', 18, GROUND)

box(100, 172, 340, 85, '#f1f5fa')
text(270, 204, 'Raspberry Pi / Windows PC', 20, anchor='middle', weight='700')
text(270, 233, 'USB data cable · power + serial', 18, anchor='middle')
wire([(440, 214), (570, 214)], BLUE, 5)
text(505, 198, 'USB', 16, BLUE, 'middle')
box(570, 165, 560, 100, '#e9f2ee', '#558b75')
text(600, 196, 'ARDUINO NANO', 23, weight='700')
text(600, 225, 'Inputs D2–D5 · outputs D6–D9', 19)
text(600, 250, 'D0 / D1 reserved for USB serial', 16, GROUND)
if USE_MOSFET:
    text(1020, 239, '5V', 17, RED, 'end', '700')
    wire([(1030, 246), (1030, 292)], RED)
text(1110, 239, 'GND', 17, GROUND, 'end', '700')
wire([(1120, 246), (1450, 246), (1450, GROUND_Y), (50, GROUND_Y)], GROUND)
if USE_MOSFET:
    wire([(50, 292), (1420, 292)], RED)
    dot(1030, 292, RED)
    text(50, 282, '+5 V from Nano USB supply', 17, RED, weight='700')
else:
    text(50, 294, 'Resistors only · each LED is powered by its GPIO output through a 1 kΩ resistor.', 20, BLUE, weight='700')

controls = [('LEFT', 2, 6, 'L / l', '#eaf2fb'),
            ('RIGHT', 3, 7, 'R / r', '#eaf2fb'),
            ('GREEN', 4, 8, 'G / g', '#e9f5ee'),
            ('RED', 5, 9, 'X / x', '#fbeeed')]
for index, (name, switch_pin, lamp_pin, codes, tint) in enumerate(controls):
    x = 50 + index * 352
    box(x, 320, 324, 755 if USE_MOSFET else 615, tint)
    text(x + 162, 358, name, 23, anchor='middle', weight='700')
    text(x + 162, 388, f'Press: {codes[0]}  ·  LED: {codes}', 17, anchor='middle')

    # Switch circuit, with distinct NO and COM contacts. The third NC contact
    # is deliberately omitted: it is not connected in this design.
    text(x + 24, 429, 'SWITCH', 16, BLUE, weight='700')
    text(x + 52, 471, f'D{switch_pin}', 20, BLUE, 'middle', '700')
    terminal(x + 82, 465, BLUE)
    wire([(x + 82, 465), (x + 150, 465), (x + 150, 480)], BLUE)
    terminal(x + 150, 480, BLUE)
    terminal(x + 150, 530)
    wire([(x + 150, 530), (x + 176, 491)], GROUND)
    text(x + 192, 484, 'NO', 17)
    text(x + 192, 535, 'COM', 17)
    wire([(x + 150, 530), (x + 150, 556)])
    ground(x + 150, 556)
    text(x + 192, 580, 'GND', 16, GROUND)
    text(x + 162, 615, 'Momentary · normally open', 17, anchor='middle')
    text(x + 162, 640, 'INPUT_PULLUP · NC unused', 16, GROUND, 'middle')

    if not USE_MOSFET:
        text(x + 24, 689, 'LED · DIRECT GPIO', 16, LAMP, weight='700')
        text(x + 35, 794, f'D{lamp_pin}', 20, BLUE, 'middle', '700')
        terminal(x + 62, 788, BLUE)
        wire([(x + 62, 788), (x + 82, 788)], BLUE)
        box(x + 82, 779, 43, 18, 'white', BLUE, 0)
        text(x + 103, 769, '1 kΩ', 16, BLUE, 'middle')
        wire([(x + 125, 788), (x + 180, 788)], BLUE)
        box(x + 180, 750, 118, 78, 'white', LAMP, 4)
        text(x + 239, 775, 'Bare LED', 17, LAMP, 'middle', '700')
        text(x + 190, 794, '+', 17, LAMP)
        text(x + 239, 802, 'anode / cathode', 12, LAMP, 'middle')
        text(x + 233, 822, '−', 17, LAMP, 'middle')
        wire([(x + 233, 828), (x + 233, GROUND_Y)])
        # The reset pull-down belongs on the GPIO side of the series resistor.
        dot(x + 70, 788, BLUE)
        wire([(x + 70, 788), (x + 70, 864)], BLUE)
        box(x + 61, 864, 18, 40, 'white', GROUND, 0)
        text(x + 92, 892, '10 kΩ', 16, GROUND)
        wire([(x + 70, 904), (x + 70, GROUND_Y)])
        dot(x + 70, GROUND_Y)
        dot(x + 233, GROUND_Y)
        continue

    # LED +5V branch runs at the right of the panel, away from switch wiring.
    wire([(x + 303, 292), (x + 303, 681), (x + 233, 681), (x + 233, 715)], RED)
    dot(x + 303, 292, RED)
    text(x + 24, 689, 'LED DRIVER', 16, LAMP, weight='700')
    box(x + 168, 715, 130, 73, 'white', LAMP, 4)
    text(x + 233, 740, '+  5 V lamp', 17, LAMP, 'middle', '700')
    text(x + 233, 764, 'current-limited', 14, LAMP, 'middle')
    text(x + 233, 782, '−', 17, LAMP, 'middle')
    wire([(x + 233, 788), (x + 233, 852)], LAMP)

    # MOSFET functional symbol: D/G/S are electrical terminals, not a package
    # footprint. This avoids suggesting an incorrect physical lead order.
    box(x + 180, 852, 118, 90, 'white', GROUND, 4)
    text(x + 233, 870, 'D', 15, anchor='middle', weight='700')
    text(x + 190, 902, 'G', 15, weight='700')
    text(x + 248, 902, 'Q' + str(index + 1), 18, anchor='middle', weight='700')
    text(x + 239, 919, 'N-MOSFET', 11, anchor='middle')
    text(x + 233, 935, 'S', 15, anchor='middle', weight='700')
    text(x + 35, 902, f'D{lamp_pin}', 20, BLUE, 'middle', '700')
    terminal(x + 62, 896, BLUE)
    wire([(x + 62, 896), (x + 82, 896)], BLUE)
    box(x + 82, 887, 43, 18, 'white', BLUE, 0)
    text(x + 103, 878, '220 Ω', 15, BLUE, 'middle')
    wire([(x + 125, 896), (x + 180, 896)], BLUE)
    dot(x + 150, 896, BLUE)
    wire([(x + 150, 896), (x + 150, 979)], BLUE)
    box(x + 141, 979, 18, 40, 'white', GROUND, 0)
    text(x + 129, 1006, '10 kΩ', 15, GROUND, 'end')
    wire([(x + 150, 1019), (x + 150, 1040), (x + 233, 1040)])
    wire([(x + 233, 942), (x + 233, 1105)])
    dot(x + 233, 1040)
    dot(x + 233, 1105)

if USE_MOSFET:
    text(50, 1133, 'COMMON GND · Nano GND, all switch COM terminals, all gate pull-downs and MOSFET sources', 17, GROUND, weight='700')
    text(50, 1178, 'Q1–Q4: logic-level N-channel MOSFETs, suitable at 5 V gate drive. Check the chosen part’s D / G / S pinout.', 18)
    text(50, 1210, 'Lamp modules must include 5 V current limiting. Keep LED and switch terminals separate. Total USB load ≤ 150 mA.', 18)
    text(50, 1241, 'No Pi GPIO connection or external supply. GPIO pins drive gates only, never the lamps directly.', 18, weight='700')
else:
    text(50, 996, 'COMMON GND · Nano GND, switch COM terminals, LED cathodes and output pull-downs', 17, GROUND, weight='700')
    text(50, 1040, 'Four 1 kΩ series resistors limit LED current; four 10 kΩ pull-downs keep outputs low during reset.', 18)
    text(50, 1072, 'High-efficiency, non-flashing LEDs · about 1.5–3.5 mA per LED. Check brightness through the button caps.', 18)
    text(50, 1104, 'Do not connect LED anodes to the Nano 5V pin in this circuit. Keep LED and switch terminals separate.', 18, weight='700')
parts.append('</g></svg>')
destination = ROOT / ('wiring-mosfet.svg' if USE_MOSFET else 'wiring.svg')
destination.write_text('\n'.join(parts) + '\n', encoding='utf-8')
print(destination)
