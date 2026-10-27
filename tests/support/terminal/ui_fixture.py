"""Real Tk/controllers with disposable state and explicitly substituted hardware."""
from contextlib import contextmanager
from pathlib import Path
import tempfile
import gc
import tkinter as tk
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch

from zmala_terminal.common import main
from zmala_terminal.common.missed_calls import MissedCallsStore
from zmala_terminal.common.volume_control import VolumeControl


def configuration():
    return {
        'schema_version': 1, 'configuration_version': 1, 'device_id': 'trace-fixture',
        'call_auth_key': 'trace-fixture-secret', 'display_name': 'Test terminal',
        'language': 'en', 'auto_answer': False, 'auto_answer_seconds': 30,
        'video_resolution': '720p', 'video_fps': 15, 'c20_speaker_volume': 50,
        'sip': {'username': 'terminal', 'password': 'fixture-password',
                'domain': 'family.test', 'proxy': 'sip:family.test'},
        'contacts': [dict(id=name, name=name.title(), sip_uri=f'sip:{name}@family.test',
                          can_call=True, can_receive=True, auto_answer=False, online=True)
                     for name in ('alice', 'bob', 'carol')], 'callbacks': [],
    }


class FixtureTerminal(main.Terminal):
    def __init__(self, directory):
        self.test_directory = directory
        super().__init__(profile='trace-fixture')

    def initialize_state(self, profile, wifi_mode):
        with patch.object(main, 'ROOT', self.test_directory):
            super().initialize_state(profile, wifi_mode)

    def restore_enrollment(self, bootstrap, unconfigured):
        self.setup_stage = None

    def bind_inputs(self):
        self.presenter_input = SimpleNamespace(connected=True, status='connected',
            battery=75, charger_connected=False, close=lambda: None)
        self.volume_control = VolumeControl(self.root, lambda: True, self.volume_activity)

    def start_services(self):
        pass

    def needs_pairing(self):
        return False

    def make_engine(self, config):
        engine = Mock()
        engine.config = config
        engine.registered, engine.call, engine.core = True, None, 1
        engine.video_settings = SimpleNamespace(resolution=config.get('video_resolution', '720p'),
                                               fps=config.get('video_fps', 15))
        engine.audio_profile = 'normal'
        engine.diagnostics.return_value = {'registered': True, 'camera': 'Fixture C20'}
        engine.incoming_video_active.return_value = True
        engine.hold_call.side_effect = lambda call: setattr(engine, 'call', call)
        engine.end.side_effect = lambda **kwargs: setattr(engine, 'call', None)
        return engine


def pump(app, predicate=lambda: True, timeout=3):
    deadline = time.monotonic() + timeout
    while True:
        app.drain_messages()
        app.root.update()
        if predicate():
            return
        if time.monotonic() >= deadline:
            raise AssertionError('Terminal did not reach the expected state')
        time.sleep(.005)


@contextmanager
def terminal_fixture():
    with tempfile.TemporaryDirectory(prefix='zmala-ui-rbt-') as directory, \
            patch.dict('os.environ', {'ZMALA_USB_POWER': '0', 'ZMALA_ARGON_ONE_FAN': '0'}), \
            patch('zmala_terminal.linux.action_sounds.ActionSounds'):
        # State is redirected before controllers are built. Assets still come from source.
        app = FixtureTerminal(Path(directory))
        app.root.geometry('1280x720')
        app.tv_control.close()
        app.tv_control = Mock()
        app.tv_control.handle_button.return_value = False
        app.tv_control.ready.return_value = True
        app.missed_calls_store = MissedCallsStore(Path(directory)/'notifications.json')
        app.apply_config(configuration())
        app.server_seen = time.monotonic()
        app.network_connected = True
        app.render()
        pump(app)
        try:
            yield app, Path(directory)
        finally:
            # Multiple Tk interpreters share the event loop in this test process.
            # Cancel queued callbacks before destroying their Tcl commands.
            for identifier in app.root.tk.call('after', 'info'):
                app.root.after_cancel(identifier)
            app.close()
            # A following test may allocate on a network worker and trigger cyclic
            # GC there. Release every fixture-owned Tk interpreter/image reference
            # here on the UI thread, even while the caller still holds `app`.
            app.current_text_images.clear()
            app.icon_renderer.cache.clear()
            owners = (app, app.text_renderer, app.volume_control, app.presenter_input,
                      app.tv_control, app.tv_check)
            for owner in owners:
                if owner is None:
                    continue
                for name, value in list(vars(owner).items()):
                    if isinstance(value, (tk.Misc, tk.Image)):
                        setattr(owner, name, None)
            gc.collect()
