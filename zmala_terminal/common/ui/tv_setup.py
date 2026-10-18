"""Post-enrollment TV checks: full-screen prompts, remote-only interaction."""
import os
import tkinter as tk
import time

from zmala_terminal.common.localization import font_family
from zmala_terminal.linux.tv_check import CheckTransport
from zmala_terminal.common.tv_check import TVCheck
from zmala_terminal.common.tv_check_messages import MESSAGES
from zmala_terminal.common.theme import BG, FG, MUTED, BUTTON_GREEN, BUTTON_RED


class TVSetupView:
    def build_tv_setup(self):
        self.tv_check = None
        self.tv_setup_checked = False
        self.tv_check_config = None
        self.tv_check_page = tk.Canvas(self.root, bg=BG, highlightthickness=0)
        self.tv_check_page.bind('<Configure>', lambda e: self.draw_tv_setup())
        self.tv_check_signature = None
        self.tv_check_images = []

    # @llr LLR-TERM-TV-003
    def begin_tv_setup(self, config):
        if self.tv_setup_checked:
            return False
        self.tv_setup_checked = True
        if not os.environ.get('ZMALA_PAIRING_STATUS'):
            return False
        if self.maintenance:
            self.maintenance.stop()
            self.maintenance = None
        self.language = config.get('language', 'en')
        self.font_family = font_family(self.language, self.available_fonts)
        self.tv_check_config = config
        self.setup_stage = 'tv'
        self.tv_check = TVCheck(self.enrollment.path.parent / 'tv-check.json', CheckTransport(self.tv_control))
        self.tv_check.start()
        return True

    def tick_tv_setup(self):
        check = self.tv_check
        if not check or self.setup_stage != 'tv':
            return
        if check.poll():
            self.render()
        if check.page == 'done':
            record = check.record
            self.tv_control.power_enabled = record['power']['status'] == 'passed'
            self.tv_control.source_enabled = record['source']['status'] == 'passed'
            check.close()
            self.tv_check = None
            self.setup_stage = None
            self.last_button = time.monotonic()
            self.apply_config(self.tv_check_config)
            self.tv_check_config = None
            self.maintenance = self.make_maintenance(self.configuration)
            self.render()

    def tv_setup_button(self, button):
        if self.setup_stage == 'tv' and self.tv_check:
            self.tv_check.button(button)
            self.render()
            return True
        return False

    def render_tv_setup(self):
        if self.setup_stage == 'tv' and self.tv_check:
            self.video.place_forget()
            self.confirmation.place_forget()
            self.settings_canvas.place_forget()
            self.remote_help.place_forget()
            self.tv_check_page.place(x=0, y=0, relwidth=1, relheight=1)
            tk.Misc.lift(self.tv_check_page)
            self.draw_tv_setup()
            return True
        self.tv_check_page.place_forget()
        self.tv_check_signature = None
        return False

    def draw_tv_setup(self):
        check = self.tv_check
        if not check or self.setup_stage != 'tv':
            return
        w, h = self.root.winfo_width(), self.root.winfo_height()
        signature = (w, h, self.language, check.page, check.selection, check.error, str(check.record))
        if signature == self.tv_check_signature:
            return
        self.tv_check_signature = signature
        c = self.tv_check_page
        c.delete('all')
        self.tv_check_images = []
        messages = MESSAGES.get(self.language, MESSAGES['en'])
        def text(key):
            return messages[key]
        scale = min(w/1280, h/720)
        def label(value, y, size=26, color=FG, maximum=320):
            picture = None
            while size >= 13:
                picture = self.text_renderer.photo(value, self.font_family, round(size*scale), BG, color, int(w*.84), False)
                if picture.height() <= maximum*scale:
                    break
                size -= 1
            self.tv_check_images.append(picture)
            c.create_image(w/2, h*y, image=picture, anchor='center')
        label(text('title'), .09, 32, maximum=60)
        page = check.page
        if page in ('done', 'probe'):
            label(text('probe'), .45)
            return
        detail = text(page)
        if page == 'choose_tv':
            candidate = check.candidates[check.selection]
            detail += '\n\n' + candidate['name'] + '\n' + candidate['host']
        elif page == 'summary':
            detail += '\n\n' + '\n'.join(text(kind) + ' : ' + text(check.record[kind]['status']) for kind in ('power', 'source'))
        label(detail, .45, maximum=380)
        if check.error and page.endswith('_confirm'):
            label(text('error'), .76, 18, MUTED, maximum=60)
        if check.busy:
            return
        green, red = 'yes', 'no'
        if page == 'power_ready':
            green, red = 'start', 'skip'
        elif page == 'source_ready':
            green, red = 'start', 'skip'
        elif page in ('retry_power', 'retry_source', 'paired', 'unavailable'):
            green, red = 'retry', 'without'
        elif page in ('samsung_help', 'sony_help', 'no_tv'):
            green, red = 'continue', 'back'
        elif page == 'choose_tv':
            green, red = 'select', 'back'
        elif page in ('save_error', 'summary', 'source_timeout'):
            green, red = 'retry' if page == 'save_error' else 'continue', None
        for index, (key, color) in enumerate(((green, BUTTON_GREEN), (red, BUTTON_RED))):
            if key is None:
                continue
            bw, bh = int(w*.34), int(64*scale)
            x = w*(.31 if index == 0 else .69)
            bg = self.icon_renderer.rounded_button(bw, bh, color, BG)
            self.tv_check_images.append(bg)
            c.create_image(x, h*.9, image=bg)
            image = self.text_renderer.photo(text(key), self.font_family, round(23*scale), color, FG, bw-20, True)
            self.tv_check_images.append(image)
            c.create_image(x, h*.9, image=image)
