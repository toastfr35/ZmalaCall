"""Installer-only C20 connection guide, before Bluetooth and QR enrollment."""
import tkinter as tk
from zmala_terminal.common.configuration import ROOT
from zmala_terminal.common.model import State
from zmala_terminal.linux.c20_status import C20Status
from zmala_terminal.common.theme import BG


class UsbSetupView:
    def build_usb_setup(self):
        self.c20_status = C20Status()
        self.usb_setup_visible = False
        self.usb_setup_source = None
        self.usb_setup_size = None
        self.usb_setup = tk.Frame(self.root, bg=BG)
        self.usb_setup_picture = tk.Label(self.usb_setup, bg=BG, borderwidth=0)
        self.usb_setup_picture.place(relx=.5, rely=.5, anchor='center')

    # @llr TLLR020
    def needs_c20(self):
        return (self.setup_stage in ('wifi', 'wifi_ready', 'server')
                and self.model.state == State.HOME and self.c20_status.read() is False)

    def update_usb_setup(self):
        if not self.needs_c20():
            if self.usb_setup_visible:
                self.usb_setup_visible = False
                self.usb_setup.place_forget()
                self.root.after_idle(self.render)
            return False
        self.stop_scanner()
        self.usb_setup_visible = True
        size = (max(1, self.root.winfo_width()), max(1, self.root.winfo_height()))
        if size != self.usb_setup_size:
            from PIL import Image, ImageOps, ImageTk
            if self.usb_setup_source is None:
                with Image.open(ROOT / 'common/assets/usb-setup.png') as source:
                    self.usb_setup_source = source.copy()
            picture = ImageTk.PhotoImage(ImageOps.contain(self.usb_setup_source, size,
                                          Image.Resampling.LANCZOS), master=self.root)
            self.usb_setup_picture.configure(image=picture)
            self.usb_setup_picture.image = picture
            self.usb_setup_size = size
        self.usb_setup.place(x=0, y=0, relwidth=1, relheight=1)
        self.usb_setup.lift()
        return True
