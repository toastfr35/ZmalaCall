"""Regression checks for hierarchy/coverage enforcement and the offline publisher."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str((Path(__file__).resolve().parents[3] / 'build_tools')))
import requirements as baseline
from requirements_trace import read_markers

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
        source.write_text('# @llr SLLR001, TLLR001\nvalue = 1\n', encoding='utf-8')
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
        self.assertEqual(report['code_traces']['TLLR001'],
                         [{'path': 'zmala_terminal/common/example.py', 'line': 1}])

    def test_each_llr_needs_a_code_comment(self):
        (self.root / 'zmala_terminal/common/example.py').write_text('# @llr TLLR001\nvalue = 1\n')
        with self.assertRaisesRegex(ValueError, 'SLLR001: no implementation @llr comment'):
            baseline.audit(self.root)

    def test_unknown_trace_id_fails(self):
        (self.root / 'zmala_terminal/common/example.py').write_text('# @llr SLLR999\nvalue = 1\n')
        with self.assertRaisesRegex(ValueError, 'unknown LLR SLLR999'):
            baseline.audit(self.root)

    def test_anchor_file_must_be_a_requirement_reference(self):
        (self.root / 'zmala_terminal/common/unreferenced.py').write_text('# @llr TLLR001\npass\n')
        with self.assertRaisesRegex(ValueError, 'TLLR001 must reference this implementation file'):
            baseline.audit(self.root)

    def test_test_file_cannot_supply_implementation_anchor(self):
        source = self.root / 'zmala_terminal/common/example.py'
        source.write_text('# @llr SLLR001\nvalue = 1\n')
        test = source.parent / 'tests/example.py'
        test.parent.mkdir()
        test.write_text('# @llr TLLR001\npass\n')
        self.change('TLLR001', references=[{'path': p.relative_to(self.root).as_posix()}
                                          for p in (source, test)])
        with self.assertRaisesRegex(ValueError, 'TLLR001: no implementation @llr comment'):
            baseline.audit(self.root)

    def test_referenced_patch_outside_inventory_is_traced(self):
        patch = self.root / 'zmala_server/vendor/sip/sip.js'
        patch.parent.mkdir(parents=True)
        patch.write_text('// @llr SLLR001\nfunction localPatch() {}\n')
        self.change('SLLR001', references=[{'path': p} for p in (
            'zmala_terminal/common/example.py', 'zmala_server/vendor/sip/sip.js')])
        self.assertEqual(len(baseline.audit(self.root)['code_traces']['SLLR001']), 2)

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


class TraceCommentTests(unittest.TestCase):
    def parse(self, suffix, source):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ('source' + suffix)
            path.write_text(source, encoding='utf-8')
            return read_markers(path)

    def test_comment_styles_and_line_numbers(self):
        for suffix, marker in (
            ('.py', '# @llr TLLR001'), ('.sh', '# @llr TLLR001'),
            ('.service', '# @llr TLLR001'), ('.conf', '# @llr TLLR001'),
            ('.js', '// @llr TLLR001'), ('.c', '// @llr TLLR001'),
            ('.css', '/* @llr TLLR001 */'), ('.html', '<!-- @llr TLLR001 -->'),
        ):
            with self.subTest(suffix=suffix):
                self.assertEqual(self.parse(suffix, '\n  ' + marker + '\n'), [(2, ['TLLR001'])])

    def test_python_literals_and_inline_comments_are_not_anchors(self):
        self.assertEqual(self.parse('.py', '''text = """
# @llr TLLR001
"""
text = '# @llr TLLR001'
value = 1  # @llr TLLR001
# @llr SLLR001
'''), [(6, ['SLLR001'])])

    def test_multiple_ids_on_shared_implementation(self):
        self.assertEqual(self.parse('.py', '# @llr SLLR098, TLLR124\n'),
                         [(1, ['SLLR098', 'TLLR124'])])

    def test_malformed_markers_are_not_silently_ignored(self):
        for marker in ('@llr', '@llr: TLLR001', '@llr TLLR001 SLLR001',
                       '@llr TLLR001, TLLR001', '@llr THLR001', '@llr TLLR001 prose'):
            with self.subTest(marker=marker), self.assertRaisesRegex(ValueError, 'malformed @llr'):
                self.parse('.py', '# ' + marker + '\n')

    def test_unclosed_comment_is_invalid(self):
        with self.assertRaisesRegex(ValueError, 'malformed @llr'):
            self.parse('.css', '/* @llr TLLR001\n')

    def test_comment_free_formats_and_inline_strings_do_not_count(self):
        self.assertEqual(self.parse('.json', '{"example":"# @llr TLLR001"}'), [])
        self.assertEqual(self.parse('.js', 'const example = "// @llr TLLR001";'), [])


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
                'source_coverage': {'a/<script>.py': ['TLLR001']}, 'exclusions': {'a&b': '<reason>'},
                'code_traces': {'TLLR001': [{'path': 'a/<script>.py', 'line': 42}]}})
            text = (output / 'coverage.html').read_text(encoding='utf-8')
            self.assertIn('&lt;script&gt;', text)
            self.assertIn('&lt;reason&gt;', text)
            self.assertNotIn('a/<script>', text)
            self.assertIn('id="trace-TLLR001"', text)
            self.assertIn('a/&lt;script&gt;.py:42', text)
            self.assertIn('documents/TLLR.html#TLLR001', text)


if __name__ == '__main__':
    unittest.main()
