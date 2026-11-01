# @test T-LLT-023
# @requirements LLR-TERM-AUDIO-005
# @environment portable
# @plan Fail C20 discovery before native call allocation, then restore it. Exercise incoming and outgoing orchestration with a retryable media error, assert a one-second retry, successful recovery and cancellation/generation guards. No receive-only or HDMI fallback is accepted.
# @pass Calls start only after recovery; cancelled or superseded calls never resume.

from zmala_terminal.common.callbacks import CallbackController
from zmala_terminal.common.media_adapter import MediaAdapter
from zmala_terminal.common.engine import media_backend
import unittest
from unittest.mock import Mock, patch
from zmala_terminal.common.engine import Engine
from zmala_terminal.common.call_control import CallControl
from zmala_terminal.common.model import State
from zmala_terminal.common.media_errors import MediaNotReady


class MissingMicrophoneTests(unittest.TestCase):
    def test_missing_c20_blocks_native_answer_and_invite_before_allocation(self):
        e = Engine.__new__(Engine); e.media = MediaAdapter(media_backend())
        e.config = {}  # Valid LAN profile; this case isolates missing C20 readiness.
        e.call = 42
        e.refresh_usb_devices = Mock(side_effect=MediaNotReady('microphone waking'))
        e.address_new = Mock()
        e.core_create_call_params = Mock()
        with patch('zmala_terminal.common.engine.WINDOWS', False):
            for action in (lambda: e.dial('sip:peer@example.test'), e.answer):
                with self.assertRaises(MediaNotReady):
                    action()
            e.address_new.assert_not_called()
            e.core_create_call_params.assert_not_called()
            e.refresh_usb_devices.side_effect = None
            e.prepare_call_media()
        self.assertEqual(e.refresh_usb_devices.call_count, 3)

    def app(self):
        app = CallControl(); app.callbacks = CallbackController()
        app.root, app.engine, app.model, app.render = Mock(), Mock(), Mock(), Mock()
        app.usb_media_ready = Mock(return_value=True)
        app.generation, app.dial_serial, app.closed, app.setup_stage = 1, 2, False, None
        app.engine.call = 42
        app.engine.registered = True
        app.model.state = State.CONNECTING
        return app

    def test_answer_waits_one_second_and_recovers(self):
        app = self.app()
        app.engine.answer.side_effect = [MediaNotReady('waking'), None]
        app.answer_when_ready()
        delay, retry = app.root.after.call_args.args
        self.assertEqual(delay, 1000)
        app.engine.end.assert_not_called()
        retry()
        self.assertEqual(app.engine.answer.call_count, 2)

    def test_answer_retry_ignores_cancellation_replacement_and_shutdown(self):
        for change in ('cancel', 'generation', 'call', 'closed'):
            app = self.app()
            app.engine.answer.side_effect = MediaNotReady('waking')
            app.answer_when_ready()
            retry = app.root.after.call_args.args[1]
            if change == 'cancel': app.model.state = State.HOME
            elif change == 'generation': app.generation += 1
            elif change == 'call': app.engine.call = 99
            else: app.closed = True
            retry()
            self.assertEqual(app.engine.answer.call_count, 1)

    def test_outgoing_waits_then_recovers_unless_cancelled(self):
        for cancel in (False, True):
            app = self.app()
            contact = {'id': 'peer', 'sip_uri': 'sip:peer@example.test'}
            app.model.contacts = [contact]
            app.model.state = State.CALLING
            app.engine.dial.side_effect = [MediaNotReady('waking'), None]
            app.dial_ready(1, 2, contact, True)
            delay, retry = app.root.after.call_args.args
            self.assertEqual(delay, 1000)
            app.model.ended.assert_not_called()
            if cancel: app.dial_serial += 1
            retry()
            self.assertEqual(app.engine.dial.call_count, 1 if cancel else 2)
