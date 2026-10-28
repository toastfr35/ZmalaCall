"""One bounded portrait worker; configuration and presence never wait for images."""
from collections import deque
import os
from pathlib import Path
import queue
import threading
import time
import uuid
from zmala_terminal.common.image_bounds import MAX_BYTES, MAX_GIF_BYTES


# Preserve the photo_cache import used by existing callers.
from zmala_terminal.common.portrait_validation import valid_photo as valid_photo


class PhotoCache:
    def __init__(self, directory, request):
        self.directory, self.request = Path(directory), request
        self.condition = threading.Condition()
        self.pending = deque()
        self.queued, self.valid, self.wanted = set(), set(), set()
        self.retry = {}
        self.completed = queue.Queue()
        self.cancelled = False
        self.worker = None

    # @llr LLR-TERM-UI-020
    def schedule(self, contacts):
        paths = dict.fromkeys(c['photo'] for c in contacts if c.get('photo'))
        with self.condition:
            if self.cancelled:
                return
            self.wanted = set(paths)
            # Keep one in-flight request, but discard obsolete waiting work immediately.
            # New contacts must not wait behind up to forty retired download timeouts.
            discarded = set(self.pending) - self.wanted
            self.pending = deque(path for path in self.pending if path in self.wanted)
            self.queued.difference_update(discarded)
            self.valid.intersection_update(paths)
            self.retry = {path: deadline for path, deadline in self.retry.items() if path in paths}
            now = time.monotonic()
            for path in paths:
                if path not in self.valid and path not in self.queued and now >= self.retry.get(path, 0):
                    if len(self.pending) >= 40:
                        break
                    self.pending.append(path)
                    self.queued.add(path)
            if self.pending and self.worker is None:
                self.worker = threading.Thread(target=self.run, daemon=True)
                self.worker.start()
            self.condition.notify()

    def close(self):
        with self.condition:
            self.cancelled = True
            self.pending.clear()
            self.wanted.clear()
            self.condition.notify()

    def changed(self):
        changed = False
        while True:
            try:
                self.completed.get_nowait()
                changed = True
            except queue.Empty:
                return changed and not self.cancelled

    # @llr LLR-TERM-UI-021
    def run(self):
        while True:
            with self.condition:
                while not self.pending and not self.cancelled:
                    self.condition.wait()
                if self.cancelled:
                    return
                path = self.pending.popleft()
            filename = self.directory / path.lstrip('/')
            temporary = filename.with_suffix('.' + uuid.uuid4().hex + '.tmp')
            try:
                cached = b''
                if filename.exists():
                    with filename.open('rb') as source:
                        cached = source.read((MAX_GIF_BYTES if path.endswith('.gif') else MAX_BYTES) + 1)
                if not valid_photo(cached, path):
                    filename.unlink(missing_ok=True)
                    data = self.request(path)
                    if not valid_photo(data, path):
                        raise ValueError('Invalid portrait')
                    filename.parent.mkdir(parents=True, exist_ok=True)
                    temporary.write_bytes(data)
                    with self.condition:
                        if self.cancelled or path not in self.wanted:
                            continue
                        os.replace(temporary, filename)
                with self.condition:
                    if not self.cancelled and path in self.wanted:
                        self.valid.add(path)
                        self.completed.put(path)
            except (OSError, ValueError):
                with self.condition:
                    if not self.cancelled and path in self.wanted:
                        self.retry[path] = time.monotonic() + 60
            finally:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
                with self.condition:
                    self.queued.discard(path)
