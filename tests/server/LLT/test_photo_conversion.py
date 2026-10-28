# @test S-LLT-011
# @requirements LLR-SRV-DIR-033, LLR-SRV-DIR-035
# @environment portable
# @plan Convert synthetic portraits using the real function and command entrypoint. Inspect bounded PNG dimensions, preserved aspect ratio, EXIF orientation and RGBA output. Assert excessive decoded dimensions are rejected before output. Convert a looping GIF and assert composited 480px frames, timings and removal of repeat metadata; reject invalid duration, counts and canvas dimensions.
# @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

"""Exercise the Linux converter with fixture images; no live account assets."""
import importlib.util
from pathlib import Path
import runpy
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]


@unittest.skipUnless(importlib.util.find_spec('PIL'), 'Pillow is required for the Linux converter')
class PhotoConversionTests(unittest.TestCase):
    def test_command_entrypoint_applies_orientation_and_produces_rgba_png(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / 'input.jpg', Path(directory) / 'output.png'
            exif = Image.Exif()
            exif[274] = 6  # Clockwise quarter-turn: a landscape image becomes portrait.
            Image.new('RGB', (120, 60), 'red').save(source, exif=exif)
            command = ROOT / 'build_tools/convert-photo.py'
            with patch.object(sys, 'argv', [str(command), '-Source', str(source), '-Destination', str(output)]):
                runpy.run_path(str(command), run_name='__main__')
            with Image.open(output) as result:
                result.load()
                self.assertEqual(result.size, (60, 120))
                self.assertEqual(result.format, 'PNG')
                self.assertEqual(result.mode, 'RGBA')

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

    def test_gif_normalizes_frames_and_ignores_source_loop(self):
        from PIL import Image
        spec = importlib.util.spec_from_file_location('converter', ROOT / 'build_tools/convert-photo.py')
        converter = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(converter)
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory)/'input.gif', Path(directory)/'output.gif'
            frames = [Image.new('RGB', (720, 720), color) for color in ('red', 'blue', 'green')]
            frames[0].save(source, save_all=True, append_images=frames[1:], duration=[100, 200, 300], loop=0)
            converter.convert(source, output)
            with Image.open(output) as result:
                self.assertEqual(result.size, (480, 480))
                self.assertEqual(result.n_frames, 3)
                self.assertNotIn('loop', result.info)
                for index, color in enumerate(((255, 0, 0), (0, 0, 255), (0, 128, 0))):
                    result.seek(index)
                    self.assertEqual(result.convert('RGB').getpixel((240, 240)), color)
                    self.assertEqual(result.info['duration'], (index+1)*100)
            for size, count, delay in [((479,479),2,100),((480,481),2,100),((480,480),1,100),((480,480),3,2000)]:
                images=[Image.new('RGB', size, (i*20,0,0)) for i in range(count)]
                images[0].save(source,save_all=True,append_images=images[1:],duration=delay)
                with self.assertRaises(ValueError): converter.convert(source, output)
