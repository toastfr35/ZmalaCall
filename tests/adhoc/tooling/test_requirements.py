"""Regression checks for hierarchy/coverage enforcement and the offline publisher."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str((Path(__file__).resolve().parents[3] / 'build_tools')))
import requirements as baseline
from requirements_trace import read_markers
from requirement_ids import documents, document_prefix, next_id

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
        source.write_text('# @llr LLR-SRV-BOOT-002, LLR-TERM-SYS-003\nvalue = 1\n', encoding='utf-8')
        (self.root/'requirements').mkdir()
        (self.root/'requirements/groups.json').write_text(json.dumps({'SRV':{'BOOT':'Service'},'TERM':{'SYS':'Appliance'}}))
        ids = {'PROD':'PROD001', 'HLR-SRV-BOOT':'HLR-SRV-BOOT-001', 'LLR-SRV-BOOT':'LLR-SRV-BOOT-002',
               'HLR-TERM-SYS':'HLR-TERM-SYS-001', 'LLR-TERM-SYS':'LLR-TERM-SYS-003'}
        for prefix, (folder, parent) in documents(self.root).items():
            path = self.root / 'requirements' / folder
            path.mkdir(parents=True, exist_ok=True)
            self.write(path / '.doorstop.yml', {'settings': {'prefix': prefix, 'parent': parent, 'digits':3, 'sep':'' if prefix=='PROD' else '-'}})
            self.write(path / (ids[prefix]+'.yml'), {
                'active': True, 'normative': True, 'derived': False,
                'header': 'Example', 'text': 'The example shall be present.',
                'area': 'Example', 'scope': 'Core', 'verification': 'Inspect example.',
                'links': [{ids[parent]: None}] if parent else [],
                'references': [{'path':'zmala_terminal/common/example.py','type':'file'}] if prefix.startswith('LLR-') else [],
            })
        for component, prefix, uid in (('server','S','LLR-SRV-BOOT-002'),('terminal','T','LLR-TERM-SYS-003')):
            test = self.root / f'tests/{component}/LLT/example.py'
            test.parent.mkdir(parents=True)
            test.write_text(
                f'# @test {prefix}-LLT-001\n# @requirements {uid}\n'
                '# @environment portable\n'
                '# @plan Supply a fixture input and compare its output against the specified value.\n'
                '# @pass The fixture assertion must succeed without changing any external state or files.\n', encoding='utf-8')
            self.change(uid, references=[{'path':'zmala_terminal/common/example.py','type':'file'},
                {'path':test.relative_to(self.root).as_posix(),'type':'file'}])

    def write(self, path, data):
        path.write_text(self.yaml.safe_dump(data), encoding='utf-8')

    def change(self, uid, **fields):
        prefix = document_prefix(uid)
        path = self.root / 'requirements' / documents(self.root)[prefix][0] / (uid + '.yml')
        data = self.yaml.safe_load(path.read_text(encoding='utf-8'))
        self.write(path, data | fields)

    def test_valid_complete_hierarchy(self):
        report = baseline.audit(self.root)
        self.assertEqual(report['counts']['LLR-TERM-SYS'], 1)
        self.assertEqual(report['source_coverage']['zmala_terminal/common/example.py'],
                         ['LLR-SRV-BOOT-002', 'LLR-TERM-SYS-003'])
        self.assertEqual(report['code_traces']['LLR-TERM-SYS-003'],
                         [{'path': 'zmala_terminal/common/example.py', 'line': 1}])

    def test_numbers_are_shared_between_hlr_and_llr_in_each_theme(self):
        folder = self.root/'requirements/terminal/sys/hlr'
        source = folder/'HLR-TERM-SYS-001.yml'
        source.rename(folder/'HLR-TERM-SYS-003.yml')
        with self.assertRaisesRegex(ValueError, 'group number already used'):
            baseline.audit(self.root)

    def test_next_number_spans_both_levels_and_reserves_migrated_ids(self):
        self.assertEqual(next_id(self.root, 'HLR', 'TERM', 'SYS'), 'HLR-TERM-SYS-004')
        self.assertEqual(next_id(self.root, 'LLR', 'TERM', 'SYS'), 'LLR-TERM-SYS-004')
        (self.root/'requirements/id-migration.json').write_text(json.dumps({'old':'HLR-TERM-SYS-010'}))
        self.assertEqual(next_id(self.root, 'LLR', 'TERM', 'SYS'), 'LLR-TERM-SYS-011')
        self.assertEqual(next_id(self.root, 'LLR', 'SRV', 'BOOT'), 'LLR-SRV-BOOT-003')
        with self.assertRaises(ValueError):
            next_id(self.root, 'LLR', 'TERM', 'ABSENT')

    def test_each_llr_needs_a_code_comment(self):
        (self.root / 'zmala_terminal/common/example.py').write_text('# @llr LLR-TERM-SYS-003\nvalue = 1\n')
        with self.assertRaisesRegex(ValueError, 'LLR-SRV-BOOT-002: no implementation @llr comment'):
            baseline.audit(self.root)

    def test_unknown_trace_id_fails(self):
        (self.root / 'zmala_terminal/common/example.py').write_text('# @llr LLR-SRV-BOOT-999\nvalue = 1\n')
        with self.assertRaisesRegex(ValueError, 'unknown LLR LLR-SRV-BOOT-999'):
            baseline.audit(self.root)

    def test_anchor_file_must_be_a_requirement_reference(self):
        (self.root / 'zmala_terminal/common/unreferenced.py').write_text('# @llr LLR-TERM-SYS-003\npass\n')
        with self.assertRaisesRegex(ValueError, 'LLR-TERM-SYS-003 must reference this implementation file'):
            baseline.audit(self.root)

    def test_test_file_cannot_supply_implementation_anchor(self):
        source = self.root / 'zmala_terminal/common/example.py'
        source.write_text('# @llr LLR-SRV-BOOT-002\nvalue = 1\n')
        test = source.parent / 'tests/example.py'
        test.parent.mkdir()
        test.write_text('# @llr LLR-TERM-SYS-003\npass\n')
        self.change('LLR-TERM-SYS-003', references=[{'path': p.relative_to(self.root).as_posix()}
                                          for p in (source, test)])
        with self.assertRaisesRegex(ValueError, 'LLR-TERM-SYS-003: no implementation @llr comment'):
            baseline.audit(self.root)

    def test_referenced_patch_outside_inventory_is_traced(self):
        patch = self.root / 'zmala_server/vendor/sip/sip.js'
        patch.parent.mkdir(parents=True)
        patch.write_text('// @llr LLR-SRV-BOOT-002\nfunction localPatch() {}\n')
        self.change('LLR-SRV-BOOT-002', references=[{'path': p} for p in (
            'zmala_terminal/common/example.py', 'zmala_server/vendor/sip/sip.js',
            'tests/server/LLT/example.py')])
        self.assertEqual(len(baseline.audit(self.root)['code_traces']['LLR-SRV-BOOT-002']), 2)

    def test_new_module_requires_mapping(self):
        (self.root / 'zmala_terminal/common/unmapped.py').write_text('pass\n')
        with self.assertRaisesRegex(ValueError, 'Unmapped implementation'):
            baseline.audit(self.root)

    def test_component_parent_cannot_cross_branches(self):
        self.change('LLR-TERM-SYS-003', links=[{'HLR-SRV-BOOT-001': None}])
        with self.assertRaisesRegex(ValueError, 'invalid parent'):
            baseline.audit(self.root)

    def test_hlr_cannot_be_orphaned(self):
        self.change('LLR-TERM-SYS-003', links=[])
        with self.assertRaisesRegex(ValueError, 'no lower-level requirement'):
            baseline.audit(self.root)

    def test_broken_reference_and_missing_verification(self):
        self.change('LLR-SRV-BOOT-002', verification='', references=[{'path': '../outside.py'}])
        with self.assertRaisesRegex(ValueError, 'missing verification'):
            baseline.audit(self.root)

    def test_test_reference_alone_is_not_implementation(self):
        path = self.root / 'zmala_terminal/common/tests/example.py'
        path.parent.mkdir()
        path.write_text('pass\n')
        self.change('LLR-SRV-BOOT-002', references=[{'path': path.relative_to(self.root).as_posix()}])
        with self.assertRaisesRegex(ValueError, 'tests alone'):
            baseline.audit(self.root)

    def test_windows_terminal_is_excluded(self):
        self.change('LLR-TERM-SYS-003', references=[{'path': 'zmala_terminal/windows/media.py'}])
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
            ('.py', '# @llr LLR-TERM-SYS-003'), ('.sh', '# @llr LLR-TERM-SYS-003'),
            ('.service', '# @llr LLR-TERM-SYS-003'), ('.conf', '# @llr LLR-TERM-SYS-003'),
            ('.js', '// @llr LLR-TERM-SYS-003'), ('.c', '// @llr LLR-TERM-SYS-003'),
            ('.css', '/* @llr LLR-TERM-SYS-003 */'), ('.html', '<!-- @llr LLR-TERM-SYS-003 -->'),
        ):
            with self.subTest(suffix=suffix):
                self.assertEqual(self.parse(suffix, '\n  ' + marker + '\n'), [(2, ['LLR-TERM-SYS-003'])])

    def test_python_literals_and_inline_comments_are_not_anchors(self):
        self.assertEqual(self.parse('.py', '''text = """
# @llr LLR-TERM-SYS-003
"""
text = '# @llr LLR-TERM-SYS-003'
value = 1  # @llr LLR-TERM-SYS-003
# @llr LLR-SRV-BOOT-002
'''), [(6, ['LLR-SRV-BOOT-002'])])

    def test_multiple_ids_on_shared_implementation(self):
        self.assertEqual(self.parse('.py', '# @llr LLR-SRV-INSTALL-011, LLR-TERM-SYS-012\n'),
                         [(1, ['LLR-SRV-INSTALL-011', 'LLR-TERM-SYS-012'])])

    def test_malformed_markers_are_not_silently_ignored(self):
        for marker in ('@llr', '@llr: LLR-TERM-SYS-003', '@llr LLR-TERM-SYS-003 LLR-SRV-BOOT-002',
                       '@llr LLR-TERM-SYS-003, LLR-TERM-SYS-003', '@llr HLR-TERM-SYS-001', '@llr LLR-TERM-SYS-003 prose', '@llr TLLR001', '@llr LLR-TERM-sys-003'):
            with self.subTest(marker=marker), self.assertRaisesRegex(ValueError, 'malformed @llr'):
                self.parse('.py', '# ' + marker + '\n')

    def test_unclosed_comment_is_invalid(self):
        with self.assertRaisesRegex(ValueError, 'malformed @llr'):
            self.parse('.css', '/* @llr LLR-TERM-SYS-003\n')

    def test_comment_free_formats_and_inline_strings_do_not_count(self):
        self.assertEqual(self.parse('.json', '{"example":"# @llr LLR-TERM-SYS-003"}'), [])
        self.assertEqual(self.parse('.js', 'const example = "// @llr LLR-TERM-SYS-003";'), [])


class ReportTests(unittest.TestCase):
    def test_actual_anchor_parser(self):
        page = baseline.ReportPage('<h2 id="LLR-TERM-SYS-003">x</h2><a href="a.html#x">link</a><h3 id="LLR-TERM-SYS-003">y</h3>')
        self.assertEqual(page.ids, {'LLR-TERM-SYS-003'})
        self.assertEqual(page.links, ['a.html#x'])
        self.assertEqual(page.duplicates, ['LLR-TERM-SYS-003'])

    def test_themed_matrix_has_four_columns_and_preserves_every_derivation(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output/'traceability.html').write_text('<header>Keep navigation</header><div class="matrix"><table>old</table></div><footer>End</footer>', encoding='utf-8')
            items = {'PROD001':{'header':'Product','parents':[]}, 'PROD002':{'header':'Other','parents':[]},
                     'HLR-TERM-MEDIA-001':{'header':'Media <test>', 'parents':['PROD001','PROD002']},
                     'LLR-TERM-MEDIA-002':{'header':'Capture','parents':['HLR-TERM-MEDIA-001']}}
            baseline.write_traceability(output, items)
            text = (output/'traceability.html').read_text(encoding='utf-8')
            self.assertEqual(text.count('<th>'), 4)
            self.assertIn('<header>Keep navigation</header>', text)
            self.assertIn('<footer>End</footer>', text)
            self.assertIn('Media &lt;test&gt;', text)
            self.assertEqual(text.count('documents/LLR-TERM-MEDIA.html#LLR-TERM-MEDIA-002'), 2)
            rows = (output/'traceability.csv').read_text().splitlines()
            self.assertEqual(rows[0], 'Theme,Product,HLR,LLR')
            self.assertEqual(len(rows), 3)
            self.assertIn('TERM-MEDIA,PROD002,HLR-TERM-MEDIA-001,LLR-TERM-MEDIA-002', rows)

    def test_inventory_html_escapes_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            baseline.write_coverage(output, {'counts': {'LLR-TERM-SYS': 1}, 'qualification': 'Unverified',
                'source_coverage': {'a/<script>.py': ['LLR-TERM-SYS-003']}, 'exclusions': {'a&b': '<reason>'},
                'code_traces': {'LLR-TERM-SYS-003': [{'path': 'a/<script>.py', 'line': 42}]}})
            text = (output / 'coverage.html').read_text(encoding='utf-8')
            self.assertIn('&lt;script&gt;', text)
            self.assertIn('&lt;reason&gt;', text)
            self.assertNotIn('a/<script>', text)
            self.assertIn('id="trace-LLR-TERM-SYS-003"', text)
            self.assertIn('a/&lt;script&gt;.py:42', text)
            self.assertIn('documents/LLR-TERM-SYS.html#LLR-TERM-SYS-003', text)


if __name__ == '__main__':
    unittest.main()
