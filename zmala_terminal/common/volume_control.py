"""Middle-button call-volume overlay, preserving the current screen and selection."""
import time
import tkinter as tk
from zmala_terminal.linux import c20_volume
from zmala_terminal.common.theme import BG, FG, MUTED, GREEN, RED


class VolumeLevel:
    def __init__(self, percent):
        self.percent = percent

    # @llr LLR-TERM-REMOTE-016
    def adjust(self, button):
        if button == 'right':
            self.percent = min(100, (self.percent//5+1)*5)
        elif button == 'left':
            self.percent = max(0, ((self.percent+4)//5-1)*5)


class VolumeControl:
    def __init__(self, root, enabled, activity, context=lambda: None, in_call=lambda: False):
        self.root, self.enabled, self.activity = root, enabled, activity
        self.in_call = in_call
        self.context = context
        self.opened_context = None
        self.level = VolumeLevel(50)
        self.active = False
        self.pressed = False
        self.canvas = None
        self.timer = None
        self.sent = None
        self.default_revision = c20_volume.default_revision()
        self.last_write = 0
        self.closed = False

    # @llr LLR-TERM-REMOTE-016
    def pointer(self, held):
        if not held:
            self.pressed = False
            return
        if self.closed or self.pressed:
            return
        self.pressed = True
        if self.active:
            self.dismiss()
            return
        if not self.enabled():
            return
        desired, _, _ = c20_volume.status()
        if desired is None:
            return
        self.level.percent = desired
        self.sent = desired
        self.default_revision = c20_volume.default_revision()
        self.active = True
        self.opened_context = self.context()
        self.activity()
        self.refresh()

    def button(self, button):
        if not self.active or self.closed:
            return
        self.activity()
        self.level.adjust(button)

    # @llr LLR-TERM-AUDIO-007
    def flush(self, force=False):
        # @llr LLR-TERM-AUDIO-008
        # A saved default supersedes unsent clicks, including when the new default
        # equals the last written value. Comparing volume values alone misses it.
        revision = c20_volume.default_revision()
        if revision != self.default_revision:
            self.default_revision = revision
            desired, _, _ = c20_volume.status()
            if desired is not None:
                self.level.percent = self.sent = desired
        now = time.monotonic()
        if self.sent != self.level.percent and (force or now-self.last_write >= .1):
            c20_volume.request(self.level.percent)
            self.sent, self.last_write = self.level.percent, now

    def dismiss(self):
        if self.active:
            self.flush(force=True)
        self.active = False
        if self.timer is not None:
            self.root.after_cancel(self.timer)
            self.timer = None
        if self.canvas:
            self.canvas.place_forget()

    def refresh(self):
        self.timer = None
        if self.closed or not self.active:
            return
        if not self.enabled() or self.context() != self.opened_context:
            self.dismiss()
            return
        self.flush()
        self.draw()
        self.timer = self.root.after(50, self.refresh)

    # @llr LLR-TERM-AUDIO-006
    def draw(self):
        if self.canvas is None:
            self.canvas = tk.Canvas(self.root, bg=BG, highlightthickness=0, takefocus=False)
        c = self.canvas
        w, h = max(1, self.root.winfo_width()), max(1, self.root.winfo_height())
        w, h = min(900, w*.8), min(160, h*.3)
        c.configure(bg='#000000')
        percent = self.level.percent
        _, _, failed = c20_volume.status()
        color = RED if failed else GREEN
        c.delete('all')
        width = max(40, w-180)
        left, right, y = (w-width)/2, (w+width)/2, h/2-22
        # A single centered horizontal control, with language-independent icons.
        c.create_polygon(left-70, y-12, left-62, y-12, left-48, y-24,
                         left-48, y+24, left-62, y+12, left-70, y+12, fill=FG)
        c.create_line(left-24, y-12, left-36, y, left-24, y+12, fill=FG, width=4)
        c.create_line(right+24, y-12, right+36, y, right+24, y+12, fill=FG, width=4)
        c.create_rectangle(left, y-22, right, y+22, outline=MUTED, width=2,
                           tags='volume-track')
        if percent:
            c.create_rectangle(left+3, y-19, left+3+(width-6)*percent/100, y+19,
                               fill=color, outline='', tags='volume-fill')
        c.create_text(w/2, y+52, text=f'{percent}%' if not failed else '!',
                      fill=color, font=('Segoe UI', 22, 'bold'), tags='volume-level')
        c.place(x=0, y=0, relx=.5, rely=.68, anchor='center',
                width=w, height=h, relwidth=0, relheight=0)

        tk.Misc.lift(c)

    def close(self):
        self.dismiss()
        self.closed = True
        if self.canvas:
            self.canvas.destroy()
