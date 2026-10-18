"""Apply configuration on the UI thread; commit the revision only after native setup succeeds."""
import logging
import time
from zmala_terminal.common.localization import font_family
from zmala_terminal.common.model import State


class ConfigurationControl:
    # @llr TLLR084
    def apply_config(self, config):
        """Apply UI changes now; defer native graph/credential changes until the terminal is idle."""
        if self.setup_stage:
            return
        if not getattr(self, 'tv_setup_checked', True) and self.begin_tv_setup(config):
            self.render()
            return
        self.callback_requests = config.get('callbacks', [])
        # Framing only changes crop coordinates, not the SIP/media graph.
        if self.engine and getattr(self.engine, 'auto_framing', None):
            self.engine.auto_framing.configure(config.get('auto_framing', False))
        # Language changes apply even while a call is active; device changes wait.
        # @llr TLLR038
        self.language = config.get('language', 'en')
        self.font_family = font_family(self.language, self.available_fonts)
        self.root.title(f"ZmalaCall · ← → {self.text('select')} · Enter {self.text('call')}/{self.text('answer')} · Esc {self.text('end')}")
        if self.model.state != State.HOME:
            self.pending_config = config
            # Permission revocation cancels a pending auto-answer immediately.
            if self.model.state == State.RINGING:
                c = next((c for c in config['contacts'] if c['id'] == self.model.contact['id']), None)
                if not c or not c['can_receive']:
                    self.press('red')
                elif not config.get('auto_answer', c.get('auto_answer', False)):
                    self.model.deadline = None
            self.render()
            return
        self.carousel_motion = None
        if time.monotonic() < getattr(self, 'engine_retry_at', 0):
            self.pending_config = config
            return
        if not self.usb_media_ready():
            self.pending_config = config
            return
        old_sip = self.model.config.get('sip') if self.model.config else None
        from zmala_terminal.common.audio_processing import requested_profile
        # Recreate the native audio graph only while idle. In-call updates stay
        # pending above, and a new core restores the default canceller cleanly.
        try:
            self.configure_engine(config, old_sip, requested_profile(config))
        except Exception:
            logging.exception('Could not apply media configuration; retrying in five seconds')
            old, self.engine = self.engine, None
            if old:
                try:
                    old.close()
                except Exception:
                    logging.exception('Could not release failed media engine')
            self.pending_config = config
            self.engine_retry_at = time.monotonic() + 5
            self.diagnostics = {'registered': False}
            self.notice = 'unavailable'
            self.render()
            return
        if self.engine_retry_at and self.notice == 'unavailable':
            self.notice = ''
        self.engine_retry_at = 0
        self.pending_config = None
        self.model.configure(config)
        if old_sip is None or (old_sip['domain'].lower(), old_sip['username']) != tuple(self.missed_calls_store.account(config)):
            self.model.restore_notifications(self.missed_calls_store.load_counts(config))
        self.missed_calls_store.save(config, self.model.notifications)
        self.diagnostics = self.engine.diagnostics()
        self.render()

    # @llr TLLR083
    def configure_engine(self, config, old_sip, audio_profile):
        if (not self.engine or old_sip != config['sip'] or
                ('video_resolution' in config and self.engine.video_settings.resolution != config['video_resolution']) or
                getattr(self.engine.video_settings, 'fps', 15) != config.get('video_fps', 15) or
                getattr(self.engine, 'audio_profile', 'normal') != audio_profile):
            if self.engine:
                old, self.engine = self.engine, None
                old.close()
            self.engine = self.make_engine(config)
            if getattr(self, 'usb_power', None) and self.usb_power.enabled:
                # Wake the speaker before playing the incoming-call melody.
                self.engine.core_set_ring(self.engine.core, None)
            self.current_settings = dict(config.get('terminal_settings', {}))
        else:
            self.engine.config = config
            self.engine.core_refresh_registers(self.engine.core)
            settings = config.get('terminal_settings', {})
            if settings != self.current_settings:
                self.engine.apply_settings(settings)
                self.current_settings = dict(settings)
            self.engine.apply_speaker_volume()
            if hasattr(self.engine, 'apply_call_timeout'):
                self.engine.apply_call_timeout()
