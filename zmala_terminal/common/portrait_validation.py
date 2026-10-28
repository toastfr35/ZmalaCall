"""Validate bounded portrait bytes independently of disk and download scheduling."""
import hashlib
import io
from pathlib import Path
import struct
import zlib
from zmala_terminal.common.image_bounds import image_size


# @llr LLR-TERM-UI-020
def valid_photo(data, name):
    try:
        image_size(data)
    except ValueError:
        return False
    digest = Path(name).stem
    if len(digest) == 64 and hashlib.sha256(data).hexdigest() != digest:
        return False
    if name.endswith('.gif'):
        if not data.endswith(b';'):
            return False
        try:
            from PIL import Image
            with Image.open(io.BytesIO(data)) as gif:
                if gif.format != 'GIF' or gif.size != (480, 480):
                    return False
                count, duration = 0, 0
                while True:
                    try:
                        gif.seek(count)
                    except EOFError:
                        return 2 <= count <= 72
                    if gif.size != (480, 480):
                        return False
                    delay = gif.info.get('duration', 100) or 100
                    duration += delay
                    if count >= 72 or not 20 <= delay <= 2000 or duration > 5000:
                        return False
                    gif.load()
                    count += 1
        except (OSError, ValueError):
            return False
    if name.endswith('.jpg'):
        return data.startswith(b'\xff\xd8\xff') and data.endswith(b'\xff\xd9')
    if not data.startswith(b'\x89PNG\r\n\x1a\n'):
        return False
    offset, header, pixels = 8, False, False
    while offset + 12 <= len(data):
        length = struct.unpack_from('>I', data, offset)[0]
        end = offset + 12 + length
        if end > len(data):
            return False
        kind = data[offset+4:offset+8]
        payload = data[offset+8:end-4]
        if zlib.crc32(kind + payload) != struct.unpack_from('>I', data, end-4)[0]:
            return False
        if kind == b'IHDR':
            if offset != 8 or length != 13:
                return False
            width, height = struct.unpack_from('>II', payload)
            header = 0 < width <= 4096 and 0 < height <= 4096
        if kind == b'IDAT':
            pixels |= bool(length)
        if kind == b'IEND':
            return header and pixels and length == 0 and end == len(data)
        offset = end
    return False


