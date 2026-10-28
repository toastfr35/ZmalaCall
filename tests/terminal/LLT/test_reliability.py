# @test T-LLT-044
# @requirements LLR-TERM-COM-003, LLR-TERM-COM-006, LLR-TERM-COM-008, LLR-TERM-CONFIG-023, LLR-TERM-CONFIG-024, LLR-TERM-UI-020, LLR-TERM-UI-021, LLR-TERM-AUDIO-007, LLR-TERM-HISTORY-018, LLR-TERM-MAINT-016, LLR-TERM-MAINT-017
# @environment portable
# @plan Check one-second C20 setup retry versus five-second general failures. Inject failed/stale results into maintenance, configuration, photo and volume controllers with temporary storage and controlled worker threads; assert no command replay, revision/history isolation, resumable cleanup, cancelled/obsolete-photo fencing and removal of queued retired portraits and coalesced mixer writes. Bound the portrait queue and retry delay; exercise the real worker with cached, invalid and cancelled data. Gate reconfiguration during setup/calls and verify bounded authenticated HTTP requests and deactivation.
# @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.
# Authorization rejection (401/403) drops the result without retrying or rerunning the command.

"""Regression coverage for unattended recovery, with no native devices or live server."""
import hashlib
import io
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

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from zmala_terminal.common.configuration import Configuration
from zmala_terminal.common.maintenance import MaintenanceAgent, bounded_output
from zmala_terminal.common.main import Terminal
from zmala_terminal.common.missed_calls import MissedCallsStore
from zmala_terminal.common.model import TerminalModel, State
from zmala_terminal.common.photo_cache import PhotoCache, valid_photo
from zmala_terminal.common.provisioning import Enrollment
from zmala_terminal.common.setup_flow import ProvisioningFlow
from tests.terminal.LLT.test_terminal import config


def png():
    def chunk(kind, payload):
        return struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', zlib.crc32(kind + payload))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)) +
            chunk(b'IDAT', zlib.compress(b'\0\xff\0\0')) + chunk(b'IEND', b''))


class ReliabilityTests(unittest.TestCase):
    def test_http_requests_are_bounded_authenticated_and_json_only_for_writes(self):
        import zmala_terminal.common.configuration as module
        client = Configuration({'device_id':'test', 'device_token':'unit-secret', 'server_url':'http://unit.test'})
        client.opener = Mock()
        client.opener.open.side_effect = lambda *args, **kwargs: io.BytesIO(b'{"ok":true}')
        self.assertEqual(client.request('/api/config'), b'{"ok":true}')
        request = client.opener.open.call_args.args[0]
        self.assertEqual(request.full_url, 'http://unit.test/api/config')
        self.assertEqual(request.get_header('Authorization'), 'Bearer unit-secret')
        self.assertIsNone(request.data)
        self.assertEqual(client.opener.open.call_args.kwargs['timeout'], 4)
        client.report({'registered':True})
        request = client.opener.open.call_args.args[0]
        self.assertEqual(json.loads(request.data), {'registered':True})
        self.assertEqual(request.get_header('Content-type'), 'application/json')
        client.opener.open.side_effect = lambda *args, **kwargs: io.BytesIO(b'x'*(module.MAX_BYTES+1))
        with self.assertRaisesRegex(ValueError, 'too large'):
            client.request('/oversized')
        client.deactivate()
        with self.assertRaisesRegex(RuntimeError, 'reset'):
            client.update_settings({}, {})

    def test_configuration_gates_setup_media_readiness_and_revoked_autoanswer(self):
        from zmala_terminal.common.configuration_control import ConfigurationControl
        app = ConfigurationControl()
        app.setup_stage = 'wifi'; app.render = Mock(); app.begin_tv_setup = Mock(return_value=True)
        app.apply_config(config()); app.begin_tv_setup.assert_not_called()
        app.setup_stage = None; app.tv_setup_checked = False
        app.apply_config(config()); app.render.assert_called_once()
        app.tv_setup_checked = True; app.model = TerminalModel(); app.model.configure(config())
        app.engine = Mock(); app.available_fonts = set(); app.root = Mock(); app.text = lambda key:key
        app.press = Mock(); app.usb_media_ready = Mock(return_value=False); app.engine_retry_at = 0
        app.model.incoming('alice', 'family.test')
        desired = config(); desired['contacts'] = []
        app.apply_config(desired); app.press.assert_called_once_with('red')
        desired = config(); desired['auto_answer'] = False
        app.apply_config(desired); self.assertIsNone(app.model.deadline)
        app.model.ended(); app.apply_config(desired)
        self.assertEqual(app.pending_config, desired)
        app.usb_media_ready.assert_called_once()
        # An existing engine that fails to apply or close remains detached and retryable.
        app.usb_media_ready.return_value = True
        app.configure_engine = Mock(side_effect=RuntimeError('apply failed'))
        failed_engine = app.engine; failed_engine.close.side_effect = OSError('close failed')
        with patch('zmala_terminal.common.configuration_control.logging.exception'), patch('time.monotonic', return_value=100):
            app.apply_config(desired)
        self.assertIsNone(app.engine)
        self.assertEqual(app.engine_retry_at, 105)
        self.assertEqual(app.diagnostics, {'registered':False})
        from zmala_terminal.common.media_errors import MediaNotReady
        app.configure_engine.side_effect = MediaNotReady('C20 waking')
        with patch('time.monotonic', return_value=106):
            app.apply_config(desired)
        self.assertEqual(app.engine_retry_at, 107)
        self.assertEqual(app.pending_config, desired)

    def test_configuration_refresh_updates_devices_without_replacing_same_native_graph(self):
        from zmala_terminal.common.configuration_control import ConfigurationControl
        from zmala_terminal.common.video_settings import VideoSettings
        app = ConfigurationControl(); desired = config()
        app.engine = Mock(audio_profile='normal', config=desired); app.engine.video_settings = VideoSettings.for_config(desired)
        app.current_settings = {}; desired['terminal_settings'] = {'camera':'selected'}
        original = app.engine
        app.configure_engine(desired, desired['sip'], 'normal')
        original.apply_settings.assert_called_once_with({'camera':'selected'})
        original.apply_call_timeout.assert_called_once()
        self.assertIs(app.engine, original)
        app.engine = None; app.make_engine = Mock(return_value=Mock()); app.usb_power = Mock(enabled=True)
        app.configure_engine(desired, None, 'normal')
        app.engine.core_set_ring.assert_called_once_with(app.engine.core, None)

    def test_photo_queue_is_bounded_and_retry_waits_before_requeue(self):
        import zmala_terminal.common.photo_cache as photos
        cache = PhotoCache('unused', Mock())
        with patch.object(photos.threading, 'Thread') as thread, patch.object(photos.time, 'monotonic', return_value=100):
            cache.schedule([{'photo':f'/photos/{i:x}.png'} for i in range(50)])
            self.assertEqual(len(cache.pending), 40)
            self.assertEqual(len(cache.queued), 40)
            thread.return_value.start.assert_called_once()
            cache.schedule([{'photo':f'/photos/{i:x}.png'} for i in range(50)])
            self.assertEqual(len(cache.pending), 40)
            cache.pending.clear(); cache.queued.clear()
            cache.retry['/photos/a.png'] = 160
            cache.schedule([{'photo':'/photos/a.png'}])
            self.assertFalse(cache.pending)
        cache.completed.put('/photos/a.png')
        self.assertTrue(cache.changed())
        self.assertFalse(cache.changed())
        cache.close(); cache.completed.put('/photos/a.png')
        self.assertFalse(cache.changed())
        cache.schedule([{'photo':'/photos/b.png'}]); self.assertFalse(cache.pending)

    def test_failed_photo_download_retries_and_valid_cache_avoids_network(self):
        import zmala_terminal.common.photo_cache as photos
        for valid in (False, True):
            with tempfile.TemporaryDirectory() as directory:
                data = png(); name = '/photos/'+hashlib.sha256(data).hexdigest()+'.png'
                cache = PhotoCache(directory, Mock(return_value=b'invalid'))
                file = Path(directory)/name.lstrip('/'); file.parent.mkdir()
                file.write_bytes(data if valid else b'stale')
                cache.pending.append(name); cache.queued.add(name); cache.wanted.add(name)
                def wait():
                    cache.cancelled = True
                with patch.object(cache.condition, 'wait', side_effect=wait), patch.object(photos.time, 'monotonic', return_value=100):
                    cache.run()
                self.assertFalse(cache.queued)
                self.assertEqual(file.exists(), valid)
                if valid:
                    cache.request.assert_not_called()
                    self.assertIn(name, cache.valid)
                else:
                    cache.request.assert_called_once_with(name)
                    self.assertEqual(cache.retry[name], 160)
                    self.assertNotIn(name, cache.valid)
                self.assertFalse(list(file.parent.glob('*.tmp')))

    def test_replaced_contacts_drop_waiting_photos_and_late_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            started, release = threading.Event(), threading.Event()
            requested = []
            def request(path):
                requested.append(path)
                if path == '/photos/old.png':
                    started.set()
                    self.assertTrue(release.wait(2))
                return png()
            cache = PhotoCache(directory, request)
            try:
                cache.schedule([{'photo': '/photos/old.png'}, {'photo': '/photos/queued.png'}])
                self.assertTrue(started.wait(2))
                cache.schedule([{'photo': '/photos/current.png'}])
                release.set()
                self.assertEqual(cache.completed.get(timeout=2), '/photos/current.png')
                self.assertEqual(requested, ['/photos/old.png', '/photos/current.png'])
                self.assertFalse((Path(directory) / 'photos/old.png').exists())
                self.assertEqual(cache.valid, {'/photos/current.png'})
            finally:
                release.set(); cache.close(); cache.worker.join(2)
            self.assertFalse(list(Path(directory).rglob('*.tmp')))

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
                with patch('zmala_terminal.common.maintenance.run_command', execute):
                    agent.loop()
                self.assertEqual(len(executions), 1)
                self.assertEqual(len(claims), 2)
                self.assertEqual(len(submitted), 2)
                self.assertEqual(submitted[1]['lease'], 'lease')
                if code == 500:
                    self.assertEqual(submitted[0], submitted[1])
                else:
                    self.assertEqual(submitted[1]['status'], 'failed')

    def test_revoked_result_authorization_does_not_retry_a_diagnostic(self):
        for code in (401, 403):
            with self.subTest(code=code):
                agent = MaintenanceAgent.__new__(MaintenanceAgent)
                agent.configuration = Mock()
                agent.configuration.request.side_effect = HTTPError('/result', code, 'revoked', {}, None)
                agent.submit('one', {'lease': 'old-lease', 'status': 'completed'})
                self.assertEqual(agent.configuration.request.call_count, 1)

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
        with patch('zmala_terminal.common.main.Engine', side_effect=[RuntimeError('native initialization failed'), replacement]) as build:
            with patch('zmala_terminal.common.configuration_control.time.monotonic', return_value=100):
                terminal.apply_config(desired)
                self.assertIsNone(terminal.engine)
                self.assertEqual(terminal.model.config['configuration_version'], 1)
                self.assertEqual(terminal.pending_config, desired)
                old.close.assert_called_once()
                terminal.apply_poll_config(desired)
                self.assertEqual(build.call_count, 1, 'Backoff must prevent a poll retry storm')
            with patch('zmala_terminal.common.configuration_control.time.monotonic', return_value=106):
                terminal.apply_poll_config(desired)
            self.assertIs(terminal.engine, replacement)
            self.assertEqual(terminal.model.config['configuration_version'], 2)
            self.assertIsNone(terminal.pending_config)
            self.assertEqual(terminal.notice, '')

    def test_frame_rate_change_waits_for_call_end_and_rebuilds_only_once(self):
        from zmala_terminal.common.video_settings import VideoSettings
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
        replacement = Mock(auto_framing=None, audio_profile='normal', config=desired)
        replacement.video_settings = VideoSettings.for_config(desired)
        with patch('zmala_terminal.common.main.Engine', return_value=replacement) as build:
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
            with patch('zmala_terminal.common.setup_flow.forget_wifi', side_effect=OSError('offline')):
                flow.start_wifi_cleanup()
                _, event = flow.messages.get(timeout=2); flow.setup_result(*event)
            self.assertIn('wifi_cleanup', Enrollment(directory).value)
            with patch('zmala_terminal.common.setup_flow.forget_wifi') as forget:
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
        from zmala_terminal.linux import c20_volume as c20_volume
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
