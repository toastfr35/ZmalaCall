"""Read-only GPT integrity/layout checks for the pinned A/B boot experiment.

Never opens a block device, mounts a filesystem or claims that a valid partition
table proves bootability. Production image verification will add content checks.
"""
import os
from pathlib import Path
import stat
import struct
import uuid
import zlib

LABELS = ('bootconfig', 'boot_a', 'boot_b', 'system_a', 'system_b', 'persistent')
MAX_TABLE = 4*1024*1024


def header(stream, lba, sector, sectors):
    stream.seek(lba*sector)
    raw = stream.read(sector)
    if len(raw) != sector or raw[:8] != b'EFI PART':
        raise ValueError('Missing GPT header')
    revision, size, checksum, reserved = struct.unpack_from('<4I', raw, 8)
    if revision != 0x10000 or not 92 <= size <= sector or reserved or raw[56:72] == bytes(16):
        raise ValueError('Invalid GPT header format')
    checked = bytearray(raw[:size])
    struct.pack_into('<I', checked, 16, 0)
    if zlib.crc32(checked) != checksum:
        raise ValueError('GPT header checksum mismatch')
    current, other, first, last = struct.unpack_from('<4Q', raw, 24)
    table_lba, count, width, table_crc = struct.unpack_from('<Q3I', raw, 72)
    if (current != lba or other != (sectors-1 if lba == 1 else 1)
            or not 2 < first <= last < sectors-1
            or not 128 <= width <= 4096 or width % 128 or not count
            or count*width > MAX_TABLE):
        raise ValueError('Invalid GPT bounds')
    table_sectors = (count*width+sector-1)//sector
    if lba == 1:
        valid = 2 <= table_lba and table_lba+table_sectors <= first
    else:
        valid = last < table_lba and table_lba+table_sectors <= sectors-1
    if not valid:
        raise ValueError('GPT table overlaps usable disk area')
    stream.seek(table_lba*sector)
    table = stream.read(count*width)
    if len(table) != count*width or zlib.crc32(table) != table_crc:
        raise ValueError('GPT partition-array checksum mismatch')
    return {'first': first, 'last': last, 'guid': raw[56:72], 'count': count,
            'width': width, 'table': table}


def audit(path, sector=512):
    if sector not in (512, 4096):
        raise ValueError('Supported sector sizes are 512 and 4096 bytes')
    path = Path(path)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError('Expected a regular image file, never a device or symlink')
    if info.st_size % sector or info.st_size < sector*68:
        raise ValueError('Invalid image byte length')
    with path.open('rb') as stream:
        opened = os.fstat(stream.fileno())
        if not stat.S_ISREG(opened.st_mode) or (info.st_dev, info.st_ino) != (opened.st_dev, opened.st_ino):
            raise ValueError('Image changed while opening')
        mbr = stream.read(512)
        if mbr[510:512] != b'\x55\xaa' or mbr[450] != 0xee:
            raise ValueError('Missing protective MBR')
        sectors = info.st_size//sector
        primary = header(stream, 1, sector, sectors)
        backup = header(stream, sectors-1, sector, sectors)
        if primary != backup:
            raise ValueError('Primary and backup GPT disagree')
        partitions, ids = [], set()
        for index in range(primary['count']):
            row = primary['table'][index*primary['width']:(index+1)*primary['width']]
            if row[:16] == bytes(16):
                continue
            identity = row[16:32]
            first, last = struct.unpack_from('<2Q', row, 32)
            if identity == bytes(16) or identity in ids:
                raise ValueError('Missing or duplicate partition identity')
            ids.add(identity)
            if not primary['first'] <= first <= last <= primary['last']:
                raise ValueError('Partition outside usable bounds')
            label = row[56:128].decode('utf-16-le').split('\0', 1)[0]
            partitions.append({'index': index+1, 'label': label,
                               'first_lba': first, 'last_lba': last,
                               'bytes': (last-first+1)*sector,
                               'type': str(uuid.UUID(bytes_le=row[:16]))})
        if tuple(p['label'] for p in partitions) != LABELS:
            raise ValueError('Not the pinned six-partition A/B probe layout')
        for previous, following in zip(partitions, partitions[1:]):
            if previous['last_lba'] >= following['first_lba']:
                raise ValueError('Overlapping or unordered partitions')
        if partitions[1]['bytes'] != partitions[2]['bytes'] or partitions[3]['bytes'] != partitions[4]['bytes']:
            raise ValueError('A/B slot sizes differ')
        if os.fstat(stream.fileno()).st_size != info.st_size:
            raise ValueError('Image length changed during inspection')
    return {'schema': 1, 'checks': 'probe-gpt-integrity', 'image_bytes': info.st_size,
            'sector_bytes': sector, 'partitions': partitions, 'production_qualified': False}
