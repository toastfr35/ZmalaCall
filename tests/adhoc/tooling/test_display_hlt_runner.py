"""Guard test discovery: never launch live or native scenarios implicitly."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]/'build_tools'))
import run_display_hlt as runner


class DisplayRunnerTests(unittest.TestCase):
    def test_only_standalone_display_scenarios_are_selected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            directory = root/'tests/terminal/HLT'
            directory.mkdir(parents=True)
            for number, (name, environment) in enumerate([
                    ('ui.py', 'display'), ('live.py', 'hardware'), ('native.py', 'native-display'),
                    ('unit.py', 'portable'), ('test_ui.py', 'display')], 1):
                (directory/name).write_text(f'''# @test T-HLT-{number:03}
# @requirements HLR-TERM-UI-012
# @environment {environment}
# @plan Drive an isolated fixture and inspect its visible expected result.
# @pass The expected result is observed without changing the live host.
''')
            (directory/'__init__.py').touch()
            self.assertEqual(list(runner.scenarios(root)), [(directory/'ui.py', 'T-HLT-001')])

    def test_missing_display_is_a_failure_not_a_silent_success(self):
        with patch.object(runner.sys, 'platform', 'linux'), patch.dict('os.environ', {}, clear=True), \
                patch.object(runner.subprocess, 'run') as run:
            with self.assertRaisesRegex(SystemExit, 'xvfb-run'):
                runner.main()
            run.assert_not_called()

    def test_failed_scenario_stops_the_runner(self):
        with patch.dict('os.environ', {'DISPLAY': ':99'}), patch.object(runner, 'scenarios',
                return_value=[(Path('first.py'), 'T-HLT-001'), (Path('second.py'), 'T-HLT-002')]), \
                patch.object(runner.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'fixture')) as run, \
                patch('builtins.print'):
            with self.assertRaises(subprocess.CalledProcessError):
                runner.main()
            run.assert_called_once()
            self.assertTrue(run.call_args.kwargs['check'])
            self.assertEqual(run.call_args.kwargs['timeout'], 900)


if __name__ == '__main__':
    unittest.main()
