# @test T-LLT-009
# @requirements LLR-TERM-HISTORY-021, LLR-TERM-HISTORY-022, LLR-TERM-HISTORY-023
# @environment portable
# @plan Drive the model and management controller with pending, completed and stale callback results; assert one confirmed request, cancellable tags, failure retention and protection against stale poll resurrection.
# @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

"""Callback tags and cancellation retain server ownership and late-result guards."""
import copy
import json
from pathlib import Path
import queue
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from zmala_terminal.common.model import State, TerminalModel
from zmala_terminal.common.management import ManagementLoop
from zmala_terminal.common.call_control import CallControl
from tests.terminal.LLT.test_terminal import config


class CallbackTests(unittest.TestCase):
    def model(self):
        model = TerminalModel()
        model.configure(config())
        self.request = {'id': '11111111-1111-1111-1111-111111111111',
                        'from': model.config['sip']['username'], 'to': 'alice',
                        'status': 'pending', 'ready': False}
        model.config['callbacks'] = [dict(self.request)]
        return model

    def loop(self):
        loop = ManagementLoop()
        loop.model = self.model()
        loop.callback_requests = list(loop.model.config['callbacks'])
        loop.generation = 1
        loop.callback_serial = 3
        loop.render = Mock()
        loop.setup_stage = None
        return loop

    def test_only_pending_outgoing_requests_have_cancellable_tags(self):
        model = self.model()
        self.assertEqual(model.pending_callback(model.selected)['id'], self.request['id'])
        for request in [dict(self.request, status='cancelled'),
                        dict(self.request, status='completed'),
                        dict(self.request, to=self.request['from'], **{'from': 'alice'})]:
            model.config['callbacks'] = [request]
            self.assertIsNone(model.pending_callback(model.selected))

    def test_red_opens_cancellation_even_when_contact_online_and_green_still_calls(self):
        model = self.model()
        model.button('green')
        self.assertEqual(model.state, State.CONFIRMING)
        model.ended()
        model.button('red')
        self.assertEqual(model.state, State.CONFIRM_CALLBACK)
        self.assertEqual(model.callback_request['id'], self.request['id'])
        model.button('red')
        self.assertEqual(model.state, State.HOME)
        self.assertIsNotNone(model.pending_callback(model.selected))
        model.button('red')
        self.assertEqual(model.button('green'), 'cancel_callback')
        self.assertIsNone(model.button('green'))

    def test_offline_pending_request_cannot_be_duplicated_or_replaced_during_confirmation(self):
        model = self.model()
        model.config['contacts'][0]['online'] = False
        model.button('green')
        # Expiry/poll changes cannot turn a cancellation confirmation into creation.
        model.config['callbacks'] = []
        self.assertEqual(model.button('green'), 'cancel_callback')
        self.assertEqual(model.callback_request['id'], self.request['id'])

    def test_failure_preserves_tag_and_success_removes_it(self):
        loop = self.loop()
        loop.model.button('red'); loop.model.button('green')
        loop.callback_result(1, 3, 'alice', False, None, self.request['id'])
        self.assertIsNotNone(loop.model.pending_callback(loop.model.selected))
        self.assertEqual(loop.notice, 'help')
        loop.model.button('red'); loop.model.button('green')
        loop.callback_result(1, 3, 'alice', True, {'ok': True}, self.request['id'])
        self.assertIsNone(loop.model.pending_callback(loop.model.selected))
        self.assertEqual(loop.callback_requests, [])
        self.assertEqual(loop.notice, '')

    def test_old_poll_cannot_resurrect_cancelled_tag_but_fresh_poll_is_authoritative(self):
        loop = self.loop()
        before = copy.deepcopy(loop.model.config)
        loop.callback_result(1, 3, 'alice', True, {'ok': True}, self.request['id'])
        loop.handle_worker_message('poll-config', (1, before, 0))
        self.assertIsNone(loop.model.pending_callback(loop.model.selected))
        loop.handle_worker_message('poll-config', (1, before, 1))
        self.assertIsNotNone(loop.model.pending_callback(loop.model.selected))

    def test_create_result_updates_tag_after_navigation_without_interrupting_incoming_call(self):
        loop = self.loop()
        loop.callback_requests = []; loop.model.config['callbacks'] = []
        loop.model.incoming('alice', 'family.test')
        loop.callback_result(1, 3, 'alice', True, self.request, None)
        self.assertEqual(loop.model.state, State.RINGING)
        self.assertIsNotNone(loop.model.pending_callback(loop.model.selected))
        loop.render.assert_not_called()
        loop.callback_result(0, 3, 'alice', True, {'ok': True}, self.request['id'])
        self.assertIsNotNone(loop.model.pending_callback(loop.model.selected))

    def test_poll_removes_expired_tag_without_configuration_version_change(self):
        loop = self.loop()
        update = copy.deepcopy(loop.model.config)
        update['callbacks'] = []
        loop.apply_poll_config(update)
        self.assertIsNone(loop.model.pending_callback(loop.model.selected))
        loop.render.assert_called_once()

    def test_cancel_worker_posts_specific_request_even_without_sip_engine(self):
        app = CallControl()
        app.model = self.model()
        app.model.button('red'); app.model.button('green')
        app.engine = None
        app.configuration = Mock()
        app.configuration.request.return_value = json.dumps({'ok': True})
        app.callback_serial = 2; app.generation = 1; app.messages = queue.Queue()
        with patch('zmala_terminal.common.call_control.threading.Thread') as thread:
            app.action('cancel_callback')
            thread.call_args.kwargs['target']()
        app.configuration.request.assert_called_once_with('/api/callbacks/'+self.request['id']+'/cancel', {})
        kind, result = app.messages.get_nowait()
        self.assertEqual(kind, 'callback-result')
        self.assertEqual(result[:4], (1, 3, 'alice', True))
        self.assertEqual(result[-1], self.request['id'])


if __name__ == '__main__':
    unittest.main()
