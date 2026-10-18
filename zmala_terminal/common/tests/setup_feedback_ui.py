"""Localized setup error layout without camera, network, or enrollment writes."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from zmala_terminal.common import main as main
from zmala_terminal.common.localization import LANGUAGES, font_family

class Preview(main.Terminal):
    def restore_enrollment(self, bootstrap, unconfigured):
        self.setup_stage = 'server'

    def bind_inputs(self):
        pass

    def start_services(self):
        pass

app = Preview(profile='setup-feedback-test')
try:
    for size in ('900x620', '1280x720'):
        app.root.geometry(size)
        app.root.update()
        for language in LANGUAGES:
            app.language = language
            app.font_family = font_family(language, app.available_fonts)
            app.setup_result(app.generation, 'error', None)
            app.root.update()
            label = app.setup_feedback_label
            assert label.winfo_ismapped(), language
            assert app.text('help') in label.cget('text'), language
            assert label.winfo_height() < 140, language
            assert app.video.winfo_height() >= 300, language
            assert label.winfo_rooty()+label.winfo_height() <= app.video.winfo_rooty(), language
        app.setup_feedback = False
        app.render(); app.root.update()
        assert not app.setup_feedback_label.winfo_ismapped()
    print('Setup error remains visible in all 95 languages; clears on success; camera retains space.')
finally:
    app.tv_control.close()
    app.text_renderer.close()
    app.root.destroy()
