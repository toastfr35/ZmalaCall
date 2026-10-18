"""Bound retained image pixels without discarding frequently reused assets.

Budgets estimate pixel payload, not allocator overhead or total process RSS.
Oversized values remain usable by the caller but are not retained by the cache.
"""
from collections import OrderedDict
from collections.abc import MutableMapping


MIB = 1024 * 1024
TEXT_BYTES = 8 * MIB
PORTRAIT_BYTES = 32 * MIB
SOURCE_BYTES = 24 * MIB
BACKGROUND_BYTES = 8 * MIB
ICON_BYTES = 2 * MIB


def photo_bytes(photo):
    """Tk stores four bytes per pixel, including images supplied as RGB."""
    return photo.width() * photo.height() * 4


class RenderCache(MutableMapping):
    """LRU mapping for stable-size values; release owns cached native resources.

    Removal/replacement invokes release, but an oversized rejected value remains
    the caller's responsibility. Tk/Pillow values need only ordinary references.
    """
    def __init__(self, limit, *, max_bytes=None, size_of=None, release=None):
        if limit < 0 or (max_bytes is not None and max_bytes < 0):
            raise ValueError('Cache limits must not be negative')
        self.limit = limit
        self.max_bytes = max_bytes
        self.size_of = size_of or (lambda value: 0)
        self.release = release
        self.bytes_used = 0
        self._entries = OrderedDict()

    def __len__(self):
        return len(self._entries)

    def __iter__(self):
        # Mapping.values()/items() access values and therefore update recency.
        return iter(tuple(self._entries))

    def __contains__(self, key):
        return key in self._entries

    def __getitem__(self, key):
        value, _ = self._entries[key]
        self._entries.move_to_end(key)
        return value

    # @llr TLLR122
    def __setitem__(self, key, value):
        size = int(self.size_of(value))
        if size < 0:
            raise ValueError('Cache size must not be negative')
        if key in self._entries:
            previous, previous_size = self._entries.pop(key)
            self.bytes_used -= previous_size
            if self.release and previous is not value:
                self.release(previous)
        if not self.limit or (self.max_bytes is not None and size > self.max_bytes):
            return
        self._entries[key] = (value, size)
        self.bytes_used += size
        while (len(self) > self.limit or
               (self.max_bytes is not None and self.bytes_used > self.max_bytes)):
            del self[next(iter(self._entries))]

    def __delitem__(self, key):
        value, size = self._entries.pop(key)
        self.bytes_used -= size
        if self.release:
            self.release(value)

    def clear(self):
        for key in tuple(self._entries):
            del self[key]


def portrait_size(size):
    # Round down so the image fits its layout budget even at screen edges.
    # Adjacent frames share four-pixel buckets, reducing portrait resampling.
    return max(1, (int(size) // 4) * 4)
