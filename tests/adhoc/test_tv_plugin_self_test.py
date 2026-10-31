"""Development-tool regression checks; these do not qualify a physical TV."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from build_tools.linux.tv_plugin_self_test import package_report, render_html, run_sequence


class TVSelfTestTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.power = False
        self.source = 'original'

    def invoke(self, method, args):
        self.calls.append((method, args))
        if method == 'get_capabilities':
            value = ['get_power_status', 'get_current_input', 'set_power_on', 'set_power_off', 'set_current_input']
        elif method == 'get_model':
            value = '<Example TV>'
        elif method == 'get_power_status':
            value = self.power
        elif method == 'get_current_input':
            value = self.source
        else:
            if method == 'set_power_on':
                self.power = True
            elif method == 'set_power_off':
                self.power = False
            else:
                self.source = args[0]
            value = True
        return {'status': 'returned', 'value': value}

    def test_sequence_restores_baseline_and_records_each_step(self):
        photos = []
        report = run_sequence(self.invoke, lambda index: photos.append(index), ['other'], sleep=lambda _: None)
        self.assertFalse(self.power)
        self.assertEqual(self.source, 'original')
        self.assertEqual(len(photos), 1 + 3 * (len(report['steps']) - 1))
        self.assertEqual([a for m, a in self.calls if m == 'set_current_input'], [['other'], ['other'], ['other'], ['original']])
        self.assertEqual(report['visual_verdict'], 'Not assessed')
        self.assertEqual([step['method'] for step in report['steps'][:4]],
                         [None, 'set_power_off', 'set_power_on', 'set_power_on'])
        self.assertEqual([step['delay_seconds'] for step in report['steps'][1:4]], [5, 5, 5])

    def test_camera_failure_aborts_further_experiments_but_restores_baseline(self):
        def photo(index):
            if index == 2:
                raise OSError('Camera disconnected')
        report = run_sequence(self.invoke, photo, ['other'], sleep=lambda _: None)
        self.assertEqual(report['sequence_status'], 'Interrupted: RuntimeError')
        self.assertEqual(report['steps'][1]['observations'][0]['photo_error'], 'OSError')
        self.assertFalse(any(m == 'set_current_input' and args == ['other'] for m, args in self.calls))
        self.assertFalse(self.power)
        self.assertEqual(self.source, 'original')

    def test_unknown_power_runs_observation_only(self):
        self.power = None
        report = run_sequence(self.invoke, lambda _: None, ['other'], sleep=lambda _: None)
        self.assertTrue(report['sequence_status'].startswith('Observation only'))
        self.assertFalse(any(m.startswith('set_') for m, _ in self.calls))

    def test_missing_initial_photo_does_not_start_test_actions(self):
        def camera(_):
            raise TimeoutError()
        report = run_sequence(self.invoke, camera, ['other'], sleep=lambda _: None)
        self.assertEqual(report['sequence_status'], 'Interrupted: RuntimeError')
        self.assertFalse(any(m.startswith('set_') for m, _ in self.calls))

    def test_interruption_attempts_restoration_and_retains_evidence(self):
        def invoke(method, args):
            if method == 'set_current_input' and args == ['other']:
                raise KeyboardInterrupt()
            return self.invoke(method, args)
        report = run_sequence(invoke, lambda _: None, ['other'], sleep=lambda _: None)
        self.assertFalse(self.power)
        self.assertEqual(self.source, 'original')
        self.assertEqual(report['sequence_status'], 'Interrupted: KeyboardInterrupt')

    def test_html_escapes_values_embeds_photos_and_zip_excludes_private_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / 'report'
            folder.mkdir()
            (folder / 'photo-01.jpg').write_bytes(b'example-photo')
            (folder / 'private-config.json').write_text('secret')
            report = run_sequence(self.invoke, lambda _: 'photo-01.jpg', [], sleep=lambda _: None)
            page = render_html(report, folder)
            self.assertIn('&lt;Example TV&gt;', page)
            self.assertIn('data:image/jpeg;base64,', page)
            self.assertNotIn('secret', page)
            archive = root / 'evidence.zip'
            package_report(report, folder, archive)
            with zipfile.ZipFile(archive) as zipped:
                self.assertEqual(set(zipped.namelist()), {'index.html', 'report.json', 'photo-01.jpg'})
                self.assertEqual(json.loads(zipped.read('report.json'))['visual_verdict'], 'Not assessed')
            with self.assertRaises(FileExistsError):
                package_report(report, folder, archive)

    def test_cli_import_does_not_touch_hardware(self):
        spec = importlib.util.spec_from_file_location('tv_self_test_cli', 'build_tools/linux/tv-plugin-self-test.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(len(module.METHODS), 7)

    def test_every_directed_input_transition_and_per_input_power_cycle(self):
        report = run_sequence(self.invoke, lambda _: None, ['A', 'B'], sleep=lambda _: None)
        labels = [s['label'] for s in report['steps']]
        for source in ['A', 'B']:
            self.assertIn('Standby from input ' + source, labels)
            self.assertIn('Repeat standby from ' + source, labels)
            self.assertIn('Wake after standby from ' + source, labels)
        self.assertIn('Switch A → B', labels)
        self.assertIn('Switch B → A', labels)

    def test_interrupt_during_photo_still_produces_a_report(self):
        def photo(index):
            if index == 3:
                raise KeyboardInterrupt()
        report = run_sequence(self.invoke, photo, ['other'], sleep=lambda _: None)
        self.assertEqual(report['sequence_status'], 'Interrupted: KeyboardInterrupt')
        with tempfile.TemporaryDirectory() as directory:
            self.assertIn('Interrupted', render_html(report, Path(directory)))

    def test_three_absolute_deadlines_without_intervening_commands(self):
        now = [0.0]
        events = []
        def sleep(seconds):
            now[0] += seconds
        def invoke(method, args):
            events.append(method)
            return self.invoke(method, args)
        def snapshot(index):
            events.append('photo')
            now[0] += 1
        report = run_sequence(invoke, snapshot, [], sleep=sleep, clock=lambda: now[0])
        samples = report['steps'][1]['observations']
        self.assertEqual([s['started_seconds'] for s in samples], [5, 10, 15])
        start = events.index('set_power_off')
        end = events.index('set_power_on')
        self.assertEqual(events[start:end].count('photo'), 3)
        self.assertFalse(any(e.startswith('set_') for e in events[start+1:end]))

    def test_single_sample_controls_settling_and_records_query_overhead(self):
        now = [0.0]
        def sleep(seconds):
            now[0] += seconds
        def invoke(method, args):
            now[0] += .2
            return self.invoke(method, args)
        def snapshot(index):
            now[0] += .05
        report = run_sequence(invoke, snapshot, [], delay=5, sleep=sleep,
                              clock=lambda: now[0], observation_count=1)
        for step in report['steps'][1:]:
            self.assertEqual(len(step['observations']), 1)
            sample = step['observations'][0]
            self.assertEqual(sample['started_seconds'], 5)
            self.assertEqual(sample['power_query_started_seconds'], 5.05)
            self.assertEqual(sample['input_query_started_seconds'], 5.25)
        self.assertEqual(report['steps'][2]['gap_since_previous_command_seconds'], 5.45)

    def test_camera_wait_detects_dead_process_and_missing_receipt(self):
        from unittest.mock import Mock, patch
        spec = importlib.util.spec_from_file_location('tv_cli', 'build_tools/linux/tv-plugin-self-test.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'missing'
            with self.assertRaises(RuntimeError):
                module.wait_for_file(path, Mock(poll=Mock(return_value=1)), 5)
            with patch.object(module.time, 'monotonic', side_effect=[0, 6]):
                with self.assertRaises(TimeoutError):
                    module.wait_for_file(path, Mock(poll=Mock(return_value=None)), 5)

    def test_continuous_camera_warms_once_and_saves_next_requested_frame(self):
        from types import SimpleNamespace
        from unittest.mock import Mock, patch
        spec = importlib.util.spec_from_file_location('tv_cli_camera', 'build_tools/linux/tv-plugin-self-test.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            frames = [0]
            def read():
                frames[0] += 1
                if frames[0] == 30:
                    (folder / 'camera-request.json').write_text('1')
                if frames[0] == 32:
                    raise RuntimeError('End fake stream')
                return True, frames[0]
            camera = Mock(read=read)
            cv = Mock(VideoCapture=Mock(return_value=camera), imwrite=Mock(return_value=True))
            with patch.dict('sys.modules', {'cv2': cv}):
                with self.assertRaisesRegex(RuntimeError, 'End fake stream'):
                    module.capture_stream(SimpleNamespace(camera='/dev/fake', capture_stream=directory))
            self.assertTrue((folder / 'camera-ready').exists())
            self.assertTrue((folder / 'capture-1.json').exists())
            cv.imwrite.assert_called_once_with(str(folder / 'photo-01.jpg'), 31)
            cv.VideoCapture.assert_called_once()
            camera.release.assert_called_once()


class TVProcessCleanupTests(unittest.TestCase):
    def test_forced_termination_has_a_second_deadline(self):
        import subprocess
        from unittest.mock import Mock
        from build_tools.linux.tv_test_processes import stop_process
        process = Mock()
        process.poll.return_value = None
        process.wait.side_effect = [subprocess.TimeoutExpired('camera', 5), None]
        stop_process(process)
        process.terminate.assert_called_once()
        process.kill.assert_called_once()
        self.assertEqual([c.kwargs for c in process.wait.call_args_list], [{'timeout': 5}, {'timeout': 5}])

    def test_cleanup_attempts_card_and_restart_even_if_camera_will_not_exit(self):
        import subprocess
        from unittest.mock import Mock, patch
        from build_tools.linux import tv_test_processes as processes
        camera, card = Mock(), Mock()
        with patch.object(processes, 'stop_process', side_effect=[subprocess.TimeoutExpired('private-camera', 5), None]) as stop, \
                patch.object(processes.subprocess, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'camera: TimeoutExpired') as raised:
                processes.cleanup(camera, card, True)
            self.assertEqual([c.args[0] for c in stop.call_args_list], [camera, card])
            run.assert_called_once_with(['sudo', '-n', 'systemctl', 'start', 'zmalacall-terminal'], check=True, timeout=30)
            self.assertNotIn('private-camera', str(raised.exception))

    def test_inactive_terminal_is_not_started_by_cleanup(self):
        from unittest.mock import patch
        from build_tools.linux import tv_test_processes as processes
        with patch.object(processes.subprocess, 'run') as run:
            processes.cleanup(None, None, False)
            run.assert_not_called()

    def test_partial_service_stop_still_restarts_terminal(self):
        import subprocess
        from unittest.mock import patch
        spec = importlib.util.spec_from_file_location('tv_cli_stop', 'build_tools/linux/tv-plugin-self-test.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(module.sys, 'argv', ['tv-test', '--operate-tv', '--pause-terminal', '--output', str(Path(directory)/'result.zip')]), \
                patch.object(module.os, 'umask'), \
                patch.object(module.subprocess, 'run', side_effect=[
                    subprocess.CompletedProcess([], 0), subprocess.TimeoutExpired('stop', 30),
                    subprocess.CompletedProcess([], 0)]) as run:
            with self.assertRaises(subprocess.TimeoutExpired):
                module.main()
            self.assertEqual(run.call_args_list[-1].args[0], ['sudo', '-n', 'systemctl', 'start', 'zmalacall-terminal'])
            self.assertEqual(run.call_count, 3)
