"""Receive a leased, authenticated call photo without touching media or Tk off-thread."""
import io
import json
import queue
import threading
import time
import urllib.parse
import tkinter as tk
from PIL import Image, ImageTk
from zmala_terminal.common.model import State


# @llr LLR-TERM-VIDEO-020
def decode_photo(data):
    if len(data) > 2 * 1024 * 1024:
        raise ValueError('Photo too large')
    with Image.open(io.BytesIO(data)) as image:
        if image.format != 'JPEG' or max(image.size) > 1600:
            raise ValueError('Invalid call photo')
        return image.convert('RGB')


# @llr LLR-TERM-VIDEO-020
class CallPhoto:
    def __init__(self, root):
        self.layer = tk.Label(root, bg='black', borderwidth=0)
        self.layer.bind('<Configure>', lambda event: self.draw())
        self.owner = None
        self.revision = None
        self.image = None
        self.picture = None
        self.results = queue.Queue()
        self.busy = False
        self.next_poll = 0
        self.deadline = 0
        self.drawn = None

    def clear(self):
        self.image = self.picture = self.revision = self.drawn = None
        self.layer.configure(image='')
        self.layer.place_forget()

    def draw(self):
        if self.image is None:
            return
        size = (max(1, self.layer.winfo_width()), max(1, self.layer.winfo_height()))
        # Tk initially reports 1x1 before placement; contain can round a side to zero.
        if min(size) < 2:
            return
        key = (self.revision, size)
        if self.drawn == key:
            return
        self.drawn = key
        scale = min(size[0] / self.image.width, size[1] / self.image.height)
        target = (max(1, round(self.image.width * scale)), max(1, round(self.image.height * scale)))
        self.picture = ImageTk.PhotoImage(self.image.resize(target, Image.Resampling.LANCZOS))
        self.layer.configure(image=self.picture)

    def tick(self, app):
        # Native SDK reads remain on its owner/Tk thread.
        call_id = app.engine.call_id() if app.engine and app.model.state == State.IN_CALL and app.model.config.get('call_photo_sharing') else None
        owner = (app.engine, call_id, app.configuration) if isinstance(call_id, str) and call_id and app.configuration else None
        if owner != self.owner:
            self.owner = owner
            self.clear()
            self.next_poll = 0
        now = time.monotonic()
        while not self.results.empty():
            ticket, revision, image, valid_until = self.results.get_nowait()
            self.busy = False
            if ticket != self.owner:
                continue
            if image is False:  # A temporary request failure cannot extend the lease.
                continue
            self.deadline = valid_until
            if revision != self.revision or image is None:
                self.clear()
                if image is not None and valid_until > now:
                    self.revision, self.image = revision, image
                    self.layer.place(x=0, y=0, relwidth=1, relheight=1)
                    self.layer.lift()
                    self.draw()
        if self.image is not None and now >= self.deadline:
            self.clear()
        if owner is None or self.busy or now < self.next_poll:
            return
        self.busy = True
        self.next_poll = now + 1
        revision = self.revision
        previous_image = self.image
        def fetch():
            image, value, deadline = False, None, 0
            try:
                route = '/api/call/photo?call_id=' + urllib.parse.quote(call_id, safe='')
                status = json.loads(owner[2].request(route))
                value = status['revision']
                deadline = now + min(12, max(0, status.get('remaining_ms', 0) / 1000))
                image = None
                if status.get('sharing'):
                    # Reuse pixels for unchanged revisions; don't reread image on Tk.
                    image = previous_image if value == revision else decode_photo(owner[2].request(
                        route + '&image=1&revision=' + str(value)))
            except Exception:
                image = False
            self.results.put((owner, value, image, deadline))
        threading.Thread(target=fetch, daemon=True, name='zmala-call-photo').start()
