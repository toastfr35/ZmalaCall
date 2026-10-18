"""Exercise every translation, complex script rendering and carousel motion in our own UI."""
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
    """Keep this display-only check independent of real registrations and devices."""
    registered, core, call = True, None, None

    def __init__(self, config, *args, **kwargs):
        self.config, self.dialed = config, None

    def diagnostics(self):
        return {}

    def core_refresh_registers(self, *args):
        pass

    def iterate(self):
        pass

    def incoming_video_active(self):
        return True

    def dial(self, uri):
        self.dialed = uri

    def end(self, **kwargs):
        pass

    def close(self):
        pass


main.Engine = QuietEngine
class QuietMaintenance:
    def __init__(self, *args, **kwargs):
        pass

    def stop(self):
        pass


main.MaintenanceAgent = QuietMaintenance
app = main.Terminal(profile='languages-ui')
app.poll = lambda: None
base = Configuration().fetch()
for contact in base['contacts']:
    contact['online'] = True
app.configuration.request = lambda *args: json.dumps({'id': app.model.contact['id'], 'online': True, 'can_call': True}).encode('utf-8')
assert all(c['photo'] for c in base['contacts']), 'Test contacts need pictures'
app.apply_config(base)
app.server_seen = time.monotonic()
app.root.geometry('900x620')
app.root.update()
try:
    assert not hasattr(app, 'hint') and not hasattr(app, 'brand'), 'Footer or terminal name is still displayed'
    assert app.connectivity.winfo_width()<=170 and app.connectivity.winfo_height()<=48
    assert all(app.connectivity.type(i) != 'text' for i in app.connectivity.find_all()), 'Network indicator still has captions'
    assert app.connectivity.find_withtag('network-status'), 'Smooth connection graphic is missing'
    checked = []
    for code in LANGUAGES:
        app.language = code
        app.font_family = font_family(code, app.available_fonts)
        for state in [State.HOME,State.CALLING,State.RINGING,State.CONNECTING,State.IN_CALL,State.STOPPING]:
            app.model.state = state
            app.model.contact = None if state == State.HOME else app.model.selected
            app.model.deadline = time.monotonic()+5 if state == State.RINGING else None
            app.render()
            app.root.update_idletasks()
            for name in ['title','name','subtitle','connectivity','avatar','video']:
                w = getattr(app,name)
                if not w.winfo_ismapped():
                    continue
                x,y = w.winfo_rootx()-app.root.winfo_rootx(),w.winfo_rooty()-app.root.winfo_rooty()
                assert x>=0 and y>=0 and x+w.winfo_width()<=app.root.winfo_width()+1 and y+w.winfo_height()<=app.root.winfo_height()+1, (code,state,name,[x,y,w.winfo_width(),w.winfo_height()])
            if state == State.HOME:
                assert app.title.cget('text') == LANGUAGES[code]['messages']['choose']
                assert len(app.current_photos) == 3
            if state == State.RINGING:
                assert len(app.avatar.find_withtag('ring-pulse'))==2 and app.avatar.find_withtag('ring-phone')
                before = app.subtitle.image
                app.model.deadline = time.monotonic()+2
                app.render()
                assert app.subtitle.image != before, 'Countdown image did not refresh'
        checked.append(code)
    app.model.ended()
    app.model.configure(base)
    app.model.contact = app.model.selected
    app.model.state = State.RINGING
    app.render()
    pulse_before = [app.avatar.coords(i) for i in app.avatar.find_withtag('ring-pulse')]
    app.ringing_started -= .4
    app.next_ring_frame = 0  # Advance the throttled animation without relying on render time.
    app.draw_avatar(app.model.contact)
    assert pulse_before != [app.avatar.coords(i) for i in app.avatar.find_withtag('ring-pulse')], 'Ringing glow did not animate'
    app.press('red')
    assert not app.avatar.find_withtag('ring-pulse'), 'Ringing animation did not stop after decline'
    app.model.ended()
    app.language = 'fr'
    app.font_family = font_family('fr', app.available_fonts)
    app.render()
    item_count = len(app.avatar.find_all())
    app.draw_avatar(app.model.selected)
    assert len(app.avatar.find_all()) == item_count, 'Redrawing retained stale canvas items'
    old_index = app.model.index
    app.press('right')
    assert app.carousel_motion and app.model.index==(old_index+1)%len(app.model.contacts)
    first = [app.avatar.coords(item) for item in app.avatar.find_all()]
    app.carousel_motion.started -= .1
    app.draw_avatar(app.model.selected)
    assert first != [app.avatar.coords(item) for item in app.avatar.find_all()], 'Animation did not move'
    app.press('right')
    assert app.model.index == (old_index+1)%len(app.model.contacts), 'Rapid key skipped contacts'
    selected = app.model.selected
    app.server_seen = time.monotonic()  # The quiet engine does not poll live presence.
    app.press('green')
    assert app.model.state == State.CONFIRMING and app.engine.dialed is None
    app.press('green')
    deadline = time.monotonic()+2
    while app.engine.dialed is None and time.monotonic()<deadline:
        app.tick()
        app.root.update()
        time.sleep(.01)
    assert app.carousel_motion is None and app.engine.dialed == selected['sip_uri'], 'Calling during animation chose the wrong person'
    # A new language is immediately visible during an active call.
    app.model.state = State.IN_CALL
    changed = copy.deepcopy(base)
    changed['language'] = 'ja'
    app.apply_config(changed)
    assert app.language == 'ja' and app.root.title().startswith('ZmalaCall')
    (ROOT/'data/languages-ui-result.json').write_text(json.dumps({'languages':checked,'screen_states':6,'animation':True,'ringing_animation':True,'call_during_animation':True,'live_language_change':True,'no_footer_or_terminal_name':True,'small_connectivity_icons':True}))
    print(f'{len(checked)} languages: all six states fit; countdowns, motion, ringing pulse, immediate calling and live language changes passed. Footer/name removed; smaller icons verified.')
finally:
    app.close()
