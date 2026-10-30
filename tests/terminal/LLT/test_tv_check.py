# @test T-LLT-035
# @requirements LLR-TERM-TV-019, LLR-TERM-TV-020, LLR-TERM-TV-021, LLR-TERM-TV-022, LLR-TERM-TV-023, LLR-TERM-TV-024
# @environment portable
# @plan Run the setup state machine against fake TV responses and saved attempts; assert consent before switching, independent user-confirmed outcomes, alternate-input sequence and restart-safe TV binding. Run queued setup work with controlled threads, late cancellation and failures; verify persisted-state recovery and retry/brand/skip choices.
# @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

"""Isolated tests: no commands reach a real television."""
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from zmala_terminal.common.tv_check import TVCheck
from zmala_terminal.linux.tv_check import CheckTransport
from zmala_terminal.linux.tv_control import TVControl

IDENTITY = {'address': '2.0.0.0', 'display': 'test-edid'}


class CheckTests(unittest.TestCase):
    def test_worker_delivers_one_outcome_and_cancelled_check_ignores_late_results(self):
        import zmala_terminal.common.tv_check as module
        check = TVCheck('unused', Mock())
        check.transport.probe.return_value = IDENTITY
        with patch.object(module.threading, 'Thread') as thread:
            check.start()
            self.assertTrue(check.busy)
            thread.call_args.kwargs['target']()
            self.assertEqual(check.messages.get_nowait(), ('probe', IDENTITY, False))
            check.transport.probe.side_effect = OSError('offline')
            check.start(); thread.call_args.kwargs['target']()
            self.assertEqual(check.messages.get_nowait(), ('probe', None, True))
        self.assertFalse(check.poll())
        check.messages.put(('probe', IDENTITY, False)); check.close()
        self.assertFalse(check.poll())
        self.assertEqual(check.messages.qsize(), 1)

    def test_setup_recovery_navigation_and_completed_summary(self):
        c = self.check
        self.path.write_text('[]')
        self.deliver('probe', IDENTITY)
        self.assertEqual(c.page, 'power_ready')
        c.button('pointer'); self.assertEqual(c.page, 'power_ready')
        c.busy = True; c.button('red'); self.assertEqual(c.page, 'power_ready'); c.busy = False
        c.page = 'retry_power'; c.button('green'); c.launch.assert_called_with('power')
        c.page = 'sony'; c.button('red'); self.assertEqual(c.page, 'retry_source')
        c.page = 'samsung_help'; c.button('red'); self.assertEqual(c.page, 'retry_source')
        self.deliver('discover', [{'host':'192.0.2.1'}, {'host':'192.0.2.2'}])
        c.button('left'); self.assertEqual(c.selection, 1)
        c.button('right'); self.assertEqual(c.selection, 0)
        c.button('red'); self.assertEqual(c.page, 'retry_source')
        self.deliver('pair', None, True); self.assertEqual(c.page, 'retry_source')
        self.deliver('probe', None); self.assertEqual(c.page, 'unavailable')
        c.button('green'); c.launch.assert_called_with('probe')
        self.deliver('probe', None); c.button('red'); self.assertEqual(c.page, 'summary')
        self.assertTrue(c.record['complete'])
        self.assertEqual(c.record['power']['status'], 'skipped')
        c.button('green'); self.assertEqual(c.page, 'done')
        c.page = 'source_ready'; c.button('left'); self.assertEqual(c.page, 'source_ready')

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / 'tv-check.json'
        self.transport = Mock()
        self.check = TVCheck(self.path, self.transport)
        self.check.messages.put(('probe', IDENTITY, False))
        self.check.poll()
        self.check.launch = Mock()

    def deliver(self, operation, result=True, error=False):
        self.check.messages.put((operation, result, error))
        self.check.poll()

    def test_complete_requires_user_confirmations_and_persists_independently(self):
        c = self.check
        self.assertEqual(c.page, 'power_ready')
        c.button('green')
        self.assertEqual(json.loads(self.path.read_text())['power']['status'], 'running')
        self.deliver('power')
        self.assertEqual(c.page, 'power_confirm')
        self.assertFalse(c.record['complete'])
        c.button('green')
        self.assertEqual(c.page, 'source_ready')
        c.button('green')
        self.deliver('source')
        self.assertEqual(c.page, 'source_confirm')
        c.button('green')
        self.assertEqual(c.page, 'summary')
        saved = json.loads(self.path.read_text())
        self.assertTrue(saved['complete'])
        for kind in ('power', 'source'):
            self.assertTrue(saved[kind]['performed'])
            self.assertEqual(saved[kind]['status'], 'passed')
        resumed = TVCheck(self.path, self.transport)
        resumed.messages.put(('probe', IDENTITY, False))
        resumed.poll()
        self.assertEqual(resumed.page, 'done')
        self.transport.confirm_source.assert_called_once()

    def test_skip_not_confused_with_performed_and_failed_remains_failed(self):
        c = self.check
        c.button('red')
        self.assertFalse(c.record['power']['performed'])
        c.button('green')
        self.deliver('source')
        c.button('red')
        self.assertEqual(c.page, 'samsung')
        c.button('red')
        self.assertEqual(c.page, 'sony')
        c.button('green')
        self.assertEqual(c.page, 'sony_help')
        c.button('green')
        c.button('red')
        self.assertEqual(c.page, 'summary')
        self.assertEqual(c.record['source']['status'], 'failed')
        self.assertTrue(c.record['source']['performed'])
        self.transport.confirm_source.assert_not_called()

    def test_failed_network_binding_save_never_records_a_pass(self):
        self.transport.confirm_source.side_effect = OSError('disk full')
        self.check.page = 'source_confirm'
        self.check.button('green')
        self.assertEqual(self.check.page, 'retry_source')
        self.check.button('red')
        self.assertEqual(self.check.record['source']['status'], 'failed')

    def test_changed_tv_never_reuses_previous_network_remote(self):
        self.check.record['network_paired'] = True
        self.check.button('red')
        self.check.button('red')
        resumed = TVCheck(self.path, self.transport)
        resumed.messages.put(('probe', IDENTITY | {'display': 'new-tv'}, False))
        resumed.poll()
        self.transport.resume_network.assert_called_with(False)

    def test_corrupt_state_restarts_with_a_prompt(self):
        self.path.write_text(json.dumps({'version': 1, 'identity': IDENTITY, 'complete': True}))
        resumed = TVCheck(self.path, self.transport)
        resumed.messages.put(('probe', IDENTITY, False))
        resumed.poll()
        self.assertEqual(resumed.page, 'power_ready')

    def test_completed_checks_survive_temporarily_unavailable_tv(self):
        saved = {'version': 1, 'identity': IDENTITY, 'complete': True,
                 'power': {'status': 'passed', 'attempts': 1},
                 'source': {'status': 'passed', 'attempts': 1}}
        self.path.write_text(json.dumps(saved))
        resumed = TVCheck(self.path, self.transport)
        resumed.messages.put(('probe', None, False))
        resumed.poll()
        self.assertEqual(resumed.page, 'done')
        self.assertEqual(resumed.record['identity'], IDENTITY)

    def test_changed_hdmi_port_invalidates_results(self):
        c = self.check
        c.button('red')
        c.button('red')
        resumed = TVCheck(self.path, self.transport)
        resumed.messages.put(('probe', IDENTITY | {'address': '3.0.0.0'}, False))
        resumed.poll()
        self.assertEqual(resumed.page, 'power_ready')
        self.assertFalse(resumed.record['complete'])

    def test_interrupted_attempt_is_not_passed_or_repeated_automatically(self):
        self.check.button('green')
        resumed = TVCheck(self.path, self.transport)
        resumed.messages.put(('probe', IDENTITY, False))
        resumed.poll()
        self.assertEqual(resumed.page, 'power_ready')
        self.assertEqual(resumed.record['power']['status'], 'running')

    def test_disk_failure_prevents_test_and_can_retry(self):
        with patch('zmala_terminal.common.tv_check.save_config', side_effect=OSError):
            self.check.button('green')
        self.assertEqual(self.check.page, 'save_error')
        self.check.launch.assert_not_called()
        self.check.button('green')
        self.check.launch.assert_called_once_with('power')

    def test_busy_and_cancelled_workers_cannot_advance_or_queue_commands(self):
        self.check.busy = True
        for button in ('green', 'red', 'left', 'right'):
            self.check.button(button)
        self.check.launch.assert_not_called()
        self.check.close()
        self.deliver('power')
        self.assertEqual(self.check.page, 'power_ready')

    def test_timeout_is_not_claimed_as_a_completed_source_test(self):
        c = self.check
        c.button('red')
        c.button('green')
        self.deliver('source', False)
        self.assertEqual(c.page, 'source_timeout')
        c.button('green')
        self.assertFalse(c.record['source']['performed'])

    def test_samsung_requires_user_choice_permission_and_successful_test(self):
        c = self.check
        c.page = 'samsung'
        c.button('green')
        self.assertEqual(c.page, 'samsung_help')
        c.button('green')
        c.launch.assert_called_with('discover')
        self.deliver('discover', [{'host': '192.168.1.5', 'name': 'TV A'}, {'host': '192.168.1.6', 'name': 'TV B'}])
        c.button('right')
        c.button('green')
        c.launch.assert_called_with('pair', '192.168.1.6')
        self.deliver('pair')
        self.assertEqual(c.page, 'paired')
        self.transport.confirm_source.assert_not_called()

    def test_skipped_unavailable_is_remembered_until_hardware_changes(self):
        c = TVCheck(self.path, self.transport)
        c.messages.put(('probe', None, False))
        c.poll()
        c.button('red')
        resumed = TVCheck(self.path, self.transport)
        resumed.messages.put(('probe', None, False))
        resumed.poll()
        self.assertEqual(resumed.page, 'done')


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.tv = TVControl()
        self.tv._run = Mock(return_value='pwr-state: standby (1)')
        self.transport = CheckTransport(self.tv)
        self.transport.address = '2.0.0.0'
        self.transport.prepare = Mock()
        self.cancel = Mock()
        self.cancel.is_set.return_value = False
        self.cancel.wait.return_value = False

    def test_power_always_attempts_wake_after_uncertain_standby(self):
        def run(*args):
            if '--standby' in args:
                raise RuntimeError('ack lost')
            return ''
        self.tv._run.side_effect = run
        with self.assertRaises(RuntimeError):
            self.transport.power(self.cancel)
        commands = self.tv._run.call_args_list
        self.assertTrue(any('--image-view-on' in c.args for c in commands))
        self.assertTrue(any('--active-source' in c.args for c in commands))

    def test_source_roundtrip_restores_observed_route_not_a_hardcoded_port(self):
        self.tv._previous_source = Mock(return_value='4.0.0.0')
        self.tv._driver_call = Mock()
        self.transport.source(self.cancel)
        routes = [c.args for c in self.tv._run.call_args_list if '--active-source' in c.args]
        self.assertEqual(routes, [('--active-source', 'phys-addr=2.0.0.0'),
                                  ('--active-source', 'phys-addr=4.0.0.0'),
                                  ('--active-source', 'phys-addr=2.0.0.0')])
        self.assertEqual([c.args[0] for c in self.cancel.wait.call_args_list], [3, 3])

    def test_source_timeout_and_cancel_never_send_commands(self):
        self.tv._previous_source = Mock(return_value=None)
        with patch('zmala_terminal.linux.tv_check.time.monotonic', side_effect=[0, 0, 31]):
            self.assertFalse(self.transport.source(self.cancel))
        self.tv._run.assert_not_called()
        cancelled = threading.Event()
        cancelled.set()
        with self.assertRaises(InterruptedError):
            self.transport.run(cancelled, '--standby')
        self.tv._run.assert_not_called()

    def test_failed_features_are_disabled_independently(self):
        self.tv.power_enabled = False
        self.assertFalse(self.tv._control_allowed(True))
        self.assertTrue(self.tv._control_allowed(False))
        self.tv.power_enabled, self.tv.source_enabled = True, False
        self.assertTrue(self.tv._control_allowed(True))
        self.assertFalse(self.tv._control_allowed(False))
        self.tv.power_enabled = False
        self.assertFalse(self.tv._control_allowed(None))


if __name__ == '__main__':
    unittest.main()
