"""Play uploaded GIF portraits once after the selected carousel card settles.

Static portrait rendering remains the fallback during navigation and calls. All Tk objects
are created on the UI thread, in small batches, and retained under a 64 MiB cap.
"""

from collections import OrderedDict
import io
import queue
import threading
import time
from pathlib import Path
import tkinter as tk
import logging
from PIL import Image

LIMIT = 64 * 1024 * 1024


# @llr LLR-TERM-UI-026
def load_frames(path, size):
    """Decode in a worker, composite GIF disposal, bound work before Tk allocation."""
    from zmala_terminal.common.photo_cache import valid_photo
    from zmala_terminal.common.image_bounds import MAX_GIF_BYTES

    with path.open("rb") as stream:
        data = stream.read(MAX_GIF_BYTES + 1)
    if not valid_photo(data, path.name):
        raise ValueError("Invalid animated portrait")
    if not 40 <= size <= 460:
        raise ValueError("Invalid portrait display size")
    pngs, durations = [], []
    with Image.open(io.BytesIO(data)) as source:
        for index in range(source.n_frames):
            source.seek(index)
            frame = source.convert("RGB").resize((size, size), Image.Resampling.LANCZOS)
            out = io.BytesIO()
            frame.save(out, format="PNG")
            pngs.append(out.getvalue())
            durations.append(source.info.get("duration", 100) or 100)
    return pngs, durations


# @llr LLR-TERM-UI-026
class PortraitAnimation:
    def __init__(self, app, directory):
        self.app = app
        self.directory = Path(directory)
        self.completed = 0
        self.error_count = 0
        self.cache = OrderedDict()
        self.results = queue.Queue()
        self.loading = None
        self.build = None
        self.key = None
        self.armed = True
        self.playing = False
        self.started = 0
        self.frame = -1
        self.visible_photo = None
        self.painted_item = None
        self.failures = set()
        self.app.root.after(20, self.tick)

    def request(self, key):
        if self.loading or self.build or key in self.failures:
            return
        photo, size = key
        folder = (self.directory / photo.lstrip("/")).resolve()
        if not folder.is_relative_to(self.directory.resolve()):
            raise ValueError("Invalid portrait path")
        if not folder.is_file():
            return  # The photo worker may still be downloading.
        self.loading = key

        def worker():
            try:
                self.results.put((key, load_frames(folder, size), None))
            except Exception as e:
                self.results.put((key, None, type(e).__name__))

        threading.Thread(target=worker, daemon=True).start()

    def prepare(self):
        try:
            key, result, error = self.results.get_nowait()
        except queue.Empty:
            return
        self.loading = None
        if key != self.key:
            return  # Navigation invalidates a late preparation result.
        if error:
            self.failures.add(key)
            logging.warning("Animated portrait unavailable: %s", error)
            return
        pngs, durations = result
        needed = len(pngs) * key[1] * key[1] * 4
        while self.cache and sum(v[2] for v in self.cache.values()) + needed > LIMIT:
            self.cache.popitem(last=False)
        self.build = (key, pngs, durations, [], needed)

    def build_images(self):
        if not self.build:
            return
        key, pngs, durations, photos, needed = self.build
        if key != self.key:
            self.build = None
            return
        for _ in range(min(4, len(pngs) - len(photos))):
            photos.append(
                tk.PhotoImage(
                    master=self.app.root, data=pngs[len(photos)], format="png"
                )
            )
        if len(photos) == len(pngs):
            self.cache[key] = (photos, durations, needed)
            self.build = None

    def paint(self, photo):
        items = self.app.avatar.find_withtag("portrait-preview-target")
        item = items[-1] if items else None
        if item and (photo is not self.visible_photo or item != self.painted_item):
            self.app.avatar.itemconfigure(item, image=photo)
            self.painted_item = item
        self.visible_photo = photo

    def close(self):
        self.playing = False
        self.key = None
        self.visible_photo = None
        self.build = None
        self.cache.clear()

    def tick(self):
        app = self.app
        if app.closed:
            return
        try:
            from zmala_terminal.common.model import State

            target = getattr(app, "portrait_animation_target", None)
            selected = app.model.selected
            eligible = (
                app.model.state == State.HOME
                and not app.setup_stage
                and not app.settings_open
                and not app.carousel_motion
                and selected
                and target
                and selected["id"] == target[0]
            )
            photo = selected.get("photo", "") if selected else ""
            key = (photo, target[1]) if eligible and photo.endswith(".gif") else None
            if key != self.key:
                self.key = key
                self.armed = True
                self.playing = False
                self.frame = -1
                self.visible_photo = None
                self.painted_item = None
            if app.model.state != State.HOME:
                self.cache.clear()
                self.build = None  # Calls retain no animation image cache.
            self.prepare()
            self.build_images()
            if key:
                if key not in self.cache:
                    self.request(key)
                else:
                    self.cache.move_to_end(key)
                    photos, durations, _ = self.cache[key]
                    now = time.monotonic()
                    if self.armed:
                        self.armed = False
                        self.playing = True
                        self.started = now
                    if self.playing:
                        elapsed = (now - self.started) * 1000
                        boundary = 0
                        index = 0
                        for index, duration in enumerate(durations):
                            boundary += duration
                            if elapsed < boundary:
                                break
                        else:
                            self.playing = False
                            index = len(photos) - 1
                            self.completed += 1
                        self.paint(photos[index])
                        if self.frame != index:
                            self.frame = index
                    elif self.visible_photo:
                        # A presence refresh may redraw the card; keep the final still frame.
                        self.paint(self.visible_photo)
        except Exception as e:
            self.error_count += 1
            logging.warning("Animated portrait playback stopped: %s", type(e).__name__)
            self.playing = False
        app.root.after(10 if self.playing or self.build else 30, self.tick)
