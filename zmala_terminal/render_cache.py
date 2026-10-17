"""Bound animation assets without discarding frequently reused images."""
from collections import OrderedDict


class RenderCache(OrderedDict):
    def __init__(self, limit):
        super().__init__()
        self.limit = limit

    def __getitem__(self, key):
        value = super().__getitem__(key)
        self.move_to_end(key)
        return value

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self.move_to_end(key)
        while len(self) > self.limit:
            self.popitem(last=False)


def portrait_size(size):
    # Round down so the image fits its layout budget even at screen edges.
    # Adjacent frames share four-pixel buckets, reducing portrait resampling.
    return max(1, (int(size) // 4) * 4)
