"""Development-tool regressions, not product requirement verification.

Use tiny temporary repositories to prove bad test links/plans fail validation
and that the report distinguishes missing coverage from execution success.
"""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'build_tools'))
from test_trace import audit_tests, read_plan, write_test_report


class TestPlanAuditTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.path = self.root / 'tests/terminal/LLT/example.py'
        self.path.parent.mkdir(parents=True)
        self.header = (
            '# @test T-LLT-001\n'
            '# @requirements LLR-TERM-SYS-003\n'
            '# @environment portable\n'
            '# @plan Supply bad input to the parser and assert rejection without mutation.\n'
            '# @pass All parser assertions pass and original state remains unchanged after rejection.\n'
        )
        self.path.write_text(self.header + 'value = 1\n', encoding='utf-8')
        self.hlt_path = self.root / 'tests/terminal/HLT/scenario.py'
        self.hlt_path.parent.mkdir(parents=True)
        self.hlt_path.write_text(self.header.replace('T-LLT-001', 'T-HLT-001')
                                .replace('LLR-TERM-SYS-003', 'HLR-TERM-SYS-001'), encoding='utf-8')
        self.records = {
            'LLR-TERM-SYS-003': {'prefix': 'LLR-TERM-SYS', 'references': [{'path': 'tests/terminal/LLT/example.py'}]},
            'HLR-TERM-SYS-001': {'prefix': 'HLR-TERM-SYS', 'references': [{'path': 'tests/terminal/HLT/scenario.py'}]},
        }

    def test_valid_plans_are_separate_from_execution(self):
        trace = audit_tests(self.root, self.records)
        self.assertEqual(trace['requirements'], {'LLR-TERM-SYS-003': ['T-LLT-001'], 'HLR-TERM-SYS-001': ['T-HLT-001']})
        self.assertFalse(any(trace['unmapped'].values()))
        self.assertNotIn('passed', trace['tests']['T-LLT-001'])
        self.assertNotIn('passed', trace['tests']['T-HLT-001'])

    def test_every_hlr_needs_a_direct_system_plan(self):
        for uid in ('HLR-SRV-HOST-999', 'HLR-TERM-NET-999'):
            with self.subTest(uid=uid):
                records = self.records | {uid: {'prefix': uid.rsplit('-', 1)[0], 'references': []}}
                with self.assertRaisesRegex(ValueError, f'{uid}: no mapped HLT'):
                    audit_tests(self.root, records)

    def test_every_llr_needs_a_direct_unit_test(self):
        for uid, prefix in (('LLR-SRV-BOOT-999', 'LLR-SRV-BOOT'), ('LLR-TERM-SYS-004', 'LLR-TERM-SYS')):
            with self.subTest(uid=uid):
                records = self.records | {uid: {'prefix': prefix, 'references': []}}
                adhoc = self.root / 'tests/adhoc/experiment.py'
                adhoc.parent.mkdir(exist_ok=True)
                adhoc.write_text(self.header.replace('LLR-TERM-SYS-003', uid), encoding='utf-8')
                with self.assertRaisesRegex(ValueError, f'{uid}: no mapped LLT'):
                    audit_tests(self.root, records)

    def test_unknown_id_wrong_level_and_wrong_component_fail(self):
        for old, new, message in (
                ('LLR-TERM-SYS-003', 'LLR-TERM-SYS-999', 'unknown requirement'),
                ('LLR-TERM-SYS-003', 'HLR-TERM-SYS-001', 'must trace'),
                ('T-LLT-001', 'S-LLT-001', 'component/level')):
            with self.subTest(new=new):
                self.path.write_text(self.header.replace(old, new), encoding='utf-8')
                with self.assertRaisesRegex(ValueError, message):
                    audit_tests(self.root, self.records)

    def test_duplicate_ids_and_repeated_directives_fail(self):
        other = self.path.with_name('other.py')
        other.write_text(self.header, encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'duplicate test ID'):
            audit_tests(self.root, self.records)
        self.path.write_text(self.header + '# @plan Another plan cannot override the original plan.\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'duplicate @plan'):
            read_plan(self.path)

    def test_missing_reciprocal_links_fail_in_both_directions(self):
        self.records['LLR-TERM-SYS-003']['references'] = []
        with self.assertRaisesRegex(ValueError, 'missing reciprocal'):
            audit_tests(self.root, self.records)
        self.records['HLR-TERM-SYS-001']['references'] = [{'path': 'tests/terminal/HLT/missing.py'}]
        with self.assertRaisesRegex(ValueError, 'no reciprocal requirement trace'):
            audit_tests(self.root, self.records)

    def test_embedded_inline_and_late_metadata_cannot_supply_a_plan(self):
        for text in ('"""\n' + self.header + '"""', 'value = 1\n' + self.header,
                     'value = 1  ' + self.header):
            self.path.write_text(text, encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'missing leading'):
                read_plan(self.path)

    def test_missing_plan_invalid_environment_and_duplicate_requirement_fail(self):
        for text, message in (
                ('\n'.join(line for line in self.header.splitlines() if '@plan' not in line), 'missing leading'),
                (self.header.replace('portable', 'anything'), 'unknown test environment'),
                (self.header.replace('@requirements LLR-TERM-SYS-003', '@requirements LLR-TERM-SYS-003, LLR-TERM-SYS-003'), 'duplicate requirement'),
                (self.header.replace('@plan Supply bad input to the parser and assert rejection without mutation.', '@plan Check it.'), 'must explain')):
            self.path.write_text(text, encoding='utf-8')
            with self.assertRaisesRegex(ValueError, message):
                read_plan(self.path)

    def test_old_test_location_is_rejected_but_adhoc_is_not_coverage(self):
        adhoc = self.root / 'tests/adhoc/test_experiment.py'
        adhoc.parent.mkdir()
        adhoc.write_text('assert True\n', encoding='utf-8')
        self.assertEqual(len(audit_tests(self.root, self.records)['tests']), 2)
        old = self.root / 'zmala_server/test_example.py'
        old.parent.mkdir()
        old.write_text('assert True\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'outside tests/'):
            audit_tests(self.root, self.records)

    def test_report_escapes_plan_and_shows_gaps_without_pass_claims(self):
        trace = audit_tests(self.root, self.records)
        trace['tests']['T-LLT-001']['plan'] += ' <script>unsafe</script>'
        # The renderer also supports imported historical reports with gaps.
        trace['unmapped']['HLR-TERM'] = ['HLR-TERM-SYS-999']
        write_test_report(self.root, trace)
        report = (self.root / 'tests.html').read_text(encoding='utf-8')
        self.assertIn('&lt;script&gt;unsafe&lt;/script&gt;', report)
        self.assertNotIn('<script>unsafe', report)
        self.assertIn('No mapped test', report)
        self.assertIn('id="T-LLT-001"', report)
        self.assertIn('documents/LLR-TERM-SYS.html#LLR-TERM-SYS-003', report)


if __name__ == '__main__':
    unittest.main()
