# @test S-LLT-067
# @requirements LLR-SRV-MEDIA-016
# @environment portable
# @plan Normalize synthetic JPEG/PNG images with EXIF rotation and metadata. Assert bounded output, aspect ratio, metadata removal and rejection of GIF/oversized pixels before decode.
# @pass Normalized output is a metadata-free JPEG no larger than 1600 pixels per side; rejected input produces no usable output.
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from zmala_server.call_photo import normalize


class CallPhotoTests(unittest.TestCase):
    def test_orientation_bounds_and_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            source, output = Path(folder)/'in.jpg', Path(folder)/'out.jpg'
            exif = Image.Exif(); exif[274] = 6; exif[270] = 'private description'
            Image.new('RGB', (2400, 1200), 'blue').save(source, exif=exif)
            normalize(source, output)
            with Image.open(output) as image:
                self.assertEqual(image.size, (800, 1600))
                self.assertEqual(image.format, 'JPEG')
                self.assertFalse(image.getexif())
    def test_gif_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            source, output = Path(folder)/'in.gif', Path(folder)/'out.jpg'
            Image.new('RGB', (20, 20)).save(source)
            with self.assertRaises(ValueError): normalize(source, output)
            self.assertFalse(output.exists())

    def test_png_and_pixel_limit(self):
        with tempfile.TemporaryDirectory() as folder:
            source, output = Path(folder)/'in.png', Path(folder)/'out.jpg'
            Image.new('RGBA', (300, 600), 'blue').save(source)
            normalize(source, output)
            with Image.open(output) as image:
                self.assertEqual(image.size, (300, 600))
                self.assertEqual(image.format, 'JPEG')
            output.unlink()
            Image.new('RGB', (4001, 4000)).save(source)
            with self.assertRaises(ValueError):
                normalize(source, output)
            self.assertFalse(output.exists())
