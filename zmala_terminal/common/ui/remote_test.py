"""English installation-only button tutorial, driven by physical HID events."""
import tkinter as tk
import time
from zmala_terminal.common.model import State
from zmala_terminal.common.theme import BG, FG, MUTED, GREEN, PANEL
from zmala_terminal.common.remote_test import BUTTONS, RemoteTest

NAMES = {'left': 'Left', 'right': 'Right', 'green': 'Green',
         'red': 'Red', 'pointer': 'Middle'}


class RemoteTestView:
    def build_remote_test(self):
        self.remote_test = RemoteTest(self.enrollment.path.parent / 'remote-test.json')
        self.remote_test_page = tk.Canvas(self.root, bg=BG, highlightthickness=0)
        self.remote_test_signature = None

    def remote_setup_blocked(self):
        return self.model.state == State.HOME and self.needs_pairing()

    def remote_test_event(self, button, pressed):
        """Called only by the Presenter reader, before normal actions."""
        if not self.remote_setup_blocked():
            return False
        if self.needs_c20():
            return True
        self.remote_test.event(button, pressed)
        self.last_button = time.monotonic()
        # The final release is consumed too; it cannot activate the next page.
        self.render()
        return True

    def draw_remote_test(self):
        test = self.remote_test
        w, h = self.root.winfo_width(), self.root.winfo_height()
        signature = (w, h, test.index, test.armed, test.error)
        c = self.remote_test_page
        if signature != self.remote_test_signature:
            self.remote_test_signature = signature
            c.delete('all')
            scale = min(w/1280, h/720)
            ox, oy = (w-1280*scale)/2, (h-720*scale)/2

            def coords(*values):
                return [value*scale + (ox if i % 2 == 0 else oy) for i, value in enumerate(values)]

            def text(x, y, value, size=24, color=FG, **kw):
                c.create_text(*coords(x, y), text=value, fill=color,
                              font=(self.font_family, max(12, round(size*scale))), **kw)

            text(640, 62, 'Test your remote', 34)
            text(640, 113, 'Press and release each highlighted button.', 22, MUTED)
            text(340, 171, 'Front of remote', 19, MUTED)
            c.create_oval(*coords(235, 200, 445, 410), fill='#252d39', outline='#617084', width=2)
            c.create_rectangle(*coords(235, 305, 445, 535), fill='#252d39', outline='')
            c.create_oval(*coords(235, 430, 445, 640), fill='#252d39', outline='#617084', width=2)
            c.create_rectangle(*coords(237, 305, 443, 535), fill='#252d39', outline='')
            shapes = {'green': (274, 222, 406, 354), 'left': (254, 367, 330, 443),
                      'right': (350, 367, 426, 443), 'pointer': (263, 459, 417, 521),
                      'red': (286, 524, 394, 632)}
            for button, box in shapes.items():
                active = button == test.expected
                color = GREEN if active else '#617084'
                c.create_oval(*coords(*box), fill=PANEL,
                              outline=color, width=round((5 if active else 2)*scale))
                x, y = (box[0]+box[2])/2, (box[1]+box[3])/2
                if button in ('green', 'red'):
                    # The physical remote has round stickers covering both logos.
                    radius = 44
                    c.create_oval(*coords(x-radius, y-radius, x+radius, y+radius),
                                  fill='#15db2b' if button == 'green' else '#ff252b', outline='')
                else:
                    text(x, y, {'left': '‹', 'right': '›', 'pointer': '✳'}[button],
                         36 if button in ('left', 'right') else 23, GREEN if active else FG)
            for index, button in enumerate(BUTTONS):
                done, active = index < test.index, index == test.index
                text(570, 235+64*index, ('✓' if done else str(index+1)) + '   ' + NAMES[button],
                     25, GREEN if done or active else MUTED, anchor='w')
            instruction = ('Could not save. Press and release Middle to retry.' if test.error else
                           ('Now release: ' if test.armed else 'Press: ') + NAMES[test.expected])
            text(570, 588, instruction, 23, GREEN, anchor='w', width=round(620*scale))
            text(640, 680, f'{test.index} of 5 checked · No calls or volume changes during this test', 18, MUTED)
        c.place(x=0, y=0, relwidth=1, relheight=1)
        c.tk.call('raise', c._w)

