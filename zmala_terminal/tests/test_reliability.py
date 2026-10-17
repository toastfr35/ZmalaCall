"""Regression coverage for unattended recovery, with no native devices or live server."""
import hashlib
import json
from pathlib import Path
import queue
import struct
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from configuration import Configuration
from maintenance import MaintenanceAgent, bounded_output
from main import Terminal
from missed_calls import MissedCallsStore
from model import TerminalModel, State
from photo_cache import PhotoCache, valid_photo
from provisioning import Enrollment
from setup_flow import ProvisioningFlow
from test_terminal import config


def png():
    def chunk(kind, payload):
        return struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', zlib.crc32(kind + payload))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)) +
            chunk(b'IDAT', zlib.compress(b'\0\xff\0\0')) + chunk(b'IEND', b''))


class ReliabilityTests(unittest.TestCase):
    def test_output_contract_counts_replacement_characters_and_json_expansion(self):
        for stdout, stderr in [(b'\0' * 65536, b''), (b'\xff' * 65536, b'error'),
                               ('日本語'.encode() * 10000, 'été'.encode() * 10000)]:
            with self.subTest(stdout=stdout[:10]):
                result = bounded_output(stdout, stderr)
                size = sum(len(result[k].encode()) for k in ('stdout', 'stderr'))
                self.assertLessEqual(size, 65536)
                self.assertLess(len(json.dumps(result).encode()), 400000)
                self.assertEqual(result['truncated'], size < len(stdout.decode(errors='replace').encode()) + len(stderr.decode(errors='replace').encode()))

    def test_permanent_results_do_not_stall_next_job_and_transient_results_retry_without_execution(self):
        for code in (400, 413, 500):
            with self.subTest(code=code):
                agent = MaintenanceAgent.__new__(MaintenanceAgent)
                agent.cancelled, agent.interval = threading.Event(), 0
                submitted, executions, claims = [], [], []
                job = {'id': 'one', 'command': 'echo once', 'timeout_seconds': 5, 'lease': 'lease'}
                def request(route, data):
                    if route == '/api/console/next':
                        claims.append(route)
                        if len(claims) == 1:
                            return json.dumps({'job': job})
                        agent.cancelled.set()
                        return '{}'
                    submitted.append(data)
                    if len(submitted) == 1 or code != 500:
                        raise HTTPError(route, code, 'injected', {}, None)
                    return '{}'
                agent.configuration = Mock(request=request)
                def execute(*args):
                    executions.append(args)
                    return {'status': 'completed', 'exit_code': 0, 'stdout': 'ok', 'stderr': '', 'truncated': False}
                with patch('maintenance.run_command', execute):
                    agent.loop()
                self.assertEqual(len(executions), 1)
                self.assertEqual(len(claims), 2)
                self.assertEqual(len(submitted), 2)
                self.assertEqual(submitted[1]['lease'], 'lease')
                if code == 500:
                    self.assertEqual(submitted[0], submitted[1])
                else:
                    self.assertEqual(submitted[1]['status'], 'failed')

    def test_revoked_contact_counts_stay_pruned_after_restart_and_regrant(self):
        with tempfile.TemporaryDirectory() as directory:
            store = MissedCallsStore(Path(directory) / 'counts.json')
            model = TerminalModel(); model.configure(config()); model.mark_notification('alice')
            store.save(model.config, model.notifications)
            revoked = config(); revoked['contacts'][0].update(can_call=False, can_receive=False)
            model.configure(revoked)
            self.assertEqual(model.notification_total, 0)
            self.assertEqual(store.load_counts(revoked), {})
            store.save(revoked, model.notifications)
            self.assertEqual(MissedCallsStore(store.path).load_counts(config()), {})

    def test_failed_native_reconfiguration_preserves_applied_revision_and_retries(self):
        terminal = Terminal.__new__(Terminal)
        terminal.model = TerminalModel(); terminal.model.configure(config())
        terminal.setup_stage = None; terminal.available_fonts = set()
        terminal.root = Mock(); terminal.render = Mock(); terminal.text = lambda key: key
        terminal.engine = old = Mock(); terminal.current_settings = {}; terminal.profile = 'test'
        terminal.missed_calls_store = Mock(account=Mock(return_value=['family.test', 'terminal']))
        terminal.diagnostics = {}; terminal.engine_retry_at = 0
        terminal.video_window = 0
        terminal.preview_window = 0
        desired = config(); desired['configuration_version'] = 2; desired['sip']['password'] = 'new'
        replacement = Mock()
        with patch('main.Engine', side_effect=[RuntimeError('native initialization failed'), replacement]) as build:
            with patch('configuration_control.time.monotonic', return_value=100):
                terminal.apply_config(desired)
                self.assertIsNone(terminal.engine)
                self.assertEqual(terminal.model.config['configuration_version'], 1)
                self.assertEqual(terminal.pending_config, desired)
                old.close.assert_called_once()
                terminal.apply_poll_config(desired)
                self.assertEqual(build.call_count, 1, 'Backoff must prevent a poll retry storm')
            with patch('configuration_control.time.monotonic', return_value=106):
                terminal.apply_poll_config(desired)
            self.assertIs(terminal.engine, replacement)
            self.assertEqual(terminal.model.config['configuration_version'], 2)
            self.assertIsNone(terminal.pending_config)
            self.assertEqual(terminal.notice, '')

    def test_frame_rate_change_waits_for_call_end_and_rebuilds_only_once(self):
        from video_settings import VideoSettings
        terminal = Terminal.__new__(Terminal)
        terminal.model = TerminalModel(); terminal.model.configure(config())
        terminal.model.state = State.IN_CALL
        terminal.setup_stage = None; terminal.available_fonts = set()
        terminal.root = Mock(); terminal.render = Mock(); terminal.text = lambda key: key
        terminal.engine = old = Mock(auto_framing=None, audio_profile='normal')
        old.video_settings = VideoSettings.for_config({})
        terminal.current_settings = {}; terminal.profile = 'test'
        terminal.video_window = terminal.preview_window = 0
        desired = config(); desired.update(configuration_version=2, video_fps=25)
        replacement = Mock(auto_framing=None, audio_profile='normal')
        replacement.video_settings = VideoSettings.for_config(desired)
        with patch('main.Engine', return_value=replacement) as build:
            terminal.apply_config(desired)
            build.assert_not_called(); old.close.assert_not_called()
            self.assertEqual(terminal.pending_config, desired)
            terminal.model.state = State.HOME
            terminal.configure_engine(desired, desired['sip'], 'normal')
            build.assert_called_once(); old.close.assert_called_once()
            terminal.configure_engine(desired, desired['sip'], 'normal')
            self.assertEqual(build.call_count, 1)

    def test_setup_failure_feedback_survives_retry_and_ignores_stale_results(self):
        flow = ProvisioningFlow()
        flow.generation = 2; flow.closed = False; flow.setup_busy = True
        flow.setup_stage = 'server'; flow.render = Mock()
        flow.enrollment = Mock(value={}); flow.last_qr = ('', 0)
        flow.setup_result(2, 'error', None)
        self.assertTrue(flow.setup_feedback)
        self.assertFalse(flow.setup_busy)
        self.assertEqual(flow.setup_stage, 'server')
        flow.setup_result(1, 'forgot', None)
        self.assertTrue(flow.setup_feedback)
        # A malformed QR must be explained without starting a worker.
        flow.needs_pairing = Mock(return_value=False)
        flow.qr_found('wrong QR type')
        self.assertTrue(flow.setup_feedback)
        flow.render.assert_called()
        flow.stop_scanner = Mock()
        flow.setup_result(2, 'wifi', {})
        self.assertFalse(flow.setup_feedback)
        self.assertEqual(flow.setup_stage, 'wifi_ready')

    def test_linux_wifi_cleanup_survives_restart_failure_and_clears_only_on_success(self):
        with tempfile.TemporaryDirectory() as directory:
            enrollment = Enrollment(directory)
            enrollment.set_wifi({'linux_profile': 'ZmalaCall-test-one', 'linux_uuid': 'one', 'password': 'secret'})
            enrollment.set_server({'device_token': 'secret-token'})
            enrollment.reset()
            restored = Enrollment(directory)
            self.assertEqual(restored.stage, 'wifi')
            self.assertEqual(restored.value, {'version': 1, 'wifi_cleanup': {'linux_profile': 'ZmalaCall-test-one', 'linux_uuid': 'one'}})
            flow = ProvisioningFlow()
            flow.enrollment = restored; flow.setup_busy = False; flow.generation = 1
            flow.profile = 'test'; flow.messages = queue.Queue(); flow.closed = False
            flow.render = Mock(); flow.start_scanner = Mock(); flow.setup_stage = 'wifi'
            with patch('setup_flow.forget_wifi', side_effect=OSError('offline')):
                flow.start_wifi_cleanup()
                _, event = flow.messages.get(timeout=2); flow.setup_result(*event)
            self.assertIn('wifi_cleanup', Enrollment(directory).value)
            with patch('setup_flow.forget_wifi') as forget:
                flow.start_wifi_cleanup()
                _, event = flow.messages.get(timeout=2); flow.setup_result(*event)
                forget.assert_called_once_with({'linux_profile': 'ZmalaCall-test-one', 'linux_uuid': 'one'}, 'test')
            self.assertEqual(Enrollment(directory).value, {'version': 1})

    def test_blocked_photo_does_not_delay_configuration_and_partial_cache_is_repaired(self):
        with tempfile.TemporaryDirectory() as directory:
            image = png(); name = '/photos/' + hashlib.sha256(image).hexdigest() + '.png'
            value = config(); value['contacts'][0]['photo'] = name
            path = Path(directory) / name.lstrip('/'); path.parent.mkdir(); path.write_bytes(image[:30])
            started, release = threading.Event(), threading.Event()
            def request(route):
                if route.startswith('/api/config'):
                    return json.dumps(value).encode()
                started.set(); release.wait(2); return image
            configuration = Configuration({'device_id': 'test'}, Path(directory) / 'cache.json')
            configuration.request = request
            configuration.photos = PhotoCache(directory, request)
            try:
                self.assertEqual(configuration.fetch()['configuration_version'], 1)
                self.assertTrue(started.wait(1))
                self.assertFalse(path.exists(), 'Partial cache must not be considered usable')
                self.assertEqual(configuration.fetch()['configuration_version'], 1)
                release.set()
                self.assertEqual(configuration.photos.completed.get(timeout=2), name)
                self.assertEqual(path.read_bytes(), image)
                self.assertFalse(valid_photo(image[:-1], name))
                self.assertFalse(valid_photo(image, '/photos/' + '0' * 64 + '.png'))
            finally:
                release.set(); configuration.deactivate(); configuration.photos.worker.join(2)

    def test_cancelled_photo_download_cannot_publish(self):
        with tempfile.TemporaryDirectory() as directory:
            started, release = threading.Event(), threading.Event()
            def request(_route):
                started.set(); release.wait(2); return png()
            cache = PhotoCache(directory, request)
            cache.schedule([{'photo': '/photos/abcd.png'}])
            self.assertTrue(started.wait(1))
            cache.close(); release.set(); cache.worker.join(2)
            self.assertFalse((Path(directory) / 'photos/abcd.png').exists())
            self.assertFalse(list(Path(directory).rglob('*.tmp')))

    def test_volume_worker_coalesces_changes_and_does_not_block_caller(self):
        from platforms import c20_volume
        started, release = threading.Event(), threading.Event()
        applied = []
        def apply(value):
            applied.append(value)
            if value == 10:
                started.set(); release.wait(2)
            return True
        with patch.multiple(c20_volume, _desired=None, _applied=None, _worker=None), patch.object(c20_volume, 'apply', apply):
            try:
                c20_volume.request(10); self.assertTrue(started.wait(1))
                worker = c20_volume._worker
                c20_volume.request(20); c20_volume.request(30)
                release.set(); worker.join(2)
                self.assertEqual(applied, [10, 30])
                c20_volume.request(30)
                self.assertIsNone(c20_volume._worker)
            finally:
                release.set()
                if c20_volume._worker:
                    c20_volume._worker.join(2)
