"""Inspect PNG/JPEG portrait headers before a native decoder allocates pixels."""
import struct
import zlib

MAX_BYTES = 2 * 1024 * 1024
MAX_GIF_BYTES = 16 * 1024 * 1024
MAX_SIDE = 4096
MAX_PIXELS = 4 * 1024 * 1024
PNG = b'\x89PNG\r\n\x1a\n'


# @llr LLR-TERM-UI-020
def checked_size(width, height):
    if not (0 < width <= MAX_SIDE and 0 < height <= MAX_SIDE and width * height <= MAX_PIXELS):
        raise ValueError('Portrait dimensions exceed the decoding limit')
    return width, height


# @llr LLR-TERM-UI-020
def image_size(data):
    """Header validation is a size guard, not proof that compressed pixels decode."""
    if data[:6] in (b'GIF87a', b'GIF89a'):
        if len(data) < 14 or len(data) > MAX_GIF_BYTES:
            raise ValueError('GIF file exceeds the decoding limit')
        width, height = struct.unpack_from('<HH', data, 6)
        if width != 480 or height != 480:
            raise ValueError('Published GIF must be 480 × 480 pixels')
        return width, height
    if not data or len(data) > MAX_BYTES:
        raise ValueError('Portrait file exceeds the decoding limit')
    if data.startswith(PNG):
        if (len(data) < 33 or data[8:16] != b'\0\0\0\rIHDR' or
                zlib.crc32(data[12:29]) != struct.unpack_from('>I', data, 29)[0]):
            raise ValueError('Invalid PNG header')
        return checked_size(*struct.unpack_from('>II', data, 16))
    if data.startswith(b'\xff\xd8') and data.endswith(b'\xff\xd9'):
        offset = 2
        while offset < len(data):
            if data[offset] != 0xff:
                break
            while offset < len(data) and data[offset] == 0xff:
                offset += 1
            if offset >= len(data):
                break
            marker = data[offset]
            offset += 1
            if marker in (0xda, 0xd9):  # No frame header before scan/end.
                break
            if marker == 0x01 or 0xd0 <= marker <= 0xd7:
                continue
            if offset + 2 > len(data):
                break
            length = struct.unpack_from('>H', data, offset)[0]
            if length < 2 or offset + length > len(data):
                break
            if marker in (0xc0, 0xc1, 0xc2):  # Baseline, extended sequential, progressive.
                if length < 8:
                    break
                components = data[offset + 7]
                if data[offset + 2] != 8 or not 1 <= components <= 4 or length != 8 + 3 * components:
                    break
                height, width = struct.unpack_from('>HH', data, offset + 3)
                return checked_size(width, height)
            offset += length
    raise ValueError('Invalid or unsupported portrait header')


def check_file(path):
    """Bound reads as well as pixels, including files from an older local cache."""
    with open(path, 'rb') as source:
        try:
            data = source.read(MAX_GIF_BYTES + 1)
            size = image_size(data)
            if data[:3] == b'GIF':
                # Read only the first frame header here; full animation validation
                # belongs to the background photo worker, never the UI thread.
                import io
                from PIL import Image
                with Image.open(io.BytesIO(data)) as gif:
                    if gif.size != (480, 480):
                        raise ValueError('Invalid animated portrait')
            return size
        except ValueError as error:
            # Existing image callers handle optional missing/invalid files as OSError.
            raise OSError(str(error)) from error
