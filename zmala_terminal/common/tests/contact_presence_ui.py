"""Native canvas visibility and call guards, without placing a real SIP call."""
import copy
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT.parent))
from zmala_terminal.common import main as main
from zmala_terminal.common.configuration import Configuration
from zmala_terminal.common.localization import LANGUAGES, font_family
from zmala_terminal.common.model import State


class QuietEngine:
    registered, core, call = True, None, None

    def __init__(self, config, *args, **kwargs):
        self.config, self.dialed = config, []

    def dial(self, uri):
        self.dialed.append(uri)

    def iterate(self):
        pass

    def diagnostics(self):
        return {}

    def core_refresh_registers(self, *args):
        pass

    def end(self, **kwargs):
        pass

    def close(self):
        pass


class QuietMaintenance:
    def __init__(self, *args, **kwargs):
        pass

    def stop(self):
        pass


main.Engine, main.MaintenanceAgent = QuietEngine, QuietMaintenance
app = main.Terminal(profile='presence-ui')
app.poll = lambda: None
base = Configuration().fetch()
base['contacts'] = [c for c in base['contacts'] if c['can_call']][:3]
assert len(base['contacts']) == 3
for index, contact in enumerate(base['contacts']):
    contact['online'] = index != 1
app.apply_config(base)
app.server_seen = time.monotonic()
app.root.geometry('900x620')
app.root.update()


def pump():
    deadline = time.monotonic() + 2
    while app.model.state == State.CALLING and not app.engine.dialed and time.monotonic() < deadline:
        app.tick()
        app.root.update()
        time.sleep(.01)


try:
    for code in LANGUAGES:
        app.language = code
        app.font_family = font_family(code, app.available_fonts)
        app.render()
        app.root.update_idletasks()
        assert len(app.avatar.find_withtag('contact-online')) == 2, code
        assert len(app.avatar.find_withtag('contact-offline')) == 1, code
        for item in (*app.avatar.find_withtag('contact-online'), *app.avatar.find_withtag('contact-offline')):
            x1, y1, x2, y2 = app.avatar.coords(item)
            assert 0 <= x1 < x2 <= app.avatar.winfo_width(), (code, 'horizontal', x1, x2)
            assert 0 <= y1 < y2 <= app.avatar.winfo_height(), (code, 'vertical', y1, y2)
    app.language = 'en'
    app.model.index = 1
    app.press('green')
    assert app.model.state == State.CONFIRM_CALLBACK and not app.engine.dialed
    app.press('red')
    app.model.index = 0
    app.server_seen = time.monotonic()
    app.configuration.request = lambda *args: json.dumps({'id': app.model.contact['id'], 'online': False, 'can_call': True}).encode()
    app.press('green')
    assert app.model.state == State.CONFIRMING and not app.engine.dialed
    app.press('green')
    pump()
    assert app.model.state == State.HOME and not app.engine.dialed, 'A stale online contact started a SIP call'
    # A presence change updates the canvas without a configuration version bump.
    fresh = copy.deepcopy(base)
    fresh['contacts'][0]['online'] = True
    fresh['contacts'][1]['online'] = True
    app.messages.put(('poll-config', (app.generation, fresh)))
    app.tick()
    assert len(app.avatar.find_withtag('contact-online')) == 3
    app.configuration.request = lambda *args: json.dumps({'id': app.model.contact['id'], 'online': True, 'can_call': True}).encode()
    app.server_seen = time.monotonic()
    app.press('green')
    app.press('green')
    pump()
    assert app.engine.dialed == [app.model.contact['sip_uri']]
    app.engine.dialed.clear()
    app.model.ended()
    app.dial_serial += 1
    app.dial_ready(app.generation, app.dial_serial - 1, base['contacts'][0], True)
    assert not app.engine.dialed, 'A cancelled preflight started a call'
    app.server_seen = time.monotonic() - 7
    app.render()
    assert len(app.avatar.find_withtag('contact-offline')) == 3
    app.press('green')
    assert app.model.state == State.CONFIRM_CALLBACK and not app.engine.dialed
    app.press('red')
    print('95-language status bands fit the native carousel; offline, unknown/stale presence, fresh preflight and cancellation guards passed.')
finally:
    app.close()
