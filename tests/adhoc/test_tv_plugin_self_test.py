"""Development-tool regression checks; these do not qualify a physical TV."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from build_tools.tv_plugin_self_test import package_report, render_html, run_sequence


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
        self.assertEqual(len(photos), len(report['steps']))
        self.assertEqual([a for m, a in self.calls if m == 'set_current_input'], [['other'], ['other'], ['other'], ['original']])
        self.assertEqual(report['visual_verdict'], 'Not assessed')
        self.assertEqual([step['method'] for step in report['steps'][:4]],
                         [None, 'set_power_off', 'set_power_on', 'set_power_on'])
        self.assertEqual([step['delay_seconds'] for step in report['steps'][1:4]], [5, 5, 5])

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
        self.assertEqual(report['steps'][2]['power']['status'], 'not observed')
        with tempfile.TemporaryDirectory() as directory:
            self.assertIn('Interrupted', render_html(report, Path(directory)))
