"""Pixel-budget, recency and native-resource ownership regressions."""
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock
import weakref

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from render_cache import RenderCache, photo_bytes


class RenderCacheTests(unittest.TestCase):
    def test_byte_pressure_evicts_oldest_without_clearing_recent_entries(self):
        cache = RenderCache(10, max_bytes=10, size_of=len)
        cache.update(old=b'1234', active=b'1234')
        self.assertEqual(cache['active'], b'1234')
        cache['new'] = b'12345'
        self.assertEqual(set(cache), {'active', 'new'})
        self.assertEqual(cache.bytes_used, 9)

    def test_reads_and_replacements_refresh_recency_and_accounting(self):
        cache = RenderCache(3, max_bytes=9, size_of=len)
        cache.update(a=b'123', b=b'123', c=b'123')
        cache['a']
        cache['b'] = b'1'
        cache['d'] = b'1234'
        self.assertEqual(list(cache), ['a', 'b', 'd'])
        self.assertEqual(cache.bytes_used, 8)
        del cache['a']
        self.assertEqual(cache.bytes_used, 5)
        cache.clear()
        self.assertEqual(cache.bytes_used, 0)

    def test_oversized_item_does_not_flush_useful_cache_or_take_ownership(self):
        release = Mock()
        cache = RenderCache(4, max_bytes=5, size_of=len, release=release)
        cache['keep'] = b'1234'
        cache['large'] = b'123456'
        self.assertEqual(list(cache), ['keep'])
        self.assertEqual(cache.bytes_used, 4)
        release.assert_not_called()

    def test_native_resources_are_released_once_on_eviction_replacement_and_clear(self):
        release = Mock()
        cache = RenderCache(2, release=release)
        a, b, c, d = (object() for _ in range(4))
        cache.update(a=a, b=b)
        cache['c'] = c
        cache['b'] = d
        cache['b'] = d  # Same resource is still owned by this cache.
        cache.clear()
        cache.clear()
        self.assertEqual([call.args[0] for call in release.call_args_list], [a, b, c, d])

    def test_active_image_reference_survives_eviction(self):
        class Image:
            pass
        cache = RenderCache(1)
        visible = Image()
        reference = weakref.ref(visible)
        cache['visible'] = visible
        cache['next'] = Image()
        self.assertIs(reference(), visible)
        del visible
        self.assertIsNone(reference())

    def test_zero_capacity_and_invalid_weights(self):
        cache = RenderCache(0)
        cache['unused'] = object()
        self.assertFalse(cache)
        for arguments in ({'limit': -1}, {'limit': 1, 'max_bytes': -1}):
            with self.assertRaises(ValueError):
                RenderCache(**arguments)
        cache = RenderCache(2, size_of=lambda value: value)
        cache['valid'] = 2
        with self.assertRaises(ValueError):
            cache['valid'] = -1
        self.assertEqual(cache['valid'], 2)

    def test_tk_pixel_estimate_uses_alpha_storage(self):
        photo = Mock()
        photo.width.return_value, photo.height.return_value = 640, 480
        self.assertEqual(photo_bytes(photo), 1228800)


if __name__ == '__main__':
    unittest.main()
