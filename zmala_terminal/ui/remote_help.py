"""An idle-only recovery page; calls and enrollment always take priority."""
import time
import tkinter as tk
from configuration import ROOT
from model import State
from theme import BG, FG, MUTED
from ui.remote_test import RemoteTestView


class RemoteHelpView(RemoteTestView):
    def build_remote_help(self):
        from platforms.pairing_status import PairingStatus
        self.pairing_status = PairingStatus()
        self.pairing_page_visible = False
        self.remote_missing_since = None
        self.remote_help_signature = None
        self.remote_back_source = None
        self.remote_pairing_source = None
        self.remote_help = tk.Frame(self.root, bg=BG)
        content = tk.Frame(self.remote_help, bg=BG)
        content.place(relx=.5, rely=.48, anchor='center')
        self.remote_help_icon = tk.Label(content, bg=BG)
        self.remote_help_icon.pack(pady=(0, 16))
        self.remote_picture_labels = [tk.Label(self.remote_help_icon, bg=BG, fg=FG, borderwidth=0)
                                      for _ in range(3)]
        self.remote_help_title = tk.Label(content, bg=BG, fg=FG)
        self.remote_help_title.pack(before=self.remote_help_icon, pady=(0, 16))
        self.remote_help_detail = tk.Label(content, bg=BG, fg=MUTED, justify='center')
        self.remote_help_detail.pack()
        self.build_remote_test()

    def remote_back_picture(self, height, pairing=False):
        from PIL import Image, ImageTk
        attribute = 'remote_pairing_source' if pairing else 'remote_back_source'
        if getattr(self, attribute) is None:
            name = 'presenter-pairing.png' if pairing else 'presenter-turn-over.png'
            with Image.open(ROOT / 'assets' / name) as source:
                setattr(self, attribute, source.copy())
        source = getattr(self, attribute)
        size = (round(source.width * height / source.height), height)
        return ImageTk.PhotoImage(source.resize(size, Image.Resampling.LANCZOS), master=self.root)

    def label_remote_picture(self, height, visible, pairing=False):
        """Translate labels at render time; hardware artwork contains no copy."""
        for widget, key, x, y, limit in zip(self.remote_picture_labels,
                ('remote_picture_front', 'remote_picture_back', 'remote_picture_pairing' if pairing else 'remote_picture_power'),
                (.27, .69, .895), (.055, .055, .60 if pairing else .72), (.33, .33, .195)):
            if not visible:
                widget.place_forget()
                continue
            width = round(height * 16/9 * limit)
            size = 22 if key in ('remote_picture_front', 'remote_picture_back') else 17
            text = self.text(key)
            picture = self.text_renderer.photo(text, self.font_family, size, BG, FG, width, True)
            while picture and picture.height() > height * (.13 if y < .1 else .28) and size > 12:
                size -= 1
                picture = self.text_renderer.photo(text, self.font_family, size, BG, FG, width, True)
            widget.configure(text=text, image=picture if picture else '', wraplength=width,
                             font=(self.font_family, size, 'bold'))
            widget.image = picture
            widget.place(relx=x, rely=y, anchor='center')

    def update_remote_help(self):
        if self.update_usb_setup() or self.update_pairing_page():
            return
        status = getattr(getattr(self, 'presenter_input', None), 'status', None)
        now = time.monotonic()
        if status in (None, 'connected'):
            self.remote_missing_since = None
        elif self.remote_missing_since is None:
            self.remote_missing_since = now
        visible = (self.remote_missing_since is not None and now - self.remote_missing_since >= 5
                   and self.model.state == State.HOME and not self.setup_stage
                   and not getattr(self, 'settings_open', False)
                   and not (getattr(self, 'settings_hold', None) and self.settings_hold.capturing))
        if not visible:
            self.remote_help.place_forget()
            self.remote_help_signature = None
            return
        width = max(400, self.root.winfo_width() - 100)
        picture_height = max(160, min(340, int((self.root.winfo_height() - 80) * .5)))
        signature = (status, width, picture_height, self.language)
        if signature != self.remote_help_signature:
            self.remote_help_signature = signature
            key = status if status in ('unpaired', 'bluetooth_unavailable', 'blocked', 'input_unavailable') else 'disconnected'
            for widget, suffix, size, color in [(self.remote_help_title, 'title', 30, FG),
                                               (self.remote_help_detail, 'detail', 21, MUTED)]:
                text = self.text('remote_' + key + '_' + suffix)
                picture = self.text_renderer.photo(text, self.font_family, size, BG, color, width, suffix == 'title')
                widget.configure(text=text, image=picture if picture else '', wraplength=width,
                                 font=(self.font_family, size))
                widget.image = picture
            if key in ('disconnected', 'input_unavailable'):
                picture = self.remote_back_picture(picture_height)
            else:
                picture = self.icon_renderer.bluetooth(76, MUTED, BG, False)
            self.remote_help_icon.configure(image=picture)
            self.remote_help_icon.image = picture
            self.label_remote_picture(picture_height, key in ('disconnected', 'input_unavailable'))
        self.carousel_motion = None
        # Leave the existing connectivity icons visible. Never wake the TV.
        self.remote_help.place(x=0, y=80, relwidth=1, relheight=1, height=-80)
        self.remote_help.lift()

    def needs_pairing(self):
        state = self.pairing_status.read()
        if state is None:
            return False  # Desktop launchers do not require a Presenter.
        remote = getattr(self, 'presenter_input', None)
        ready = state == 'paired' and getattr(remote, 'status', None) == 'connected'
        self.remote_test.sync(self.pairing_status.bond if state == 'paired' else None, ready)
        return (state != 'paired' or not self.remote_test.complete or
                (self.setup_stage in ('wifi', 'wifi_ready', 'server') and not ready))

    def update_pairing_page(self):
        """Pair before opening a native camera surface, including fresh setup.

        The service pairs automatically; no confirmation from an unpaired
        remote is required. Calls retain priority if a pairing is later lost.
        """
        visible = self.model.state == State.HOME and self.needs_pairing()
        if not visible:
            if hasattr(self, 'remote_test_page'):
                self.remote_test_page.place_forget()
            if self.pairing_page_visible:
                self.pairing_page_visible = False
                self.remote_help.place_forget()
                self.remote_help_signature = None
                self.root.after_idle(self.render)
            return False
        self.pairing_page_visible = True
        self.stop_scanner()
        if self.remote_test.ready and self.remote_test.bond:
            self.remote_help.place_forget()
            self.draw_remote_test()
            return True
        self.remote_test_page.place_forget()
        width = max(400, self.root.winfo_width() - 100)
        key = 'bluetooth_unavailable' if self.pairing_status.read() == 'bluetooth_unavailable' else 'unpaired'
        if self.pairing_status.read() == 'paired':
            key = 'disconnected' if getattr(self.presenter_input, 'status', None) == 'disconnected' else 'input_unavailable'
        picture_height = max(180, min(300, self.root.winfo_height() - 400))
        signature = ('pairing-page', key, width, picture_height, self.language)
        if signature != self.remote_help_signature:
            self.remote_help_signature = signature
            for widget, suffix, size, color in [(self.remote_help_title, 'title', 30, FG),
                                               (self.remote_help_detail, 'detail', 23, MUTED)]:
                text = self.text('remote_' + key + '_' + suffix)
                picture = self.text_renderer.photo(text, self.font_family, size, BG, color, width, suffix == 'title')
                widget.configure(text=text, image=picture if picture else '', wraplength=width,
                                 font=(self.font_family, size))
                widget.image = picture
            picture = (self.remote_back_picture(picture_height, pairing=True) if key == 'unpaired'
                       else self.icon_renderer.bluetooth(100, MUTED, BG, False))
            self.remote_help_icon.configure(image=picture)
            self.remote_help_icon.image = picture
            self.label_remote_picture(picture_height, key == 'unpaired', pairing=True)
        self.remote_help.place(x=0, y=0, relwidth=1, relheight=1)
        self.remote_help.lift()
        return True
