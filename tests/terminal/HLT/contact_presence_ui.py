# @test T-HLT-005
# @requirements HLR-TERM-NAV-001, HLR-TERM-UI-012
# @environment display
# @plan Render real Tk/Linux text with a disposable profile and substituted hardware. Check complete status-label and symbol bounds, their separation and enclosing frames in 95 languages at three/five-card display sizes and during French carousel motion. Check full French labels at 720p, presence colours, stable selection, stale-preflight rejection and cancellation without placing SIP calls.
# Check that settled short selected names use larger bold type than neighbours, and that short/long names remain above availability inside their cards at every display size and during movement.
# @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

"""Native canvas visibility and call guards, without placing a real SIP call."""
import copy
import json
from pathlib import Path
import sys
import time
from unittest.mock import Mock

ROOT = (Path(__file__).resolve().parents[3] / 'zmala_terminal')
sys.path.insert(0, str(ROOT.parent))
from zmala_terminal.common.localization import LANGUAGES, font_family
from zmala_terminal.common.model import State


from tests.support.terminal.ui_fixture import terminal_fixture, configuration
from zmala_terminal.common.carousel import CarouselMotion

fixture = terminal_fixture()
app, _ = fixture.__enter__()
app.poll = lambda: None
rendered_labels = {}
rendered_fonts = {}
original_photo = app.text_renderer.photo
def recorded_photo(text, *args, **kwargs):
    image = original_photo(text, *args, **kwargs)
    rendered_labels[str(image)] = text
    rendered_fonts[str(image)] = (args[1], args[5] if len(args) > 5 else False)
    return image
app.text_renderer.photo = recorded_photo
app.engine.dialed = []
app.engine.dial.side_effect = app.engine.dialed.append
base = configuration()
for index, contact in enumerate(base['contacts']):
    contact['online'] = index != 1
    contact['presence'] = ('available', 'offline', 'push')[index]
app.apply_config(base)
app.server_seen = time.monotonic()


def assert_status_bounds(code, moving=False):
    bands = [app.avatar.coords(item) for tag in ('contact-online', 'contact-offline')
             for item in app.avatar.find_withtag(tag)]
    for label, symbol in zip(app.avatar.find_withtag('contact-status-label'),
                             app.avatar.find_withtag('contact-status-symbol')):
        text_box, icon_box = app.avatar.bbox(label), app.avatar.bbox(symbol)
        x, y = app.avatar.coords(label)
        enclosing = [band for band in bands if band[0] < x < band[2] and band[1] < y < band[3]]
        assert len(enclosing) == 1, (code, 'status owner', text_box, enclosing)
        left, top, right, bottom = enclosing[0]
        for box in (text_box, icon_box):
            assert left <= box[0] < box[2] <= right, (code, 'horizontal content', box, enclosing)
            assert top <= box[1] < box[3] <= bottom, (code, 'vertical content', box, enclosing)
        assert icon_box[2]+3 <= text_box[0], (code, 'icon overlaps text', icon_box, text_box)
        if not moving:  # Entering/leaving cards intentionally cross the canvas edge.
            assert 0 <= left < right <= app.avatar.winfo_width(), (code, 'screen width', enclosing)
        assert 0 <= top < bottom <= app.avatar.winfo_height(), (code, 'screen height', enclosing)
    cards = [app.avatar.coords(item) for item in app.avatar.find_withtag('contact-card')]
    for item in app.avatar.find_withtag('contact-name'):
        box = app.avatar.bbox(item)
        x, y = app.avatar.coords(item)
        owner = [card for card in cards if card[0] < x < card[2] and card[1] < y < card[3]]
        assert len(owner) == 1, (code, 'name owner', box, owner)
        left, top, right, bottom = owner[0]
        assert left <= box[0] < box[2] <= right, (code, 'name width', box, owner)
        status_top = next(band[1] for band in bands if band[0] < x < band[2])
        assert top <= box[1] < box[3] <= status_top, (code, 'name above status', box, owner)
    if not moving:
        items = app.avatar.find_withtag('contact-name-'+app.model.selected['id'])
        selected = rendered_fonts[app.avatar.itemcget(items[0], 'image')]
        others = [rendered_fonts[app.avatar.itemcget(i, 'image')] for i in app.avatar.find_withtag('contact-name') if i != items[0]]
        assert selected[1] and all(not bold for size, bold in others), (code, 'selected bold', selected, others)
        if len(app.model.selected['name']) <= 8:
            assert all(selected[0] > size for size, bold in others), (code, 'selected size', selected, others)


def pump():
    deadline = time.monotonic() + 2
    while app.model.state == State.CALLING and not app.engine.dialed and time.monotonic() < deadline:
        app.tick()
        app.root.update()
        time.sleep(.01)


try:
    for width, height, portraits in ((900, 620, 3), (1280, 720, 5), (1920, 1080, 5)):
        app.root.geometry(f'{width}x{height}')
        fixture_config = copy.deepcopy(base)
        if portraits == 5:
            fixture_config['contacts'] += [dict(fixture_config['contacts'][index], id='extra'+str(index)) for index in (0, 2)]
        fixture_config['carousel_portraits'] = portraits
        app.apply_config(fixture_config)
        app.root.update()
        for code in LANGUAGES:
            app.language = code
            app.font_family = font_family(code, app.available_fonts)
            app.server_seen = time.monotonic()
            app.render()
            app.root.update_idletasks()
            for state in ('available', 'push', 'offline'):
                assert app.avatar.find_withtag('presence-'+state), (code, state)
            assert_status_bounds(code)
        original_names = [person['name'] for person in app.model.contacts]
        for person in app.model.contacts:
            person['name'] = 'Kristell & Antoine Éléonore Madeleine Alexandra'
        app.render()
        app.root.update_idletasks()
        assert_status_bounds('long names')
        for person, name in zip(app.model.contacts, original_names):
            person['name'] = name
        app.language = 'fr'
        app.font_family = font_family('fr', app.available_fonts)
        for index in range(3):
            app.model.index = index
            app.carousel_motion = None
            app.render()
            app.root.update_idletasks()
            assert_status_bounds('fr selected '+str(index))
            # At the supported TV size, every French status is displayed in full.
            if width >= 1280:
                for item in app.avatar.find_withtag('contact-status-label'):
                    image_name = app.avatar.itemcget(item, 'image')
                    rendered = rendered_labels[image_name]
                    assert '…' not in rendered, ('French label truncated', rendered)
        app.carousel_motion = CarouselMotion(app.model.contacts, 0, 1, time.monotonic())
        for progress in (.05, .25, .5, .75, .95):
            app.carousel_motion.started = time.monotonic()-app.carousel_motion.duration*progress
            app.draw_avatar(app.model.selected)
            app.root.update_idletasks()
            assert_status_bounds('fr moving '+str(progress), moving=True)
        app.carousel_motion = None
    app.apply_config(base)
    app.root.update()
    app.configuration = Mock()  # Only preflight responses are substituted below.
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
    fresh['contacts'][1]['presence'] = 'available'
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
    print('95-language text/icon bounds, full French status labels, three/five cards, animation and presence/call guards passed.')
finally:
    fixture.__exit__(None, None, None)
