"""Publishing-tool regressions, not terminal product verification."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from xml.etree import ElementTree

from build_tools.leaflet.generate import SOURCE, impose, load_catalogs, render_html


class TerminalLeafletTests(unittest.TestCase):
    def test_all_supported_languages_have_complete_copy_and_direction(self):
        languages, catalogs = load_catalogs()
        self.assertEqual(set(languages), set(catalogs))
        for code, info in languages.items():
            with self.subTest(code=code):
                page = render_html(code, info, catalogs[code])
                self.assertEqual(page.count('<section class="page'), 4)
                self.assertIn(f'lang="{code}" dir="{info["direction"]}"', page)
                self.assertNotIn('Ethernet', json.dumps(catalogs[code]))
                self.assertNotIn('microSD', json.dumps(catalogs[code]))
                self.assertNotIn('Terminals > Setup', json.dumps(catalogs[code]))

    def test_missing_language_and_untranslated_field_are_rejected(self):
        languages, catalogs = load_catalogs()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'locales').mkdir()
            with self.assertRaisesRegex(ValueError, 'Locale mismatch'):
                load_catalogs(root, {'en': languages['en']})
            data = copy.deepcopy(catalogs['en'])
            data['setup'][2][1] = ''
            path = root / 'locales/en.json'
            path.write_text(json.dumps(data), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'empty or non-text'):
                load_catalogs(root, {'en': languages['en']})
            data['setup'][2][1] = 'Complete'
            del data['help']
            path.write_text(json.dumps(data), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'translation keys'):
                load_catalogs(root, {'en': languages['en']})

    def test_translation_markup_is_escaped(self):
        languages, catalogs = load_catalogs()
        data = copy.deepcopy(catalogs['en'])
        data['title'] = '<script>unsafe & text</script>'
        result = render_html('en', languages['en'], data)
        self.assertNotIn('<script>', result)
        self.assertIn('&lt;script&gt;unsafe &amp; text&lt;/script&gt;', result)

    def test_vector_art_has_no_text_or_foreign_objects(self):
        for path in (SOURCE / 'assets').glob('*.svg'):
            with self.subTest(asset=path.name):
                root = ElementTree.fromstring(path.read_text(encoding='utf-8'))
                for node in root.iter():
                    self.assertNotIn(node.tag.rsplit('}', 1)[-1], ('text', 'foreignObject', 'image'))
                    self.assertFalse((node.text or '').strip())

    def test_imposition_order_dimensions_and_positions_in_both_directions(self):
        from pypdf import PdfReader, PdfWriter
        from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            writer = PdfWriter()
            font = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
                                     NameObject('/Subtype'): NameObject('/Type1'),
                                     NameObject('/BaseFont'): NameObject('/Helvetica')})
            for number in range(1, 5):
                page = writer.add_blank_page(148.5 / 25.4 * 72, 210 / 25.4 * 72)
                page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
                stream = DecodedStreamObject()
                stream.set_data(f'BT /F1 12 Tf 20 200 Td (PAGE{number}) Tj ET'.encode())
                page[NameObject('/Contents')] = stream
            writer.add_metadata({'/Title': 'Test'})
            source = folder / 'reading.pdf'
            with source.open('wb') as output:
                writer.write(output)
            for direction, expected in [('ltr', (('PAGE4', 'PAGE1'), ('PAGE2', 'PAGE3'))),
                                        ('rtl', (('PAGE1', 'PAGE4'), ('PAGE3', 'PAGE2')))]:
                destination = folder / (direction + '.pdf')
                impose(source, destination, direction)
                pages = PdfReader(destination).pages
                self.assertEqual(len(pages), 2)
                for page, pair in zip(pages, expected):
                    self.assertAlmostEqual(float(page.mediabox.width), 297 / 25.4 * 72, places=3)
                    self.assertAlmostEqual(float(page.mediabox.height), 210 / 25.4 * 72, places=3)
                    positions = {}
                    def visit(text, cm, tm, font, size):
                        if text.strip():
                            positions[text.strip()] = cm[4] + tm[4]
                    page.extract_text(visitor_text=visit)
                    self.assertLess(positions[pair[0]], float(page.mediabox.width) / 2)
                    self.assertGreaterEqual(positions[pair[1]], float(page.mediabox.width) / 2)
                    self.assertEqual(page.extract_text().split(), list(pair))

    def test_imposition_rejects_wrong_page_count(self):
        from pypdf import PdfWriter
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            source = folder / 'bad.pdf'
            writer = PdfWriter()
            writer.add_blank_page(100, 100)
            with source.open('wb') as output:
                writer.write(output)
            with self.assertRaisesRegex(ValueError, 'Expected four reading pages'):
                impose(source, folder / 'out.pdf')


if __name__ == '__main__':
    unittest.main()
