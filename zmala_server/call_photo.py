"""Bounded still-image normalization for temporary in-call sharing."""
import sys
import warnings
from PIL import Image, ImageOps


# @llr LLR-SRV-MEDIA-016
def normalize(source, destination):
    # Read dimensions before decoding; never preserve EXIF or animation metadata.
    with warnings.catch_warnings():
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        with Image.open(source) as original:
            if original.format not in ('JPEG', 'PNG') or original.width * original.height > 16000000:
                raise ValueError('Unsupported image dimensions or format')
            image = ImageOps.exif_transpose(original).convert('RGB')
            image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
            clean = Image.new('RGB', image.size)
            clean.paste(image)
            clean.save(destination, 'JPEG', quality=85)


if __name__ == '__main__':
    normalize(*sys.argv[1:])
