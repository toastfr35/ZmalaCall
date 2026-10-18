# @test T-HLT-009
# @requirements HLR-TERM-SETUP-001
# @environment display
# @plan Render USB, Bluetooth and ordered button-test stages on a real Tk canvas; assert current-step illustration and button feedback. Inspect the generated screens for legibility.
# @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

"""Real Tk layout/transition test without Bluetooth, camera, Wi-Fi or enrollment writes."""
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from zmala_terminal.common.main import Terminal
from zmala_terminal.common.localization import font_family
from zmala_terminal.common.remote_test import RemoteTest, BUTTONS


class PairingFixture(Terminal):
    def restore_enrollment(self, *args):
        self.setup_stage = 'wifi'

    def bind_inputs(self):
        self.presenter_input = Mock(status='unpaired', connected=False, battery=None, charger_connected=None)
        self.volume_control = Mock()

    def start_services(self):
        pass


with tempfile.TemporaryDirectory() as folder:
    status = Path(folder) / 'status.json'
    status.write_text(json.dumps({'state': 'unpaired'}))
    os.environ['ZMALA_PAIRING_STATUS'] = str(status)
    app = PairingFixture(profile='qa-pairing-layout')
    app.remote_test = RemoteTest(Path(folder)/'test.json')
    app.c20_status = Mock()
    try:
        for width, height in [(900, 620), (1280, 720), (1920, 1080)]:
            app.root.geometry(f'{width}x{height}')
            app.root.update()
            for language in ('en', 'fr'):
                app.language = language
                app.font_family = font_family(language, app.available_fonts)
                app.c20_status.read.return_value = False
                app.render()
                app.root.update()
                assert app.usb_setup_visible and app.usb_setup.winfo_ismapped()
                picture = app.usb_setup_picture
                assert picture.winfo_width() <= width and picture.winfo_height() <= height
                assert app.scanner is None
                app.c20_status.read.return_value = True
                app.render()
                app.root.update()
                assert not app.usb_setup_visible
                assert not app.usb_setup.winfo_ismapped()
                assert app.pairing_page_visible
                assert app.remote_help_title.cget('text') == 'Connect your remote'
                assert app.scanner is None
                for widget in (app.remote_help_title, app.remote_help_icon, app.remote_help_detail):
                    x = widget.winfo_rootx() - app.root.winfo_rootx()
                    y = widget.winfo_rooty() - app.root.winfo_rooty()
                    assert 0 <= x and x + widget.winfo_width() <= width, (language, width, x)
                    assert 0 <= y and y + widget.winfo_height() <= height, (language, height, y)
        status.write_text(json.dumps({'state': 'paired', 'bond': 'layout-bond'}))
        app.pairing_status.next_read = 0
        app.presenter_input.status = 'connected'
        for width, height in [(900, 620), (1280, 720), (1920, 1080)]:
            app.root.geometry(f'{width}x{height}')
            app.root.update()
            app.render()
            app.root.update()
            assert app.pairing_page_visible and app.remote_test_page.winfo_ismapped()
            assert app.scanner is None
            c = app.remote_test_page
            for item in c.find_all():
                box = c.bbox(item)
                assert box and 0 <= box[0] and box[2] <= width and 0 <= box[1] and box[3] <= height, box
        for button in BUTTONS:
            app.remote_test_event(button, True)
            app.remote_test_event(button, False)
        app.render()
        app.root.update()
        assert not app.pairing_page_visible
        assert not app.remote_help.winfo_ismapped()
        assert app.video.winfo_ismapped()
        assert not app.remote_test_page.winfo_ismapped()
        print('USB -> pairing -> five physical buttons -> Wi-Fi passed at three viewport sizes; setup stays English.')
    finally:
        app.close()
