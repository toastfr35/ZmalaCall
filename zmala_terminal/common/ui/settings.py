"""Two-panel remote-only settings, with hints on the active side and a serial footer."""
import json
from pathlib import Path
import tkinter as tk
from zmala_terminal.common.local_settings import FIELDS, SettingsDraft
from zmala_terminal.common.localization import LANGUAGES, font_family
from zmala_terminal.common.theme import BG, FG, MUTED, PANEL, ACCENT, BUTTON_GREEN, BUTTON_RED, RED

MESSAGES = json.loads((Path(__file__).resolve().parents[1] / 'shared/settings-messages.json').read_text(encoding='utf-8'))
KEYS = ('settings', 'language', 'auto_answer', 'auto_framing', 'c20_speaker_volume',
        'carousel_portraits', 'never', 'open', 'accept', 'exit', 'current', 'tv_idle_seconds')


class SettingsView:
    def settings_text(self, key):
        if key == 'reset':
            return self.text('reset')
        return MESSAGES.get(self.language, MESSAGES['en'])[KEYS.index(key)]

    def build_settings(self):
        self.settings_canvas = tk.Canvas(self.root, bg=BG, highlightthickness=0)
        self.settings_canvas.bind('<Configure>', lambda event: self.draw_settings())
        self.settings_images = []
        self.settings_signature = None

    def settings_value(self, key, value):
        if key == 'reset':
            return ''
        if key == 'language':
            return LANGUAGES[value]['native']
        if key in ('auto_answer', 'tv_idle_seconds'):
            return self.settings_text('never') if not value else f'{value//60} min' if value % 60 == 0 else f'{value} s'
        if key == 'auto_framing':
            return self.text('yes' if value else 'no')
        return f'{value} %' if key == 'c20_speaker_volume' else str(value)

    def render_settings(self):
        sequence = getattr(self, 'settings_hold', None)
        active = getattr(self, 'settings_open', False) or bool(sequence and sequence.capturing)
        if active:
            self.settings_canvas.place(x=0, y=0, relwidth=1, relheight=1)
            tk.Misc.lift(self.settings_canvas)
            self.draw_settings()
        else:
            self.settings_canvas.place_forget()
            self.settings_signature = None
        return active

    def settings_label(self, text, x, y, width, size=22, color=FG, background=BG,
                       bold=False, anchor='nw', language=None, max_height=None, tags=()):
        if not text:
            return
        family = font_family(language or self.language, self.available_fonts)
        while True:
            picture = self.text_renderer.photo(text, family, size, background, color, int(width), bold)
            if not max_height or picture.height() <= max_height or size <= 11:
                break
            size -= 1
        self.settings_images.append(picture)
        self.settings_canvas.create_image(x, y, image=picture, anchor=anchor, tags=tags)

    def settings_panel(self, x, y, width, height, fill, outline=None, tags=()):
        if outline:
            image = self.icon_renderer.rounded_button(int(width), int(height), outline, BG)
            self.settings_images.append(image)
            self.settings_canvas.create_image(x, y, image=image, anchor='nw', tags=tags)
            x, y, width, height = x+3, y+3, width-6, height-6
        image = self.icon_renderer.rounded_button(int(width), int(height), fill, outline or BG)
        self.settings_images.append(image)
        self.settings_canvas.create_image(x, y, image=image, anchor='nw', tags=tags)

    def draw_settings(self):
        if not (self.settings_open or self.settings_hold.capturing):
            return
        c, config = self.settings_canvas, self.model.config
        width, height = max(900, c.winfo_width()), max(620, c.winfo_height())
        draft = self.settings_draft
        signature = (width, height, self.language, self.settings_open, int(self.settings_hold.progress*100),
                     draft.row, draft.editing, draft.index, draft.busy, draft.error,
                     tuple(SettingsDraft.value(config, key) for key in FIELDS))
        if signature == self.settings_signature:
            return
        self.settings_signature = signature
        c.delete('all')
        self.settings_images = []
        serial = config.get('device_id', '')
        self.settings_label('ID : ' + serial, width/2, height-18, width-64, 11, MUTED, anchor='center', tags='settings-serial')
        if not self.settings_open:
            self.settings_label(self.settings_text('settings'), width/2, height*.35, width-80,
                                36, bold=True, anchor='center')
            x, y, bar_width = width*.2, height*.55, width*.6
            self.settings_panel(x, y, bar_width, 32, PANEL)
            c.create_rectangle(x+5, y+5, x+5+(bar_width-10)*self.settings_hold.progress,
                               y+27, fill=BUTTON_RED, outline='', tags='settings-progress')
            return
        split, margin = int(width*.39), 28
        left_width, right_x = split-2*margin, split+margin
        right_width = width-right_x-margin
        c.create_line(split, 28, split, height-50, fill='#2b3547')
        self.settings_label(self.settings_text('settings'), margin, 28, left_width, 32, bold=True, max_height=66)
        row_height = min(88, (height-210-6*(len(FIELDS)-1))/len(FIELDS))
        for index, key in enumerate(FIELDS):
            y = 112+index*(row_height+6)
            selected = draft.row == index
            fill = '#303b50' if selected else PANEL
            self.settings_panel(margin, y, left_width, row_height, fill,
                                ACCENT if selected and not draft.editing else None, tags='settings-row')
            self.settings_label(self.settings_text(key), margin+14, y+(row_height*.3 if key == 'reset' else 10), left_width-28,
                                22, color=RED if key == 'reset' else FG, background=fill, bold=True, max_height=row_height*.45)
            value = self.settings_value(key, SettingsDraft.value(config, key))
            self.settings_label(value, margin+14, y+row_height*.55, left_width-28,
                                19, MUTED, fill, max_height=row_height*.37)
        key = draft.key
        self.settings_label(self.settings_text(key), right_x, 28, right_width, 30, bold=True, max_height=72)
        shown = draft
        if not draft.editing and key != 'reset':
            shown = SettingsDraft()
            shown.row = draft.row
            shown.open(config)
        if key == 'reset':
            self.settings_label(self.text('factory_reset'), right_x, 180, right_width,
                                28, RED, bold=True, max_height=150)
        elif key == 'c20_speaker_volume':
            value = shown.options[shown.index]
            self.settings_label(f'‹   {value} %   ›', right_x+right_width/2, 190,
                                right_width, 40, ACCENT if draft.editing else MUTED, anchor='center')
            x, top, bottom = right_x+right_width/2, 250, height-200
            self.settings_panel(x-20, top, 40, bottom-top, PANEL)
            if value:
                c.create_rectangle(x-15, bottom-5-(bottom-top-10)*value/100, x+15, bottom-5,
                                   fill=ACCENT, outline='')
        else:
            visible = min(7, len(shown.options))
            start = max(0, min(shown.index-visible//2, len(shown.options)-visible))
            option_height = min(52, (height-306-(visible-1)*5)/max(1, visible))
            for index in range(start, start+visible):
                value = shown.options[index]
                y = 126+(index-start)*(option_height+5)
                selected = index == shown.index
                fill = '#303b50' if selected else PANEL
                self.settings_panel(right_x, y, right_width, option_height, fill,
                                    ACCENT if selected and draft.editing else None, tags='settings-option')
                text = ('›  ' if selected and draft.editing else '') + self.settings_value(key, value)
                self.settings_label(text, right_x+16, y+option_height/2, right_width-32, 22,
                                    FG if draft.editing else MUTED, fill, selected,
                                    anchor='w', language=value if key == 'language' else None,
                                    max_height=option_height-8)
            if len(shown.options) > visible:
                self.settings_label(f'{shown.index+1} / {len(shown.options)}', right_x+right_width,
                                    height-178, right_width, 14, MUTED, anchor='e')
        if key != 'reset':
            current = self.settings_value(key, SettingsDraft.value(config, key))
            self.settings_label(self.settings_text('current') + ' : ' + current, right_x, height-154,
                                right_width, 17, MUTED, max_height=36)
        x, available = (right_x, right_width) if draft.editing else (margin, left_width)
        if draft.busy or draft.error:
            self.settings_label(self.text('wait' if draft.busy else 'help'), right_x, height-116,
                                right_width, 17, MUTED if draft.busy else RED, max_height=38)
        if not draft.busy:
            # Hints belong exclusively to the active panel.
            y, gap = height-72, 8
            part = (available-2*gap)/3
            for i, (label, fill) in enumerate([
                    ('‹ › ' + self.text('select'), PANEL),
                    ('✓ ' + self.settings_text('accept' if draft.editing else 'open'), BUTTON_GREEN),
                    ('× ' + (self.text('cancel') if draft.editing else self.settings_text('exit')), BUTTON_RED)]):
                self.settings_panel(x+i*(part+gap), y, part, 40, fill, tags='settings-hint')
                self.settings_label(label, x+i*(part+gap)+part/2, y+20, part-10, 17, FG, fill,
                                    True, anchor='center', max_height=32)
