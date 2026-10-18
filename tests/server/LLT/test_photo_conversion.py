# @test S-LLT-011
# @requirements SLLR087, SLLR089
# @environment portable
# @plan Convert synthetic portraits using the image conversion function; inspect bounded valid PNG output and assert excessive decoded dimensions are rejected.
# @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

"""Exercise the Linux converter with fixture images; no live account assets."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]


@unittest.skipUnless(importlib.util.find_spec('PIL'), 'Pillow is required for the Linux converter')
class PhotoConversionTests(unittest.TestCase):
    def test_converts_portrait_to_bounded_valid_png_and_rejects_excessive_dimensions(self):
        from PIL import Image
        spec = importlib.util.spec_from_file_location('photo_conversion', ROOT / 'build_tools/convert-photo.py')
        converter = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(converter)
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / 'input.jpg', Path(directory) / 'output.png'
            Image.new('RGB', (800, 400), 'red').save(source)
            converter.convert(source, output)
            with Image.open(output) as result:
                result.load()
                self.assertEqual(result.size, (480, 240))
                self.assertEqual(result.format, 'PNG')
            # A wide one-row image reaches the dimension limit without a large allocation.
            Image.new('RGB', (8193, 1), 'red').save(source)
            with self.assertRaisesRegex(ValueError, 'dimensions'):
                converter.convert(source, output)
