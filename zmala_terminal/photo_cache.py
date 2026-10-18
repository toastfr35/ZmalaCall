"""One bounded portrait worker; configuration and presence never wait for images."""
from collections import deque
import hashlib
import os
from pathlib import Path
import queue
import struct
import threading
import time
import uuid
import zlib
from image_bounds import MAX_BYTES, image_size


def valid_photo(data, name):
    try:
        image_size(data)
    except ValueError:
        return False
    digest = Path(name).stem
    if len(digest) == 64 and hashlib.sha256(data).hexdigest() != digest:
        return False
    if name.endswith('.jpg'):
        return data.startswith(b'\xff\xd8\xff') and data.endswith(b'\xff\xd9')
    if not data.startswith(b'\x89PNG\r\n\x1a\n'):
        return False
    offset, header, pixels = 8, False, False
    while offset + 12 <= len(data):
        length = struct.unpack_from('>I', data, offset)[0]
        end = offset + 12 + length
        if end > len(data):
            return False
        kind = data[offset+4:offset+8]
        payload = data[offset+8:end-4]
        if zlib.crc32(kind + payload) != struct.unpack_from('>I', data, end-4)[0]:
            return False
        if kind == b'IHDR':
            if offset != 8 or length != 13:
                return False
            width, height = struct.unpack_from('>II', payload)
            header = 0 < width <= 4096 and 0 < height <= 4096
        if kind == b'IDAT':
            pixels |= bool(length)
        if kind == b'IEND':
            return header and pixels and length == 0 and end == len(data)
        offset = end
    return False


class PhotoCache:
    def __init__(self, directory, request):
        self.directory, self.request = Path(directory), request
        self.condition = threading.Condition()
        self.pending = deque()
        self.queued, self.valid = set(), set()
        self.retry = {}
        self.completed = queue.Queue()
        self.cancelled = False
        self.worker = None

    def schedule(self, contacts):
        paths = {c['photo'] for c in contacts if c.get('photo')}
        with self.condition:
            if self.cancelled:
                return
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
            self.condition.notify()

    def changed(self):
        changed = False
        while True:
            try:
                self.completed.get_nowait()
                changed = True
            except queue.Empty:
                return changed and not self.cancelled

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
                        cached = source.read(MAX_BYTES + 1)
                if not valid_photo(cached, path):
                    filename.unlink(missing_ok=True)
                    data = self.request(path)
                    if not valid_photo(data, path):
                        raise ValueError('Invalid portrait')
                    filename.parent.mkdir(parents=True, exist_ok=True)
                    temporary.write_bytes(data)
                    with self.condition:
                        if self.cancelled:
                            return
                        os.replace(temporary, filename)
                with self.condition:
                    self.valid.add(path)
                    self.completed.put(path)
            except (OSError, ValueError):
                with self.condition:
                    self.retry[path] = time.monotonic() + 60
            finally:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
                with self.condition:
                    self.queued.discard(path)
