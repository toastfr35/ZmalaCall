"""Read-only image artifact verification; not product runtime/boot evidence."""
import os
from pathlib import Path
import struct
import tempfile
import unittest
import uuid
import zlib

from build_tools.images import inspect_disk


def image(path, sector=512, overlap=False, unequal=False, backup_differs=False):
    count, width, sectors = 128, 128, 2048
    table = bytearray(count*width)
    names = ('bootconfig', 'boot_a', 'boot_b', 'system_a', 'system_b', 'persistent')
    for i, name in enumerate(names):
        first = 64+i*20
        if overlap and i == 2:
            first = 85
        last = first+9+(1 if unequal and i == 2 else 0)
        offset = i*width
        table[offset:offset+16] = uuid.UUID('0fc63daf-8483-4772-8e79-3d69d8477de4').bytes_le
        table[offset+16:offset+32] = uuid.UUID(int=i+1).bytes_le
        struct.pack_into('<2Q', table, offset+32, first, last)
        label = name.encode('utf-16-le')
        table[offset+56:offset+56+len(label)] = label
    data = bytearray(sector*sectors)
    data[450] = 0xee
    data[510:512] = b'\x55\xaa'
    for current, other in ((1, sectors-1), (sectors-1, 1)):
        rows = bytearray(table)
        if backup_differs and current != 1:
            rows[16] ^= 1  # Both copies independently valid but inconsistent.
        table_lba = 2 if current == 1 else sectors-1-(len(rows)+sector-1)//sector
        hdr = bytearray(sector)
        hdr[:8] = b'EFI PART'
        struct.pack_into('<4I4Q', hdr, 8, 0x10000, 92, 0, 0, current, other, 34, sectors-34)
        hdr[56:72] = uuid.UUID(int=42).bytes_le
        struct.pack_into('<Q3I', hdr, 72, table_lba, count, width, zlib.crc32(rows))
        struct.pack_into('<I', hdr, 16, zlib.crc32(hdr[:92]))
        data[current*sector:(current+1)*sector] = hdr
        data[table_lba*sector:table_lba*sector+len(rows)] = rows
    path.write_bytes(data)


class ImageDiskTests(unittest.TestCase):
    def test_gpt_in_both_sector_formats_without_qualifying_boot(self):
        with tempfile.TemporaryDirectory() as temporary:
            for sector in (512, 4096):
                path = Path(temporary)/str(sector)
                image(path, sector)
                before = path.read_bytes()
                result = inspect_disk.audit(path, sector)
                self.assertEqual([p['label'] for p in result['partitions']],
                                 ['bootconfig', 'boot_a', 'boot_b', 'system_a', 'system_b', 'persistent'])
                self.assertFalse(result['production_qualified'])
                self.assertEqual(path.read_bytes(), before)

    def test_header_array_and_backup_corruption(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'image'
            for offset in (512+16, 2*512+16, 2047*512+16):
                image(path)
                with path.open('r+b') as stream:
                    stream.seek(offset)
                    changed = stream.read(1)[0] ^ 1
                    stream.seek(offset)
                    stream.write(bytes([changed]))
                with self.assertRaisesRegex(ValueError, 'checksum'):
                    inspect_disk.audit(path)

    def test_individually_valid_inconsistent_or_unsafe_layouts(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'image'
            for options, message in (({'overlap': True}, 'Overlapping'),
                                     ({'unequal': True}, 'sizes differ'),
                                     ({'backup_differs': True}, 'disagree')):
                image(path, **options)
                with self.assertRaisesRegex(ValueError, message):
                    inspect_disk.audit(path)

    def test_plain_or_truncated_files_are_not_disk_images(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'image'
            path.write_bytes(b'not-an-image')
            with self.assertRaisesRegex(ValueError, 'length'):
                inspect_disk.audit(path)
            path.write_bytes(bytes(512*100))
            with self.assertRaisesRegex(ValueError, 'MBR'):
                inspect_disk.audit(path)
            with self.assertRaisesRegex(ValueError, 'sector sizes'):
                inspect_disk.audit(path, 123)

    @unittest.skipIf(os.name == 'nt', 'Linux builder filesystem links')
    def test_linked_input_is_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'image'
            image(path)
            link = Path(temporary)/'link'
            link.symlink_to(path)
            with self.assertRaisesRegex(ValueError, 'regular image'):
                inspect_disk.audit(link)


if __name__ == '__main__':
    unittest.main()
