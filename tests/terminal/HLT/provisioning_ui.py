# @test T-HLT-010
# @requirements HLR-TERM-SETUP-002
# @environment display
# @plan Connect the real setup controller and UI to an isolated HTTP service; scan valid/invalid enrollment payloads, resize views and assert errors, canonical enrollment and camera cleanup.
# @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

"""Isolated setup/reset UI and real outbound maintenance polling integration."""
import json
from pathlib import Path
import sys
import time
import urllib.request
from unittest.mock import patch
from types import SimpleNamespace
ROOT = (Path(__file__).resolve().parents[3] / 'zmala_terminal')
sys.path.insert(0, str(ROOT.parent))
from zmala_terminal.common import main as main
from zmala_terminal.common.localization import LANGUAGES, font_family
from zmala_terminal.common.local_settings import FIELDS
from zmala_terminal.common.model import State

from tests.support.terminal.http_fixture import http_server_fixture

with http_server_fixture() as server:
    base, admin = f"http://127.0.0.1:{server['http_port']}", server['admin_token']
    account = 'qa-onboarding'


    def api(route, method='GET', value=None):
        request = urllib.request.Request(base+route, method=method, data=json.dumps(value).encode() if value is not None else None,
                                         headers={'Authorization': 'Bearer '+admin, 'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.load(response)


    class QuietEngine:
        registered, core, call = True, None, None

        def __init__(self, config, *args, **kwargs):
            self.config = config
            self.video_settings = SimpleNamespace(resolution=config.get("video_resolution", "720p"))
            self.audio_profile = config.get("audio_profile", "normal")

        def apply_settings(self, settings):
            pass

        def apply_speaker_volume(self):
            pass

        def diagnostics(self):
            return {}

        def core_refresh_registers(self, *args):
            pass

        def iterate(self):
            pass

        def close(self):
            pass

        def end(self, **kwargs):
            pass


    class QuietScanner:
        def __init__(self, *args, **kwargs):
            pass

        def iterate(self):
            pass

        def close(self):
            pass


    main.Engine, main.QRScanner = QuietEngine, QuietScanner
    created, app = False, None
    try:
        api('/api/users', 'POST', {'id': account, 'name': 'Onboarding verification', 'type': 'terminal', 'emails': ['onboarding@example.test']})
        created = True
        bootstrap = api('/api/terminal-bootstrap?id='+account)
        bootstrap['server_url'] = base  # The isolated service listens on loopback only.
        app = main.Terminal(profile='onboard-verification', unconfigured=True)

        def wait(condition, seconds=10):
            deadline = time.monotonic()+seconds
            while not condition() and time.monotonic()<deadline:
                app.root.update()
                time.sleep(.02)
            assert condition(), 'Setup/maintenance operation did not finish'

        assert app.title.cget('text') == 'wifi QR code ?'
        # Stable preview must not receive a background-erasing configure call on
        # every 20 ms tick while the native camera renderer draws into it.
        with patch.object(app.root, 'after', return_value=None), patch.object(app.video, 'configure', wraps=app.video.configure) as repaint:
            for _ in range(50):
                app.tick()
            assert repaint.call_count == 1, 'Stable camera frame is being repainted continuously'
        app.qr_found('not a wifi code')
        assert app.setup_stage == 'wifi' and not app.setup_busy
        app.qr_found('WIFI:T:WPA;S:Test;P:test12345;;')
        wait(lambda: app.setup_stage == 'wifi_ready')
        assert app.scanner is None and app.setup_continue_at - time.monotonic() > 9.5
        assert app.title.cget('text') == app.text('wifi_connected')
        assert app.name.cget('text') == app.text('server_qr_next')
        assert not app.video.winfo_ismapped(), 'Camera preview must be hidden during confirmation'
        app.qr_found(json.dumps({'type': 'family-call-server', 'version': 1, **bootstrap}))
        assert app.setup_stage == 'wifi_ready' and not app.setup_busy and app.configuration is None, 'Server QR bypassed the confirmation pause'
        app.root.geometry('900x620')
        app.root.update_idletasks()
        for code in LANGUAGES:
            app.language = code
            app.font_family = font_family(code, app.available_fonts)
            app.render()
            app.root.update_idletasks()
            assert app.title.winfo_height() < 180 and app.name.winfo_height() < 180, (code, app.title.winfo_height(), app.name.winfo_height())
        app.language = 'en'
        app.font_family = font_family('en', app.available_fonts)
        wait(lambda: app.setup_stage == 'server', 12)
        assert app.scanner is not None and app.setup_continue_at is None
        assert app.title.cget('text') == 'server QR code?'
        app.qr_found(json.dumps({'type': 'family-call-server', 'version': 1, **bootstrap}))
        wait(lambda: app.setup_stage is None)
        assert app.model.config['sip']['username'] == account and app.engine

        route = '/api/terminals/'+account+'/console'
        command = api(route, 'POST', {'command': ("Write-Output 'ZmalaCall maintenance verified'" if sys.platform == 'win32' else "printf 'ZmalaCall maintenance verified\n'"), 'timeout_seconds': 5})
        result = []
        def completed():
            jobs = api(route)['jobs']
            match = next((j for j in jobs if j['id']==command['id']), None)
            if match and match['status'] not in ('queued', 'running'):
                result.append(match)
                return True
            return False
        wait(completed, 12)
        assert result[-1]['status']=='completed' and result[-1]['exit_code']==0, result[-1]
        assert 'ZmalaCall maintenance verified' in result[-1]['stdout']

        # Calls cannot start settings access; repeated key-downs preserve one hold.
        for i in range(10):
            # Cancelling an availability check can return immediately to HOME.
            # Keep each tested press in a call state to verify idle-only counting.
            app.model.state = State.CALLING
            app.press('red')
        assert app.setup_stage is None
        app.model.ended()
        # This isolated setup account has no contacts; seed persisted reset state.
        app.model.missed_calls.add('reset-caller')
        app.missed_calls_store.save(app.model.config, app.model.missed_calls)
        assert app.missed_calls_store.path.exists()
        for i in range(15):
            app.keypress('red')
        assert app.setup_stage is None and app.settings_hold.started is not None
        app.tick_settings_access(app.settings_hold.started+10)
        app.keyrelease('red')
        assert app.settings_open and app.setup_stage is None
        app.settings_draft.row = FIELDS.index('reset')
        app.press('green')
        assert app.setup_stage=='reset'

        # Confirmation fits every language at the minimum terminal window size.
        app.root.geometry('900x620')
        app.root.update()
        for code in LANGUAGES:
            app.language = code
            app.font_family = font_family(code, app.available_fonts)
            app.render()
            app.root.update_idletasks()
            assert app.title.winfo_height()<180, code
        app.press('red')
        assert app.setup_stage is None and app.model.config
        assert app.settings_open and app.settings_draft.key == 'reset'
        app.press('green')  # Open reset again.
        app.press('green')  # Confirm only in this isolated test profile.
        assert app.setup_stage=='wifi' and app.title.cget('text')=='wifi QR code ?'
        assert app.engine is None and app.configuration is None and app.maintenance is None
        assert not app.cache_path.exists()
        assert not app.missed_calls_store.path.exists() and not app.model.missed_calls
        assert app.enrollment.value == {'version': 1, 'language': app.language}
        assert not any(child.winfo_class() in ('Button','TButton') for parent in [app.root,app.home,app.body] for child in parent.winfo_children())
        app.close()
        app = main.Terminal(profile='onboard-verification')
        assert app.setup_stage == 'wifi', 'Reset did not survive reopening with a legacy bootstrap present'
        print('Stable camera repaint, 10-second Wi-Fi confirmation, 95 confirmation/reset translations, QR setup, console, idle-only gesture and persistent reset passed.')
    finally:
        if app:
            app.close()
        if created:
            api('/api/users/'+account, 'DELETE')
