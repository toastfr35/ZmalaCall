"""Reject excessive declared pixels before decoding network or old cached portraits."""
import hashlib
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import Mock
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from image_bounds import MAX_BYTES, MAX_PIXELS, PNG, check_file, image_size
from photo_cache import valid_photo


def png(width, height):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    return (PNG + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)) +
            chunk(b'IDAT', zlib.compress(b'\0\xff\0\0')) + chunk(b'IEND', b''))


def jpeg(width, height, marker=0xc0):
    # Header-only fixture: valid dimension metadata, deliberately not decodable pixels.
    frame = bytes([8]) + struct.pack('>HHB', height, width, 3) + b'\x01\x11\0\x02\x11\0\x03\x11\0'
    return b'\xff\xd8\xff\xe1\0\x06test\xff' + bytes([marker]) + struct.pack('>H', len(frame) + 2) + frame + b'\xff\xd9'


class ImageBoundsTests(unittest.TestCase):
    def test_png_and_common_jpeg_headers_have_bounded_dimensions(self):
        self.assertEqual(image_size(png(480, 320)), (480, 320))
        for marker in (0xc0, 0xc1, 0xc2):
            self.assertEqual(image_size(jpeg(640, 480, marker)), (640, 480))
        self.assertEqual(image_size(png(2048, 2048)), (2048, 2048))
        self.assertEqual(2048 * 2048, MAX_PIXELS)

    def test_small_compressed_files_cannot_request_huge_pixel_allocations(self):
        for builder, extension in ((png, 'png'), (jpeg, 'jpg')):
            for size in ((0, 1), (4097, 1), (4096, 4096), (2049, 2048)):
                data = builder(*size)
                self.assertLess(len(data), 100)
                with self.assertRaises(ValueError):
                    image_size(data)
                name = '/photos/' + hashlib.sha256(data).hexdigest() + '.' + extension
                self.assertFalse(valid_photo(data, name))

    def test_truncated_or_malformed_headers_do_not_escape_as_struct_errors(self):
        for original in (png(1, 1), jpeg(480, 480)):
            for end in range(33 if original.startswith(PNG) else len(original)):
                with self.assertRaises(ValueError):
                    image_size(original[:end])
        for data in (b'\xff\xd8\xff\xff\xff\xd9', b'\xff\xd8\xff\xe1\0\x01\xff\xd9',
                     b'\xff\xd8\xff\xda\0\x02\xff\xd9', PNG + b'\0' * 40,
                     png(1, 1) + b'\0' * MAX_BYTES):
            with self.assertRaises(ValueError):
                image_size(data)

    def test_file_preflight_rejects_legacy_cache_before_native_renderer(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'legacy.jpg'
            file.write_bytes(jpeg(16000, 16000))
            with self.assertRaises(OSError):
                check_file(file)
            file.write_bytes(png(80, 100))
            self.assertEqual(check_file(file), (80, 100))

    def test_optional_invalid_portrait_falls_back_without_breaking_carousel(self):
        from ui.carousel import CarouselView
        view = CarouselView()
        view.carousel_motion = None
        view.text_renderer = Mock()
        view.text_renderer.portrait.side_effect = ValueError('Invalid image dimensions')
        self.assertIsNone(view.contact_image({'photo': '/photos/abcd.png'}, 100))


if __name__ == '__main__':
    unittest.main()
