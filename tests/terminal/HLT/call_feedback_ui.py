# @test T-HLT-002
# @requirements HLR-TERM-CALL-009, HLR-TERM-UI-012, HLR-TERM-VIDEO-001
# @environment hardware
# @plan With a disposable configured server profile and display prepared, Drive the real Tk UI through ringing, answering, stalled video and ending with controlled native feedback; assert visible state and retained widget geometry.
# @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

"""Exercise confirmation input and missing-video layouts without real calls."""
import json
import copy
from pathlib import Path
import sys
import time
from types import SimpleNamespace

ROOT = (Path(__file__).resolve().parents[3] / 'zmala_terminal')
sys.path.insert(0, str(ROOT.parent))
from zmala_terminal.common import main as main
from zmala_terminal.common import theme as theme
from zmala_terminal.common.configuration import Configuration
from zmala_terminal.common.localization import LANGUAGES, font_family
from zmala_terminal.common.model import State


class QuietEngine:
    registered, core, call, video_active = True, None, None, False

    def __init__(self, config, *args, **kwargs):
        self.config, self.dialed = config, []
        self.video_settings = SimpleNamespace(resolution=config.get('video_resolution', '720p'))
        self.audio_profile = config.get('audio_profile', 'normal')

    def incoming_video_active(self):
        return self.video_active

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

    def dial(self, uri):
        self.dialed.append(uri)

    def end(self, **kwargs):
        pass

    def hold_call(self, call):
        self.call = call

    def call_decline(self, *args):
        pass

    def close(self):
        pass


class QuietMaintenance:
    def __init__(self, *args, **kwargs):
        pass

    def stop(self):
        pass


main.Engine, main.MaintenanceAgent = QuietEngine, QuietMaintenance
app = main.Terminal(profile='call-feedback-ui')
app.poll = lambda: None
base = Configuration().fetch()
for contact in base['contacts']:
    contact['online'] = True
app.apply_config(base)
app.server_seen = time.monotonic()
app.root.geometry('900x620')
app.root.update()
app.configuration.request = lambda *args: json.dumps({'id': app.model.contact['id'], 'online': True, 'can_call': True}).encode()

if '--preview' in sys.argv:
    app.root.title('ZmalaCall - Confirmation QA')
    for index, contact in enumerate(app.model.contacts):
        contact['online'] = index == 0
    app.model.contact = dict(app.model.selected)
    app.model.state = State.CONFIRMING
    app.render()
    app.root.after(120000, app.close)
    app.root.mainloop()
    sys.exit(0)

try:
    selected = app.model.selected['id']
    for button in ['left', 'right', 'red', 'cancel']:
        app.press('green')
        app.root.update_idletasks()
        assert app.model.state == State.CONFIRMING and not app.engine.dialed
        assert app.confirmation.winfo_ismapped() and app.confirmation.find_withtag('confirmed-person')
        assert app.confirmation.winfo_width() == app.root.winfo_width()
        assert app.confirmation.winfo_height() == app.root.winfo_height()
        app.press(button)
        assert app.model.state == State.HOME and app.model.selected['id'] == selected
        assert not app.confirmation.winfo_manager() and not app.engine.dialed

    app.press('green')
    app.model.selected['online'] = False
    app.press('green')
    assert app.model.state == State.CONFIRM_CALLBACK and not app.engine.dialed
    app.press('red')
    app.model.selected['online'] = True
    app.press('green')
    app.engine.registered = False
    app.press('green')
    assert app.model.state == State.CONFIRM_CALLBACK and not app.engine.dialed
    app.press('red')
    app.engine.registered = True

    for width, height in [(900, 620), (1366, 1000)]:
        app.root.geometry(f'{width}x{height}')
        app.root.update()
        for state, key in [(State.CONFIRMING, 'call_question'), (State.CONFIRM_CALLBACK, 'callback_question')]:
            app.model.contact = dict(app.model.selected)
            app.model.state = state
            for code in LANGUAGES:
                app.language = code
                app.font_family = font_family(code, app.available_fonts)
                app.render()
                app.root.update_idletasks()
                assert app.confirmation_question == app.text(key, name=app.model.contact['name'])
                assert app.confirmation.find_withtag('confirmed-person')
                tags = ['confirmed-person', 'confirmation-question', 'confirmation-yes', 'confirmation-no']
                if state == State.CONFIRM_CALLBACK:
                    tags.extend(['confirmation-name', 'confirmation-unavailable'])
                    assert app.text('contact_unavailable')
                else:
                    assert not app.confirmation.find_withtag('confirmation-unavailable')
                boxes = {}
                for tag in tags:
                    boxes[tag] = app.confirmation.bbox(tag)
                    x1, y1, x2, y2 = boxes[tag]
                    assert 0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height, (code, key, tag, boxes[tag])
                portrait = boxes['confirmed-person']
                assert portrait[0] >= 24 and portrait[1] >= 24 and portrait[2] <= width-24
                assert portrait[3]+24 <= boxes['confirmation-name' if state == State.CONFIRM_CALLBACK else 'confirmation-question'][1]
                assert boxes['confirmation-question'][3] <= boxes['confirmation-yes'][1]
                assert boxes['confirmation-yes'][2] < boxes['confirmation-no'][0]
                for tag, color in [('confirmation-yes', theme.BUTTON_GREEN), ('confirmation-no', theme.BUTTON_RED)]:
                    button, = app.confirmation.find_withtag(tag+'-button')
                    assert app.confirmation.type(button) == 'image'
                    picture = app.confirmation.itemcget(button, 'image')
                    button_width = int(app.root.tk.call('image', 'width', picture))
                    button_height = int(app.root.tk.call('image', 'height', picture))
                    rgb = lambda value: tuple(int(value[i:i+2], 16) for i in (1, 3, 5))
                    assert app.root.tk.call(picture, 'get', 0, 0) == rgb(theme.BG)
                    assert app.root.tk.call(picture, 'get', button_width//2, button_height//2) == rgb(color)
                    assert boxes[tag][3] <= height-24
                if state == State.CONFIRM_CALLBACK:
                    assert boxes['confirmation-name'][3] <= boxes['confirmation-unavailable'][1]
                    assert boxes['confirmation-unavailable'][3] <= boxes['confirmation-question'][1]
    app.model.state = State.REQUESTING_CALLBACK
    app.render()
    assert not app.confirmation.find_withtag('confirmation-yes')
    assert not app.confirmation.find_withtag('confirmation-no')
    app.root.geometry('900x620')
    app.root.update()
    app.model.ended()
    app.language = 'en'
    app.font_family = font_family('en', app.available_fonts)
    app.server_seen = time.monotonic()
    app.render()

    # Holding green cannot accidentally confirm; a distinct release is needed.
    app.keypress('green')
    app.last_key['green'] -= 1
    app.keypress('green')
    assert app.model.state == State.CONFIRMING and not app.engine.dialed
    app.other_key(SimpleNamespace(keysym='space'))
    app.keys_down.clear()
    assert app.model.state == State.HOME
    app.press('green')
    fullscreen = app.root.attributes('-fullscreen')
    app.toggle_fullscreen(None)
    assert app.model.state == State.HOME and app.root.attributes('-fullscreen') == fullscreen

    app.keypress('green')
    app.keys_down.discard('green')
    app.last_key['green'] -= 1
    app.keypress('green')
    assert app.model.state == State.CALLING
    deadline = time.monotonic() + 2
    while not app.engine.dialed and time.monotonic() < deadline:
        app.root.update()
        time.sleep(.01)
    assert app.engine.dialed == [app.model.contact['sip_uri']]

    app.model.connected()
    for code in LANGUAGES:
        app.language = code
        app.font_family = font_family(code, app.available_fonts)
        app.render()
        app.root.update_idletasks()
        assert app.missing_video.winfo_ismapped() and app.video.winfo_ismapped(), code
        assert app.missing_video_bottom.winfo_ismapped(), code
        assert app.local_video.winfo_ismapped(), code
        assert app.preview_window != app.video_window
        assert app.local_video.winfo_x() >= app.video.winfo_width()*.8-1
        assert app.local_video.winfo_y() >= app.video.winfo_height()*.8-1
        # The no-video notice must leave the native bottom-right self-view visible.
        assert app.missing_video.winfo_height() <= app.video.winfo_height() * .8 + 1
        assert app.missing_video_bottom.winfo_width() <= app.video.winfo_width() * .8 + 1
        for widget in [app.video_message, app.video_reassurance]:
            x = widget.winfo_rootx() - app.video.winfo_rootx()
            y = widget.winfo_rooty() - app.video.winfo_rooty()
            assert 0 <= x and x + widget.winfo_width() <= app.video.winfo_width(), (code, 'width', x, widget.winfo_width(), app.video.winfo_width(), app.root.winfo_width(), app.missing_video.winfo_width())
            assert 0 <= y and y + widget.winfo_height() <= app.video.winfo_height(), (code, 'height')
            assert widget.image, (code, 'text missing')
    app.engine.video_active = True
    app.tick()
    assert not app.missing_video.winfo_manager()
    assert not app.missing_video_bottom.winfo_manager()
    assert app.local_video.winfo_ismapped()
    app.engine.video_active = False
    app.tick()
    assert app.missing_video.winfo_manager() == 'place'
    app.model.ended()
    app.render()
    assert not app.missing_video.winfo_manager()
    assert not app.local_video.winfo_manager()
    app.notice = ''
    app.server_seen = time.monotonic()
    app.last_button = time.monotonic()-6
    person = app.model.selected
    app.callback_requests = [{'id':'b11aeab7-d25f-48a9-b44e-6d1a3d91d299','from':person['id'],'to':app.model.config['sip']['username'],'ready':True}]
    before = list(app.engine.dialed)
    app.model.state = State.CALLING
    app.show_callback_available(time.monotonic())
    assert not app.callback_alert, 'Callback notice interrupted a call'
    app.model.ended()
    app.show_callback_available(time.monotonic())
    assert app.callback_alert and app.model.state == State.HOME and app.engine.dialed == before
    app.callback_alert = None
    app.show_callback_available(time.monotonic())
    assert app.callback_alert is None, 'Same callback notice appeared repeatedly'
    person = app.model.selected
    app.model.config['auto_answer'] = False
    app.model.missed_calls.clear()
    app.call_event(123, 1, person['id'], app.model.config['sip']['domain'])
    app.root.update_idletasks()
    assert app.model.state == State.RINGING
    assert not app.avatar.find_withtag('missed-call')
    app.call_event(123, 14, person['id'], app.model.config['sip']['domain'])
    app.root.update_idletasks()
    assert app.model.state == State.HOME and person['id'] in app.model.missed_calls
    assert app.missed_calls_store.load(app.model.config) == {person['id']}
    for code in LANGUAGES:
        app.language = code
        app.font_family = font_family(code, app.available_fonts)
        app.render()
        app.root.update_idletasks()
        tag = 'missed-call-'+person['id']
        items = app.avatar.find_withtag(tag)
        assert len(items) == 1 and app.avatar.type(items[0]) == 'image', (code, 'badge missing')
        image = app.icon_renderer.missed_call(22, theme.BADGE_RED, theme.BADGE_WHITE)
        assert image.get(image.width()//2, 5) == tuple(int(theme.BADGE_RED[i:i+2],16) for i in (1,3,5))
        assert any(image.get(x,y) == (255,255,255) for y in range(image.height()) for x in range(image.width())), 'White handset is missing'
        assert image.transparency_get(0,0), 'Badge corners must preserve the contact picture'
        assert app.hidden_notifications.find_withtag('missed-call-corner'), 'Visible missed contact must keep the corner badge'
        assert app.corner_notification_state == 1 and app.hidden_notifications.find_withtag('notification-count')
        x1, y1, x2, y2 = app.avatar.bbox(tag)
        assert 0 <= x1 < x2 <= app.avatar.winfo_width() and 0 <= y1 < y2 <= app.avatar.winfo_height(), (code, 'badge clipped')
    app.server_seen = time.monotonic()
    app.press('right')
    assert person['id'] in app.model.missed_calls, 'Browsing cleared the badge'
    app.carousel_motion = None
    app.press('left')
    assert app.model.selected['id'] == person['id'] and person['id'] in app.model.missed_calls
    app.press('green')
    assert person['id'] not in app.model.missed_calls
    app.press('red')
    assert not app.avatar.find_withtag('missed-call')
    assert not app.missed_calls_store.load(app.model.config)
    # The corner notification persists for both hidden and visible flagged people.
    config = copy.deepcopy(app.model.config)
    config['carousel_portraits'] = 3  # This fixture asserts that the second neighbour is hidden.
    prototype = config['contacts'][0]
    config['contacts'] = [dict(prototype, id=f'person{i}', name=f'Person {i}', photo='', can_call=True, can_receive=True, online=True) for i in range(5)]
    app.model.configure(config)
    app.model.index = 0
    app.carousel_motion = None
    app.model.missed_calls = {'person2'}
    for width, height in [(900, 620), (1366, 1000)]:
        app.root.geometry(f'{width}x{height}')
        app.root.update()
        app.render()
        app.root.update_idletasks()
        assert app.hidden_notifications.find_withtag('missed-call-corner')
        assert not app.hidden_notifications.find_withtag('zmala-logo')
        assert not app.avatar.find_withtag('missed-call-person2')
        x1, y1, x2, y2 = app.hidden_notifications.bbox('missed-call-corner')
        assert 0 <= x1 < x2 <= app.hidden_notifications.winfo_width()
        assert 0 <= y1 < y2 <= app.hidden_notifications.winfo_height()
        assert app.hidden_notifications.winfo_rootx() < app.connectivity.winfo_rootx()
    app.press('right')
    # Complete the transition; the flagged contact now has a visible portrait.
    app.carousel_motion.started -= app.carousel_motion.duration
    app.tick()
    app.root.update_idletasks()
    assert app.avatar.find_withtag('missed-call-person2')
    assert app.hidden_notifications.find_withtag('missed-call')
    assert not app.hidden_notifications.find_withtag('zmala-logo')
    app.model.mark_notification('person2')
    app.model.mark_notification('person2')
    app.render()
    assert app.corner_notification_state == 3
    person_badge, = app.avatar.find_withtag('missed-call-person2')
    assert app.avatar.itemcget(person_badge, 'image') == str(app.icon_renderer.missed_call(18,theme.BADGE_RED,theme.BADGE_WHITE,count=3))
    app.model.missed_calls.add('person4')
    app.render()
    assert app.hidden_notifications.find_withtag('missed-call'), 'Another hidden flagged contact must keep the corner icon'
    assert app.corner_notification_state == 4
    two_contacts_image = app.corner_badge_image
    app.model.missed_calls.add('person4')
    app.render()
    assert app.corner_notification_state == 4 and app.corner_badge_image is two_contacts_image, 'Repeating the same flag must not increase its event count'
    app.model.mark_notification('person4')
    app.render()
    assert app.corner_notification_state == 5, 'A new event must increase the total'
    app.press('green')
    assert not app.hidden_notifications.find_withtag('missed-call'), 'Corner badge belongs to the carousel screen'
    app.press('red')
    assert app.hidden_notifications.find_withtag('missed-call')
    app.model.index = 2
    app.carousel_motion = None
    app.render()
    app.press('green');app.press('red')
    assert 'person2' not in app.model.missed_calls and app.model.missed_calls == {'person4'}
    assert app.hidden_notifications.find_withtag('missed-call'), 'Acknowledging one person must preserve another notification'
    assert app.corner_notification_state == 2 and app.corner_badge_image is not two_contacts_image
    assert app.model.notification_count('person4') == 2
    app.model.missed_calls.clear()
    app.render()
    assert not app.hidden_notifications.find_withtag('missed-call')
    assert not app.hidden_notifications.find_withtag('notification-count') and app.corner_notification_state == 0
    assert app.hidden_notifications.find_withtag('zmala-logo')
    x1, y1, x2, y2 = app.hidden_notifications.bbox('zmala-logo')
    assert 0 <= x1 < x2 <= app.hidden_notifications.winfo_width()
    assert 0 <= y1 < y2 <= app.hidden_notifications.winfo_height()
    for count in (1,9,10,40,100):
        app.draw_corner_notification(count)
        app.root.update_idletasks()
        x1,y1,x2,y2 = app.hidden_notifications.bbox('notification-count')
        assert 0 <= x1 < x2 <= app.hidden_notifications.winfo_width()
        assert 0 <= y1 < y2 <= app.hidden_notifications.winfo_height()
        assert app.corner_notification_state == count
    app.draw_corner_notification(0)
    # Smooth edges must contain intermediate colors rather than only flat strokes.
    for network, registered in [(True,True),(False,False),(None,False)]:
        app.network_connected = network
        app.server_seen = time.monotonic()
        app.draw_connectivity(registered)
        assert app.connectivity.find_withtag('network-status')
        colors = {app.network_image.get(x,y) for y in range(app.network_image.height()) for x in range(app.network_image.width())}
        flat = {tuple(int(color[i:i+2],16) for i in (1,3,5)) for color in [theme.BG,theme.GREEN,theme.RED,theme.MUTED]}
        assert len(colors-flat)>10, 'Connectivity icon edges are not anti-aliased'
    print('95-language questions and video feedback; red/white contact counters, combined corner total, partial acknowledgment, smooth transparent icons and input guards passed.')
finally:
    app.close()
