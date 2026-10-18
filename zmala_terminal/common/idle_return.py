"""Monotonic browsing countdown and its small, bottom-edge Tk indicator."""
import logging
import tkinter as tk

from zmala_terminal.common.local_settings import SettingsDraft
from zmala_terminal.common.model import State


class IdleCountdown:
    def __init__(self):
        self.session = None
        self.seconds = None
        self.activity = None
        self.deadline = None
        self.expired = False
        self.anchor = None
        self.paused = False

    def tick(self, now, session, seconds, activity, eligible=True):
        """Return (remaining fraction, just expired); pause always gives a fresh interval."""
        changed = session is not self.session or seconds != self.seconds or activity != self.activity
        if (self.anchor is None or activity != self.activity or seconds != self.seconds or
                (eligible and self.paused) or (session is not self.session and self.session is not None)):
            self.anchor = now
        self.paused = not eligible
        self.session, self.seconds, self.activity = session, seconds, activity
        if changed:
            self.deadline = None
            self.expired = False
        if session is None or not seconds or not eligible:
            self.deadline = None
            return None, False
        if self.expired:
            return None, False
        if self.deadline is None:
            self.deadline = self.anchor + seconds
        remaining = self.deadline - now
        if remaining <= 0:
            self.expired = True
            return None, True
        # Keep the screen quiet until ten seconds of inactivity have elapsed.
        return (None if now < self.deadline - seconds + 10 else min(1.0, remaining / seconds)), False


class IdleReturn:
    def tick_tv_idle(self, now):
        session = self.tv_control.browsing_session()
        config = self.model.config or {}
        eligible = (bool(config) and self.setup_stage in (None, 'reset') and
                    not getattr(self, 'pairing_page_visible', False) and
                    not self.setup_busy and not self.settings_draft.busy and
                    not self.keys_down and self.model.state in
                    (State.HOME, State.CONFIRMING, State.CONFIRM_CALLBACK))
        fraction, expired = self.idle_countdown.tick(
            now, session, config.get('tv_idle_seconds', 30), self.last_button, eligible)
        if expired:
            # Cancel only idle UI drafts/confirmation. Calls and writes are never eligible.
            self.settings_open = False
            self.settings_draft = SettingsDraft()
            self.settings_hold.clear()
            self.setup_stage = None
            self.carousel_motion = None
            self.callback_alert = None
            self.notice = ''
            self.model.ended()
            self.render()
            logging.info('CEC: browsing idle timeout (%s seconds)', config.get('tv_idle_seconds', 30))
            self.tv_control.restore_browsing(session)
        self.draw_tv_idle(fraction)

    def draw_tv_idle(self, fraction):
        if not hasattr(self, 'tv_idle_bar'):
            self.tv_idle_bar = tk.Frame(self.root, bg='#388bff', borderwidth=0, highlightthickness=0)
            self.tv_idle_pixels = None
        pixels = round(self.root.winfo_width() * fraction) if fraction is not None else 0
        if pixels != self.tv_idle_pixels:
            self.tv_idle_pixels = pixels
            if pixels > 0:
                self.tv_idle_bar.place(x=0, rely=1, anchor='sw', width=pixels, height=3)
            else:
                self.tv_idle_bar.place_forget()
        if pixels > 0:
            self.tv_idle_bar.lift()
