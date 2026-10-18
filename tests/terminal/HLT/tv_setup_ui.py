# @test T-HLT-017
# @requirements HLR-TERM-TV-001
# @environment display
# @plan Render TV-check prompts using the real UI with controlled state transitions; assert localized controls and current test outcome. Physical TV power/input behavior requires a separate device run.
# @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

"""Exercise every TV wizard page at kiosk sizes without touching TV/network."""
from pathlib import Path
import sys
import tempfile
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from zmala_terminal.common.main import Terminal
from zmala_terminal.common.tv_check import TVCheck
from zmala_terminal.common.tv_check_messages import MESSAGES
from zmala_terminal.common.localization import font_family


class Fixture(Terminal):
    def restore_enrollment(self, *args):
        self.setup_stage = 'tv'

    def bind_inputs(self):
        self.presenter_input = Mock(status='connected', connected=True, battery=None, charger_connected=None)
        self.volume_control = Mock()

    def start_services(self):
        pass

    def needs_pairing(self):
        return False

    def needs_c20(self):
        return False


with tempfile.TemporaryDirectory() as folder:
    app = Fixture(profile='qa-tv-layout')
    app.tv_check = TVCheck(Path(folder)/'tv-check.json', Mock())
    app.tv_check.record = {'power': {'status': 'passed'}, 'source': {'status': 'failed'}}
    app.tv_check.candidates = [{'host': '192.168.1.123', 'name': 'Living room Samsung television'}]
    pages = ['probe', 'power_ready', 'power_running', 'power_confirm', 'retry_power',
             'source_ready', 'source_wait', 'source_confirm', 'source_timeout', 'samsung',
             'sony', 'sony_help', 'samsung_help', 'discover', 'choose_tv', 'pair', 'paired',
             'no_tv', 'retry_source', 'unavailable', 'save_error', 'summary']
    try:
        for width, height in ((900, 620), (1280, 720), (1920, 1080)):
            app.root.geometry(f'{width}x{height}')
            app.root.update()
            for language in MESSAGES:
                app.language = language
                app.font_family = font_family(language, app.available_fonts)
                for page in pages:
                    app.tv_check.page = page
                    app.tv_check.busy = page in ('probe', 'power_running', 'source_wait', 'discover', 'pair')
                    app.render()
                    app.root.update()
                    assert app.tv_check_page.winfo_ismapped()
                    c = app.tv_check_page
                    for item in c.find_all():
                        box = c.bbox(item)
                        assert box and 0 <= box[0] and box[2] <= width and 0 <= box[1] and box[3] <= height, (language, page, box)
        # Save a local rendering for visual inspection; no live camera involved.
        from PIL import Image, ImageTk
        app.tv_check.page = 'source_ready'
        app.language = 'fr'
        app.root.geometry('1280x720+30+30')
        app.root.update()
        app.render()
        app.root.update()
        output = Path('build_tools/tmp/tv-check-layout.png')
        output.parent.mkdir(parents=True, exist_ok=True)
        rendered = Image.new('RGB', (app.root.winfo_width(), app.root.winfo_height()), '#0d1420')
        pictures = {str(photo): photo for photo in app.tv_check_images}
        for item in app.tv_check_page.find_all():
            photo = pictures[app.tv_check_page.itemcget(item, 'image')]
            x, y, _, _ = app.tv_check_page.bbox(item)
            pixels = ImageTk.getimage(photo)
            rendered.paste(pixels, (x, y), pixels)
        rendered.save(output)
        print(f'{len(pages)} TV pages fit at three resolutions in {len(MESSAGES)} languages; no TV commands sent.')
    finally:
        app.close()
