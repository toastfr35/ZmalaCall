"""Linux portrait conversion; invoked as a bounded server subprocess."""
import argparse
from PIL import Image, ImageOps


# @llr LLR-SRV-DIR-033, LLR-SRV-DIR-035
def convert(source, destination):
    Image.MAX_IMAGE_PIXELS = 16000000
    with Image.open(source) as image:
        if image.width * image.height > 16000000 or max(image.size) > 8192:
            raise ValueError('Photo dimensions exceed the supported limit')
        image = ImageOps.exif_transpose(image)
        image.thumbnail((480, 480), Image.Resampling.LANCZOS)
        image.convert('RGBA').save(destination, format='PNG')


# @llr LLR-SRV-DIR-035
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-Source', required=True)
    parser.add_argument('-Destination', required=True)
    args = parser.parse_args()
    convert(args.Source, args.Destination)
