"""Tk widgets and layout. No worker or SIP callback updates widgets outside the UI thread."""
import math
import time
import tkinter as tk
import tkinter.font as tkfont
from zmala_terminal.common.model import State
from zmala_terminal.common.localization import translate
from zmala_terminal.common.theme import BG, FG, MUTED, GREEN, RED
from zmala_terminal.common.ui.carousel import CarouselView
from zmala_terminal.common.ui.confirmation import ConfirmationView
from zmala_terminal.common.ui.remote_help import RemoteHelpView
from zmala_terminal.common.ui.settings import SettingsView
from zmala_terminal.common.ui.usb_setup import UsbSetupView
from zmala_terminal.common.ui.tv_setup import TVSetupView
from zmala_terminal.common.configuration import ROOT


class TerminalDisplay(CarouselView, ConfirmationView, RemoteHelpView, SettingsView, UsbSetupView, TVSetupView):
    def build_ui(self):
        self.top = tk.Frame(self.root, bg=BG)
        self.top.pack(fill='x', padx=18, pady=(12, 0))
        # Equal side columns keep the call name centered between the status icons.
        self.top.grid_columnconfigure(0, minsize=246)
        self.top.grid_columnconfigure(1, weight=1)
        self.top.grid_columnconfigure(2, minsize=246)
        self.hidden_notifications = tk.Canvas(self.top, width=64, height=56, bg=BG, highlightthickness=0)
        self.hidden_notifications.grid(row=0, column=0, sticky='w')
        self.corner_logo = self.text_renderer.portrait(ROOT / 'common/assets/zmala-icon.png', 40, BG)
        self.corner_notification_state = None
        self.draw_corner_notification(0)
        self.connectivity = tk.Canvas(self.top, width=246, height=30, bg=BG, highlightthickness=0)
        self.connectivity.grid(row=0, column=2, sticky='e')
        self.call_name = tk.Label(self.top, text='', bg=BG, fg=FG, borderwidth=0)
        self.title = tk.Label(self.root, text='Who would you like to call?', font=('Segoe UI', 32, 'bold'), bg=BG, fg=FG)
        self.title.pack(pady=(16, 8))
        self.setup_feedback_label = tk.Label(self.root, bg=BG, fg=RED, borderwidth=0)
        self.body = tk.Frame(self.root, bg=BG)
        self.body.pack(fill='both', expand=True, padx=40)
        self.home = tk.Frame(self.body, bg=BG)
        self.home.grid_columnconfigure(0, weight=1)
        self.home.grid_rowconfigure(0, weight=1)
        self.avatar = tk.Canvas(self.home, width=940, height=370, bg=BG, highlightthickness=0)
        self.avatar.grid(row=0, column=0, sticky='nsew', pady=(5, 0))
        self.avatar.bind('<Configure>', lambda event: self.draw_reset() if self.setup_stage == 'reset' else self.draw_wifi_confirmation() if self.setup_stage == 'wifi_ready' else self.draw_avatar(self.model.contact or self.model.selected))
        self.name = tk.Label(self.home, text='', font=('Segoe UI', 36, 'bold'), bg=BG, fg=FG)
        self.name.grid(row=1, column=0, pady=(0, 5))
        self.subtitle = tk.Label(self.home, text='', font=('Segoe UI', 19), bg=BG, fg=MUTED, wraplength=850)
        self.subtitle.grid(row=2, column=0, pady=(0, 4))
        self.video = tk.Frame(self.body, bg=BG, highlightthickness=0)
        self.video_border = (0, None)
        # Keep the native rendering surface mapped behind this child panel so
        # incoming video can start without rebuilding the media stream.
        self.missing_video = tk.Frame(self.video, bg=BG)
        # Reserve the bottom-right fifth for the local camera child surface.
        self.missing_video_bottom = tk.Frame(self.video, bg=BG)
        self.missing_video_visible = False
        message = tk.Frame(self.missing_video, bg=BG)
        message.place(relx=.5, rely=.5, anchor='center')
        camera = tk.Canvas(message, width=144, height=110, bg=BG, highlightthickness=0)
        camera.pack(pady=(0, 25))
        camera.create_rectangle(18, 25, 91, 85, outline=MUTED, width=5)
        camera.create_polygon(91, 42, 125, 26, 125, 84, 91, 68, fill=BG, outline=MUTED, width=5)
        camera.create_line(12, 9, 133, 102, fill=FG, width=6)
        self.video_message = tk.Label(message, text='', bg=BG, fg=FG)
        self.video_message.pack()
        self.video_reassurance = tk.Label(message, text='', bg=BG, fg=MUTED)
        self.video_reassurance.pack(pady=(18, 0))
        self.local_video = tk.Frame(self.video, bg=BG, highlightthickness=0)
        self.video.update_idletasks()
        self.video_window = self.video.winfo_id()
        self.preview_window = self.local_video.winfo_id()
        self.confirmation = tk.Canvas(self.root, bg=BG, highlightthickness=0)
        self.confirmation.bind('<Configure>', lambda event: self.draw_confirmation())
        self.confirmation_signature = None
        self.confirmation_images = []
        self.build_remote_help()
        self.build_settings()
        self.build_usb_setup()
        self.build_tv_setup()

    def text(self, key, **values):
        language = 'en' if self.setup_stage in ('wifi', 'wifi_ready', 'server') else self.language
        return translate(language, key, **values)

    def resize(self, event):
        if event.widget == self.root and not self.closed:
            self.fit_text()
            if self.model.state in (State.CONFIRMING, State.CONFIRM_CALLBACK, State.REQUESTING_CALLBACK):
                self.draw_confirmation()

    def fit_text(self):
        """Fit longer translations and scripts into the available display width."""
        width = max(700, self.root.winfo_width() - 80)
        self.video_message.configure(text=self.text('no_remote_video'))
        self.video_reassurance.configure(text=self.text('audio_continues'))
        signature = (width, self.language, *(w.cget('text') for w in [self.title, self.name, self.subtitle, self.video_message, self.video_reassurance, self.call_name]))
        if signature == self.layout_signature:
            return
        self.layout_signature = signature
        name_size = (28, 19) if self.setup_stage == 'wifi_ready' else (36, 22)
        for widget, maximum, minimum, limit in [(self.title, 32, 19, width), (self.name, *name_size, width), (self.video_message, 32, 22, width - 40)]:
            size = maximum
            font = tkfont.Font(self.root, family=self.font_family, size=size, weight='bold')
            while font.measure(widget.cget('text')) > limit and size > minimum:
                size -= 1
                font.configure(size=size)
            widget.configure(font=(self.font_family, size, 'bold'), wraplength=limit)
            image = self.text_renderer.photo(widget.cget('text'), self.font_family, size, BG, FG, limit, True)
            widget.configure(image=image if image else '')
            widget.image = image
        self.subtitle.configure(font=(self.font_family, 19), wraplength=width)
        image = self.text_renderer.photo(self.subtitle.cget('text'), self.font_family, 19, BG, MUTED, width)
        self.subtitle.configure(image=image if image else '')
        self.subtitle.image = image
        self.video_reassurance.configure(font=(self.font_family, 22), wraplength=width - 40)
        image = self.text_renderer.photo(self.video_reassurance.cget('text'), self.font_family, 22, BG, MUTED, width - 40)
        self.video_reassurance.configure(image=image if image else '')
        self.video_reassurance.image = image
        self.fit_call_name()

    def fit_call_name(self):
        """Keep even long display names on one line within the existing top bar."""
        width = max(100, self.root.winfo_width() - 552)
        text, size = self.call_name.cget('text'), 28
        font = tkfont.Font(self.root, family=self.font_family, size=size, weight='bold')
        while font.measure(text) > width and size > 18:
            size -= 1
            font.configure(size=size)
        if font.measure(text) > width:
            while text and font.measure(text + '…') > width:
                text = text[:-1]
            text += '…'
        image = self.text_renderer.photo(text, self.font_family, size, BG, FG, width, True)
        # Native shaping can measure differently from Tk, especially for complex
        # scripts. Check the actual image so wrapping cannot enlarge the bar.
        while image and image.height() > 52 and size > 18:
            size -= 1
            image = self.text_renderer.photo(text, self.font_family, size, BG, FG, width, True)
        shortened = text.rstrip('…')
        while image and image.height() > 52 and shortened:
            shortened = shortened[:-1]
            image = self.text_renderer.photo(shortened + '…', self.font_family, size, BG, FG, width, True)
        self.call_name.configure(image=image if image else '', font=(self.font_family, size, 'bold'))
        self.call_name.image = image

    def layout_call_header(self, state, contact):
        """Reuse the icon bar during video; restore the larger prompts elsewhere."""
        if state == State.IN_CALL and not self.setup_stage:
            self.title.pack_forget()
            self.call_name.configure(text=contact['name'] if contact else self.text('in_call'))
            self.call_name.grid(row=0, column=1, sticky='ew', padx=12)
        else:
            self.call_name.grid_remove()
            self.call_name.configure(text='')
            if not self.title.winfo_manager():
                self.title.pack(before=self.body, pady=(16, 8))

    def update_video_message(self):
        if not self.setup_stage and self.model.state == State.IN_CALL:
            self.local_video.place(relx=1, rely=1, relwidth=.2, relheight=.2, anchor='se')
            self.local_video.lift()
        else:
            self.local_video.place_forget()
        visible = not self.setup_stage and self.model.state == State.IN_CALL and bool(self.engine) and not self.engine.incoming_video_active()
        if visible == self.missing_video_visible:
            return
        self.missing_video_visible = visible
        if visible:
            self.missing_video.place(x=0, y=0, relwidth=1, relheight=.8)
            self.missing_video_bottom.place(x=0, rely=.8, relwidth=.8, relheight=.2)
            self.missing_video.lift()
            self.missing_video_bottom.lift()
        else:
            self.missing_video.place_forget()
            self.missing_video_bottom.place_forget()

    def draw_reset(self):
        self.avatar.delete('all')
        self.current_text_images = []
        width, height = max(700, self.avatar.winfo_width()), max(120, self.avatar.winfo_height())
        for x, color, label, symbol in [(width*.3, GREEN, self.text('reset'), '✓'),
                                        (width*.7, RED, self.text('keep_configuration'), '×')]:
            y = height*.42
            self.avatar.create_oval(x-54, y-54, x+54, y+54, outline=color, width=4)
            self.avatar.create_text(x, y, text=symbol, fill=color, font=('Segoe UI', 48))
            image = self.text_renderer.photo(label, self.font_family, 22, BG, color, int(width*.4), True)
            self.current_text_images.append(image)
            self.avatar.create_image(x, y+90, image=image)

    def draw_wifi_confirmation(self):
        self.avatar.delete('all')
        width, height = max(700, self.avatar.winfo_width()), max(120, self.avatar.winfo_height())
        x, y, radius = width / 2, height * .38, min(70, height * .25)
        self.avatar.create_oval(x-radius, y-radius, x+radius, y+radius, outline=GREEN, width=5)
        self.avatar.create_text(x, y, text='✓', fill=GREEN, font=('Segoe UI', 48))
        seconds = max(0, math.ceil((self.setup_continue_at or time.monotonic()) - time.monotonic()))
        self.avatar.create_text(x, height * .82, text=str(seconds), fill=FG, font=('Segoe UI', 36, 'bold'))
        self.setup_confirmation_seconds = seconds

    def draw_connectivity(self, registered):
        self.update_remote_help()
        c = self.connectivity
        server = registered and time.monotonic() - self.server_seen < 16
        network = self.network_connected
        remote = getattr(getattr(self, 'presenter_input', None), 'connected', None)
        battery = getattr(getattr(self, 'presenter_input', None), 'battery', None)
        charger = getattr(getattr(self, 'presenter_input', None), 'charger_connected', None) is True
        signature = (network, server, remote, battery, charger, self.language)
        if self.connection_drawn == signature:
            return
        self.connection_drawn = signature
        c.delete('all')
        colors = [GREEN, GREEN if network else RED if network is False else MUTED, GREEN if server else RED]
        self.network_image = self.icon_renderer.connectivity(168, 30, colors, BG)
        c.create_image(78, 0, anchor='nw', image=self.network_image, tags='network-status')
        color = GREEN if remote is True else RED if remote is False else MUTED
        self.remote_image = self.icon_renderer.bluetooth(22, color, BG, remote)
        c.create_image(36, 4, anchor='nw', image=self.remote_image, tags='remote-status')
        self.battery_image = self.icon_renderer.battery(battery, BG, charger)
        c.create_image(0, 4, anchor='nw', image=self.battery_image, tags='remote-battery')

    def render_setup_feedback(self):
        label = self.setup_feedback_label
        if self.setup_stage not in ('wifi', 'server') or not getattr(self, 'setup_feedback', False):
            label.pack_forget()
            return
        width = max(400, self.root.winfo_width()-80)
        text = self.text('help')
        if self.setup_stage == 'server':
            text = self.text('server') + ' — ' + (self.text('offline') if self.setup_feedback == 'server_unavailable' else text)
        picture = self.text_renderer.photo(text, self.font_family, 20, BG, RED, width, True)
        label.configure(text=text, image=picture if picture else '', wraplength=width,
                        font=(self.font_family, 20, 'bold'))
        label.image = picture
        label.pack(before=self.body, pady=(0, 10))

    def render(self):
        """Render the model on Tk's thread; keep the video surface alive through call transitions."""
        if self.closed:
            return
        if self.update_usb_setup() or self.update_pairing_page():
            return
        if self.model.state not in (State.HOME, State.CONFIRMING, State.CONFIRM_CALLBACK) or self.setup_stage:
            self.settings_open = False
            self.settings_hold.clear()
        if self.render_tv_setup():
            return
        if self.render_settings():
            return
        self.update_remote_help()
        state, contact = self.model.state, self.model.contact or self.model.selected
        # Carousel names live inside every card, including the selected one.
        # Retain the separate name for ringing, outgoing calls and setup.
        if state == State.HOME and not self.setup_stage:
            self.name.grid_remove()
        else:
            self.name.grid()
        self.subtitle.grid()
        self.layout_call_header(state, contact)
        self.render_setup_feedback()
        if state != State.HOME or self.setup_stage:
            self.draw_corner_notification(0)
        self.update_video_message()
        if state in (State.CONFIRMING, State.CONFIRM_CALLBACK, State.REQUESTING_CALLBACK) and not self.setup_stage:
            self.confirmation.place(x=0, y=0, relwidth=1, relheight=1)
            tk.Misc.lift(self.confirmation)
            self.draw_confirmation()
            return
        self.confirmation.place_forget()
        self.confirmation_signature = None
        self.confirmation_images = []
        if state == State.HOME and self.notice == 'offline' and self.contact_online(contact):
            self.notice = ''
        registered = bool(self.engine and self.engine.registered)
        self.draw_connectivity(registered)
        if self.setup_stage:
            self.name.configure(text='')
            self.subtitle.configure(text='')
            if self.setup_stage == 'reset':
                self.video.pack_forget()
                self.home.pack(fill='both', expand=True)
                self.title.configure(text=self.text('factory_reset'))
                self.draw_reset()
            elif self.setup_stage == 'wifi_ready':
                self.video.pack_forget()
                self.home.pack(fill='both', expand=True)
                self.title.configure(text=self.text('wifi_connected'))
                self.name.configure(text=self.text('server_qr_next'))
                self.draw_wifi_confirmation()
            else:
                self.home.pack_forget()
                self.video.pack(fill='both', expand=True)
                self.title.configure(text='Scan the Wi-Fi QR code' if self.setup_stage == 'wifi' else 'Scan the server QR code')
            self.fit_text()
            return
        if state == State.IN_CALL:
            self.home.pack_forget()
            self.video.pack(fill='both', expand=True)
            self.carousel_motion = None
            self.ringing_started = None
            self.title.configure(text=contact['name'] if contact else self.text('in_call'))
        else:
            self.video.pack_forget()
            self.home.pack(fill='both', expand=True)
            self.draw_avatar(contact)
            self.name.configure(text='' if state == State.HOME else contact['name'] if contact else self.text('family'))
            self.title.configure(text=self.text({State.HOME:'choose', State.CALLING:'calling',
                                                State.RINGING:'incoming', State.CONNECTING:'connecting',
                                                State.STOPPING:'ending'}[state]))
            if state == State.HOME and self.notice == 'callback_requested':
                self.title.configure(text=self.text('callback_requested'))
            elif state == State.HOME and self.callback_alert:
                self.title.configure(text=f"↩ {self.callback_alert[0]} · {self.text('online')}")
            if state == State.HOME:
                subtitle = self.text(self.notice) if self.notice and self.notice != 'callback_requested' else ('' if contact and registered else self.text('connecting') if contact else self.text('empty'))
            elif state == State.RINGING:
                subtitle = self.text('countdown', seconds=max(1, math.ceil(self.model.deadline-time.monotonic()))) if self.model.deadline else 'ENTER  '+self.text('answer')
            else:
                subtitle = self.text('wait')
            self.subtitle.configure(text=subtitle)
            if state == State.HOME and not subtitle:
                self.subtitle.grid_remove()
        self.fit_text()
