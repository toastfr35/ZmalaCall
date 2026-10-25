# @test T-HLT-012
# @requirements HLR-TERM-CONFIG-016, HLR-TERM-AUDIO-001
# @environment display
# @plan Render settings on the real Tk UI and drive selection/draft transitions; assert only the active pane shows controls and cancellation preserves configuration.
# At both sizes, render French short values with the real Pango font and assert their final images retain the full text without ellipsis and stay inside their rows.
# Render the exit confirmation in every supported language at both sizes; verify bounded question/buttons, red returns to the same selection and green exits without modifying configuration.
# Render the ringtone editor and exercise its debounced preview request through substituted playback; verify left/right wrap selects the last/first visible choice without saving, and cancel and incoming-call interruption stop it without changing the selected ringtone.
# @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

"""Real Tk settings navigation/layout without SIP, camera or enrollment side effects."""
from pathlib import Path
import sys
import time
from unittest.mock import patch, Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from zmala_terminal.common import main as main
from zmala_terminal.common.local_settings import FIELDS
from zmala_terminal.common.model import State
from zmala_terminal.common.localization import LANGUAGES, font_family
from tests.terminal.LLT.test_terminal import config

class Preview(main.Terminal):
    def restore_enrollment(self, bootstrap, unconfigured):
        self.setup_stage = None
    def bind_inputs(self):
        pass
    def start_services(self):
        pass
    def action(self, action):
        if action:
            self.actions.append(action)

app = Preview(profile='settings-ui-test')
app.actions = []
app.model.configure(config() | {'language': 'fr', 'auto_answer': False, 'auto_answer_seconds': 30,
                               'device_id': 'ZM-TEST-123456', 'c20_speaker_volume': 80})
app.server_seen = time.monotonic()
try:
    app.keys_down.add('red')
    with patch('zmala_terminal.common.settings_control.time.monotonic', return_value=100):
        app.press('red')
    app.tick_settings_access(101.99)
    assert not app.settings_hold.capturing
    app.tick_settings_access(102)
    app.root.update()
    assert app.settings_canvas.find_withtag('settings-progress')
    app.tick_settings_access(110)
    app.keyrelease('red')
    assert app.settings_open and not app.actions, app.actions
    for size in ('900x620', '1280x720'):
        print(f'Settings layout: {size}, {len(LANGUAGES)} languages', flush=True)
        app.root.geometry(size)
        app.root.update()
        app.language = 'fr'
        app.font_family = font_family('fr', app.available_fonts)
        rendered = {}
        original_photo = app.text_renderer.photo
        def record_photo(text, *args, **kwargs):
            photo = original_photo(text, *args, **kwargs)
            if photo is not None:
                rendered[str(photo)] = text
            return photo
        with patch.object(app.text_renderer, 'photo', side_effect=record_photo):
            app.settings_signature = None
            app.render(); app.root.update()
            for key in ('language', 'c20_speaker_volume', 'ringtone', 'carousel_portraits'):
                item = next(i for i in app.settings_canvas.find_withtag('settings-value')
                            if key in app.settings_canvas.gettags(i))
                image = app.settings_canvas.itemcget(item, 'image')
                expected = app.settings_value(key, app.settings_draft.value(app.model.config, key))
                assert rendered[image] == expected, (size, key, rendered[image], expected)
                row = app.settings_canvas.bbox('settings-row-'+key)
                value = app.settings_canvas.bbox(item)
                assert value[1] >= row[1] and value[3] <= row[3], (size, key, row, value)
        for language in LANGUAGES:
            app.language = language
            app.font_family = font_family(language, app.available_fonts)
            for row in range(len(FIELDS)):
                app.settings_draft.row = row
                for editing in ((False,) if row == FIELDS.index('reset') else (False, True)):
                    if editing:
                        app.settings_draft.open(app.model.config)
                    else:
                        app.settings_draft.editing = False
                    app.render(); app.root.update()
                    c = app.settings_canvas
                    assert c.winfo_ismapped()
                    bounds = c.bbox('all')
                    assert bounds[0] >= 0 and bounds[2] <= c.winfo_width(), (language, row, bounds)
                    assert bounds[1] >= 0 and bounds[3] <= c.winfo_height(), (language, row, bounds)
                    hints = c.bbox('settings-hint')
                    split = c.winfo_width()*.39
                    assert (hints[0] > split) if editing else (hints[2] < split)
            app.settings_draft.editing = False
            app.settings_draft.confirm_exit = True
            app.render(); app.root.update()
            c = app.settings_canvas
            for tag in ('settings-exit-question', 'settings-exit-yes', 'settings-exit-no'):
                bounds = c.bbox(tag)
                assert bounds and bounds[0] >= 0 and bounds[2] <= c.winfo_width(), (language, size, tag, bounds)
                assert bounds[1] >= 0 and bounds[3] <= c.winfo_height(), (language, size, tag, bounds)
            app.settings_draft.confirm_exit = False
    app.settings_draft.editing = False
    app.settings_draft.row = FIELDS.index('ringtone')
    app.model.config['ringtones'] = [
        {'id': 'nokia', 'name': 'Nokia', 'url': '/api/ringtones/nokia.wav'},
        {'id': 'a'*64, 'name': 'Last tone', 'url': '/api/ringtones/'+('a'*64)+'.wav'}]
    app.usb_power = Mock(enabled=True, ringtone_preview_status='playing')
    app.engine = None
    app.press('green')
    app.tick_ringtone(1000); app.tick_ringtone(1000.39)
    app.usb_power.preview_tone.assert_not_called()
    app.tick_ringtone(1000.4); app.root.update()
    app.usb_power.preview_tone.assert_called_once()
    assert app.settings_canvas.find_withtag('ringtone-preview')
    app.press('left'); app.root.update()
    assert app.settings_draft.index == 1
    assert app.settings_value('ringtone', app.settings_draft.options[1]) == 'Last tone'
    assert app.model.config.get('ringtone', 'nokia') == 'nokia'
    app.press('right'); app.root.update()
    assert app.settings_draft.index == 0
    saved_ringtone = app.model.config.get('ringtone', 'nokia')
    app.press('red'); app.tick_ringtone(1001)
    assert app.ringtone_preview_token is None and app.model.config.get('ringtone', 'nokia') == saved_ringtone
    app.press('green'); app.tick_ringtone(1002)
    app.model.state = State.RINGING; app.tick_ringtone(1003)
    assert app.ringtone_preview_token is None
    app.model.state = State.HOME; app.settings_draft.editing = False; app.settings_open = True
    app.settings_draft.row = FIELDS.index('reset')
    app.press('green')
    assert app.setup_stage == 'reset' and not app.settings_open
    app.press('red')
    assert app.setup_stage is None and app.settings_open and app.settings_draft.row == FIELDS.index('reset')
    app.language = 'fr'
    app.settings_draft.row = 1
    app.settings_draft.open(app.model.config)
    before = dict(app.model.config)
    app.press('right'); app.press('red')
    assert app.model.config == before and not app.settings_draft.editing
    app.press('red'); app.root.update()
    assert app.settings_open and app.settings_draft.confirm_exit
    selected_row = app.settings_draft.row
    app.press('red')
    assert app.settings_open and not app.settings_draft.confirm_exit and app.settings_draft.row == selected_row
    app.press('red'); app.press('green')
    assert not app.settings_open and app.model.state == State.HOME and app.model.config == before
    if len(sys.argv) > 1:
        from PIL import ImageGrab
        app.settings_open = True
        app.settings_draft.row = FIELDS.index('tv_idle_seconds')
        app.settings_draft.open(app.model.config)
        app.render(); app.root.update()
        app.draw_tv_idle(.6); app.root.update()
        assert app.tv_idle_bar.winfo_height() == 3
        assert app.tv_idle_bar.winfo_y() == app.root.winfo_height()-3
        assert app.tv_idle_bar.winfo_width() == round(app.root.winfo_width()*.6)
        ImageGrab.grab(bbox=(app.root.winfo_rootx(), app.root.winfo_rooty(),
                            app.root.winfo_rootx()+app.root.winfo_width(),
                            app.root.winfo_rooty()+app.root.winfo_height())).save(sys.argv[1])
    print('Settings: 95 languages, seven editors, both focus sides at 900x620 and 1280x720; ringtone wrap/preview/cancel/call interruption, exit confirmation, red hold and reset navigation passed.')
finally:
    app.tv_control.close()
    app.text_renderer.close()
    app.root.destroy()
