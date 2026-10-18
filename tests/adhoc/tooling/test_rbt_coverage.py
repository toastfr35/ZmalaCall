"""Coverage-tool regressions; never included in product coverage evidence."""
import gzip
import json
from pathlib import Path
import tempfile
import unittest

from build_tools.native_coverage import collect
from build_tools.rbt_coverage import python_metrics, js_metrics


class CoverageReportTests(unittest.TestCase):
    def test_python_definition_execution_does_not_count_uncalled_body(self):
        with tempfile.TemporaryDirectory() as directory:
            import coverage
            root = Path(directory)
            source = root/'sample.py'
            source.write_text('def called():\n    return 1\ndef uncalled():\n    return 2\ncalled()\n', encoding='utf-8')
            unseen = root/'unseen.py'
            unseen.write_text('def unseen():\n    return 3\n', encoding='utf-8')
            cov = coverage.Coverage(config_file=False, data_file=str(root/'.coverage'), include=[str(root/'*.py')])
            cov.start()
            exec(compile(source.read_text(), str(source), 'exec'), {})
            cov.stop()
            cov.json_report(morfs=[str(source), str(unseen)], outfile=str(root/'report.json'))
            metrics = python_metrics(root/'report.json')
            self.assertEqual(metrics['functions'], [1, 3])
            self.assertLess(metrics['statements'][0], metrics['statements'][1])

    def test_javascript_uses_statement_counters_not_line_percentages(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory)/'summary.json'
            file.write_text(json.dumps({'total': {'statements': {'covered': 3, 'total': 5},
                                                  'functions': {'covered': 1, 'total': 2},
                                                  'lines': {'covered': 1, 'total': 1}}}))
            self.assertEqual(js_metrics(file), {'statements': [3, 5], 'functions': [1, 2]})

    def test_native_baseline_adds_unexecuted_code_without_double_counting(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root/'zmala_terminal/linux/media/video/sample.c'
            record = {'file': str(source), 'lines': [{'line_number': 5, 'count': 0}, {'line_number': 9, 'count': 0}],
                      'functions': [{'start_line': 4, 'name': 'called', 'execution_count': 0},
                                    {'start_line': 8, 'name': 'uncalled', 'execution_count': 0}]}
            def write(name, entry):
                data = {'current_working_directory': str(root), 'files': [entry]}
                (root/name).write_bytes(gzip.compress(json.dumps(data).encode()))
            write('baseline.gcov.json.gz', record)
            record['lines'][0]['count'] = 7
            record['functions'][0]['execution_count'] = 7
            write('tested.gcov.json.gz', record)
            write('fixture.gcov.json.gz', record | {'file': str(root/'tests/terminal/LLT/fixture.c')})
            result = collect(root, root)
            self.assertEqual(len(result), 1)
            item = result[source.relative_to(root).as_posix()]
            self.assertEqual(item['lines'], {'5': 7, '9': 0})
            self.assertEqual(item['functions'], {'4:called': 7, '8:uncalled': 0})
