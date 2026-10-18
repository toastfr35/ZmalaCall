"""Regression checks for hierarchy/coverage enforcement and the offline publisher."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import requirements as baseline

HAS_YAML = importlib.util.find_spec('yaml') is not None


@unittest.skipUnless(HAS_YAML, 'Run in the Doorstop tooling environment (portable CI).')
class BaselineAuditTests(unittest.TestCase):
    def setUp(self):
        import yaml
        self.yaml = yaml
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        source = self.root / 'zmala_terminal/common/example.py'
        source.parent.mkdir(parents=True)
        source.write_text('value = 1\n', encoding='utf-8')
        for prefix, (folder, parent) in baseline.DOCUMENTS.items():
            path = self.root / 'requirements' / folder
            path.mkdir(parents=True, exist_ok=True)
            self.write(path / '.doorstop.yml', {'settings': {'prefix': prefix, 'parent': parent}})
            self.write(path / (prefix + '001.yml'), {
                'active': True, 'normative': True, 'derived': False,
                'header': 'Example', 'text': 'The example shall be present.',
                'area': 'Example', 'scope': 'Core', 'verification': 'Inspect example.',
                'links': [{parent + '001': None}] if parent else [],
                'references': [{'path': 'zmala_terminal/common/example.py', 'type': 'file'}]
                if prefix in ('SLLR', 'TLLR') else [],
            })

    def write(self, path, data):
        path.write_text(self.yaml.safe_dump(data), encoding='utf-8')

    def change(self, uid, **fields):
        prefix = uid.rstrip('0123456789')
        path = self.root / 'requirements' / baseline.DOCUMENTS[prefix][0] / (uid + '.yml')
        data = self.yaml.safe_load(path.read_text(encoding='utf-8'))
        self.write(path, data | fields)

    def test_valid_complete_hierarchy(self):
        report = baseline.audit(self.root)
        self.assertEqual(report['counts']['TLLR'], 1)
        self.assertEqual(report['source_coverage']['zmala_terminal/common/example.py'],
                         ['SLLR001', 'TLLR001'])

    def test_new_module_requires_mapping(self):
        (self.root / 'zmala_terminal/common/unmapped.py').write_text('pass\n')
        with self.assertRaisesRegex(ValueError, 'Unmapped implementation'):
            baseline.audit(self.root)

    def test_component_parent_cannot_cross_branches(self):
        self.change('TLLR001', links=[{'SHLR001': None}])
        with self.assertRaisesRegex(ValueError, 'invalid parent'):
            baseline.audit(self.root)

    def test_hlr_cannot_be_orphaned(self):
        self.change('TLLR001', links=[])
        with self.assertRaisesRegex(ValueError, 'no lower-level requirement'):
            baseline.audit(self.root)

    def test_broken_reference_and_missing_verification(self):
        self.change('SLLR001', verification='', references=[{'path': '../outside.py'}])
        with self.assertRaisesRegex(ValueError, 'missing verification'):
            baseline.audit(self.root)

    def test_test_reference_alone_is_not_implementation(self):
        path = self.root / 'zmala_terminal/common/tests/example.py'
        path.parent.mkdir()
        path.write_text('pass\n')
        self.change('SLLR001', references=[{'path': path.relative_to(self.root).as_posix()}])
        with self.assertRaisesRegex(ValueError, 'tests alone'):
            baseline.audit(self.root)

    def test_windows_terminal_is_excluded(self):
        self.change('TLLR001', references=[{'path': 'zmala_terminal/windows/media.py'}])
        with self.assertRaisesRegex(ValueError, 'outside this baseline'):
            baseline.audit(self.root)

    def test_exclusion_reason_is_visible(self):
        vendor = self.root / 'zmala_server/vendor/sip/sip.js'
        vendor.parent.mkdir(parents=True)
        vendor.write_text('// vendor\n')
        report = baseline.audit(self.root)
        self.assertIn('Third-party', report['exclusions']['zmala_server/vendor/sip/sip.js'])


class ReportTests(unittest.TestCase):
    def test_actual_anchor_parser(self):
        page = baseline.ReportPage('<h2 id="TLLR001">x</h2><a href="a.html#x">link</a><h3 id="TLLR001">y</h3>')
        self.assertEqual(page.ids, {'TLLR001'})
        self.assertEqual(page.links, ['a.html#x'])
        self.assertEqual(page.duplicates, ['TLLR001'])

    def test_inventory_html_escapes_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            baseline.write_coverage(output, {'counts': {'TLLR': 1}, 'qualification': 'Unverified',
                'source_coverage': {'a/<script>.py': ['TLLR001']}, 'exclusions': {'a&b': '<reason>'}})
            text = (output / 'coverage.html').read_text(encoding='utf-8')
            self.assertIn('&lt;script&gt;', text)
            self.assertIn('&lt;reason&gt;', text)
            self.assertNotIn('a/<script>', text)


if __name__ == '__main__':
    unittest.main()
