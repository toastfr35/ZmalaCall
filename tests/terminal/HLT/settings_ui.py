# @test T-HLT-012
# @requirements THLR013
# @environment display
# @plan Render settings on the real Tk UI and drive selection/draft transitions; assert only the active pane shows controls and cancellation preserves configuration.
# @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

"""Real Tk settings navigation/layout without SIP, camera or enrollment side effects."""
from pathlib import Path
import sys
import time
from unittest.mock import patch
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
        app.root.geometry(size)
        app.root.update()
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
    app.press('red')
    assert not app.settings_open and app.model.state == State.HOME
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
    print('Settings: 95 languages, six editors, both focus sides at 900x620 and 1280x720; red hold, reset navigation and red cancel passed.')
finally:
    app.tv_control.close()
    app.text_renderer.close()
    app.root.destroy()
