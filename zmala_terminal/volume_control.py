"""Pointer-held vertical volume gesture and a transient, non-interactive overlay."""
import time
import tkinter as tk
from platforms import c20_volume
from theme import PANEL, FG, MUTED, GREEN, RED


class VolumeGesture:
    UNITS_PER_STEP = 64
    PERCENT_PER_STEP = 2

    def __init__(self, percent):
        self.percent = percent
        self.held = False
        self.remainder = 0

    def hold(self, held):
        self.held = held
        self.remainder = 0

    def move(self, dy):
        if not self.held:
            return
        self.remainder -= dy  # HID Y is negative when the remote moves up.
        steps = int(self.remainder / self.UNITS_PER_STEP)
        self.remainder -= steps * self.UNITS_PER_STEP
        self.percent = max(0, min(100, self.percent + steps * self.PERCENT_PER_STEP))
        if self.percent in (0, 100):
            self.remainder = 0  # Reversing direction at a limit responds immediately.


class VolumeControl:
    def __init__(self, root, enabled, activity):
        self.root, self.enabled, self.activity = root, enabled, activity
        self.gesture = VolumeGesture(50)
        self.canvas = None
        self.timer = None
        self.hide_at = 0
        self.sent = None
        self.last_write = 0
        self.closed = False

    def pointer(self, held):
        if self.closed or held and not self.enabled():
            return
        if held:
            desired, _, _ = c20_volume.status()
            if desired is None:
                return
            self.gesture.percent = desired
            self.sent = desired
            self.activity()
        elif not self.gesture.held:
            return
        self.gesture.hold(held)
        self.hide_at = time.monotonic() + 2
        if self.timer is None:
            self.refresh()

    def motion(self, dy):
        if not self.closed:
            self.gesture.move(dy)

    def refresh(self):
        self.timer = None
        if self.closed:
            return
        now = time.monotonic()
        if self.gesture.held:
            self.activity()
        if self.sent != self.gesture.percent and now - self.last_write >= .1:
            c20_volume.request(self.gesture.percent)
            self.sent, self.last_write = self.gesture.percent, now
        if not self.gesture.held and now >= self.hide_at:
            if self.canvas:
                self.canvas.place_forget()
            return
        self.draw()
        self.timer = self.root.after(50, self.refresh)

    def draw(self):
        if self.canvas is None:
            self.canvas = tk.Canvas(self.root, width=84, height=300, bg=PANEL,
                                    highlightthickness=1, highlightbackground=MUTED,
                                    takefocus=False)
        c = self.canvas
        percent = self.gesture.percent
        _, _, failed = c20_volume.status()
        color = RED if failed else GREEN
        c.delete('all')
        # Speaker geometry avoids platform-dependent emoji/font glyphs.
        c.create_polygon(19, 23, 27, 23, 37, 15, 37, 45, 27, 37, 19, 37, fill=FG)
        if percent:
            c.create_arc(31, 17, 56, 43, start=-60, extent=120, style='arc', outline=FG, width=2)
        else:
            c.create_line(45, 23, 57, 37, fill=MUTED, width=2)
            c.create_line(45, 37, 57, 23, fill=MUTED, width=2)
        c.create_rectangle(30, 62, 54, 252, outline=MUTED, width=2)
        if percent:
            c.create_rectangle(33, 249-184*percent/100, 51, 249, fill=color, outline='')
        c.create_text(42, 277, text=f'{percent}%' if not failed else '!', fill=color,
                      font=('Segoe UI', 16, 'bold'))
        c.place(relx=1, rely=.5, x=-24, anchor='e')
        tk.Misc.lift(c)  # Also above confirmation and native-video sibling surfaces.

    def close(self):
        self.closed = True
        if self.timer is not None:
            self.root.after_cancel(self.timer)
        # Flush a final adjustment without blocking shutdown on the mixer worker.
        if self.sent is not None and self.sent != self.gesture.percent:
            c20_volume.request(self.gesture.percent)
        if self.canvas:
            self.canvas.destroy()
