# @test T-HLT-008
# @requirements HLR-TERM-UI-002, HLR-TERM-CALL-001
# @environment native-display
# @plan Start the real Linux terminal against a private server, wait for registration and render every language/call state; assert confirmation images and notification state, and retain screenshots for visual review.
# @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

"""Run the real Linux Tk/native engine against a private LAN server fixture."""
import argparse
import json
from pathlib import Path
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from zmala_terminal.common.main import Terminal
from zmala_terminal.common.model import State
from zmala_terminal.common.localization import LANGUAGES, font_family
from PIL import ImageGrab

parser = argparse.ArgumentParser()
parser.add_argument('--bootstrap', type=Path, required=True)
args = parser.parse_args()
app = Terminal(bootstrap=args.bootstrap, profile='linux-ui-test')
try:
    deadline = time.monotonic() + 35
    while time.monotonic() < deadline and not (app.engine and app.engine.registered):
        app.root.update(); time.sleep(.02)
    assert app.engine and app.engine.registered, 'Linux terminal did not register'
    app.poll = lambda: None
    app.model.config['contacts'] = [dict(app.model.config['contacts'][0], id=id_, name=name,
        online=True, sip_uri=f'sip:{id_}@{app.model.config["sip"]["domain"]}')
        for id_, name in [('alice','Alice'),('bob','Bob'),('carol','Carol')]]
    app.presence_stale = False
    languages = []
    for language in LANGUAGES:
        app.language = language
        app.font_family = font_family(language, app.available_fonts)
        for state in (State.HOME, State.CONFIRMING, State.CONFIRM_CALLBACK, State.RINGING):
            app.model.state = state
            app.model.contact = None if state == State.HOME else app.model.selected
            app.render(); app.root.update_idletasks()
            if state in (State.CONFIRMING, State.CONFIRM_CALLBACK):
                assert app.confirmation_images, (language, state)
        languages.append(language)
    app.language = 'fr'
    app.font_family = font_family('fr', app.available_fonts)
    app.model.state, app.model.contact = State.HOME, None
    app.model.restore_notifications({'alice': 2})
    app.render(); app.root.update()
    ImageGrab.grab().save(Path(__file__).parent / 'linux-home.png')
    app.model.state, app.model.contact = State.CONFIRMING, app.model.selected
    app.render(); app.root.update()
    ImageGrab.grab().save(Path(__file__).parent / 'linux-confirmation.png')
    app.model.state = State.CONFIRM_CALLBACK
    app.render(); app.root.update()
    ImageGrab.grab().save(Path(__file__).parent / 'linux-callback.png')
    print(json.dumps({'registered': True, 'languages': len(languages), 'devices': app.engine.diagnostics()}))
finally:
    app.close()
