"""Wi-Fi/server QR enrollment and reset. Generation IDs discard work from a prior enrollment."""
import logging
import math
import threading
import time
from zmala_terminal.common.model import State, TerminalModel
from zmala_terminal.common.provisioning import parse_wifi, parse_server
from zmala_terminal.common.wifi import connect_wifi, forget_wifi
from zmala_terminal.common.theme import RED, ACCENT, GREEN


class ProvisioningFlow:
    def stop_scanner(self):
        if self.scanner:
            self.scanner.close()
            self.scanner = None

    def iterate_scanner(self):
        if not self.scanner:
            return
        try:
            self.scanner.iterate()
        except Exception:
            logging.exception('Camera QR worker failed; keeping the setup screen open')
            self.stop_scanner()
            self.setup_error_until = time.monotonic() + 5
            self.setup_feedback = True
            self.render()

    def update_setup_display(self, now):
        if self.needs_c20() or self.needs_pairing():
            return
        if self.setup_stage == 'wifi_ready':
            if now >= self.setup_continue_at:
                self.setup_stage = 'server'
                self.setup_continue_at = None
                self.setup_confirmation_seconds = None
                self.last_qr = ('', 0)
                self.render()
            elif max(0, math.ceil(self.setup_continue_at - now)) != self.setup_confirmation_seconds:
                self.draw_wifi_confirmation()
        if self.setup_stage in ('wifi', 'server'):
            color = RED if now < self.setup_error_until else ACCENT if self.setup_busy else GREEN
            border = (3, color)
            # Touching the native preview border every frame causes camera flicker.
            if border != self.video_border:
                self.video.configure(highlightthickness=3, highlightbackground=color)
                self.video_border = border
            if not self.scanner and not self.setup_busy and now > self.setup_error_until:
                self.start_scanner()
        elif self.video_border[0] != 0:
            self.video.configure(highlightthickness=0)
            self.video_border = (0, None)

    def start_scanner(self):
        if self.closed or self.setup_stage not in ('wifi', 'server') or self.scanner or self.needs_c20() or self.needs_pairing():
            return
        if (self.enrollment.value or {}).get('wifi_cleanup'):
            self.start_wifi_cleanup()
            return
        ready = getattr(self, 'usb_media_ready', None)
        if ready and not ready():
            return
        self.render()
        self.root.update_idletasks()
        try:
            self.scanner = self.make_scanner()
        except Exception:
            self.setup_error_until = time.monotonic() + 4
            logging.exception('Camera QR scanner could not start')
            self.setup_feedback = True
            self.render()

    def factory_reset(self):
        """Invalidate workers first, then erase enrollment and start setup with a fresh model."""
        if self.model.state != State.HOME:
            return
        self.generation += 1
        self.setup_cancelled.set()
        self.setup_cancelled = threading.Event()
        if self.maintenance:
            self.maintenance.stop()
            self.maintenance = None
        if self.configuration:
            self.configuration.deactivate(erase=True)
        self.configuration = None
        if self.engine:
            self.engine.close()
            self.engine = None
        self.stop_scanner()
        wifi = (self.enrollment.value or {}).get('wifi', {})
        self.enrollment.reset(wifi, language=self.language)
        self.remote_test.reset()
        self.tv_setup_checked = False
        if self.tv_check:
            self.tv_check.close()
            self.tv_check = None
        (self.enrollment.path.parent / 'tv-check.json').unlink(missing_ok=True)
        self.setup_feedback = False
        self.missed_calls_store.clear()
        self.model = TerminalModel()
        self.pending_config = None
        self.engine_retry_at = 0
        self.callback_requests = []
        self.callback_seen.clear()
        self.callback_alert = None
        self.callback_serial += 1
        self.current_settings = {}
        self.server_seen = 0
        self.last_registration = False
        self.settings_hold.clear()
        self.settings_open = False
        self.setup_stage = 'wifi'
        self.setup_continue_at = None
        self.setup_confirmation_seconds = None
        self.worker_busy = False
        self.setup_busy = False
        self.render()
        self.start_scanner()

    def start_wifi_cleanup(self):
        wifi = (self.enrollment.value or {}).get('wifi_cleanup')
        if wifi and not self.setup_busy:
            self.setup_busy = True
            generation = self.generation
            def forget_worker():
                try:
                    forget_wifi(wifi, self.profile)
                    self.messages.put(('setup', (generation, 'forgot', None)))
                except Exception:
                    logging.exception('Removing the terminal Wi-Fi profile failed')
                    self.messages.put(('setup', (generation, 'error', None)))
            threading.Thread(target=forget_worker, daemon=True).start()

    def qr_found(self, value):
        if self.needs_pairing():
            return
        if self.setup_stage not in ('wifi', 'server') or self.setup_busy or (self.enrollment.value or {}).get('wifi_cleanup'):
            return
        now = time.monotonic()
        if value == self.last_qr[0] and now - self.last_qr[1] < 3:
            return
        self.last_qr = value, now
        try:
            decoded = parse_wifi(value) if self.setup_stage == 'wifi' else parse_server(value)
        except (ValueError, TypeError, KeyError):
            self.setup_error_until = now + 2
            logging.warning('QR code is not valid for the current setup step')
            self.setup_feedback = True
            self.render()
            return
        stage, generation, cancelled = self.setup_stage, self.generation, self.setup_cancelled
        self.setup_busy = True
        self.setup_error_until = 0
        def setup_worker():
            try:
                if stage == 'wifi':
                    result = connect_wifi(decoded, self.profile, self.wifi_mode, cancelled)
                else:
                    candidate = self.make_configuration(decoded)
                    result = (candidate, candidate.fetch(persist=False))
                self.messages.put(('setup', (generation, stage, result)))
            except Exception as error:
                # Do not log QR contents, network passwords or device tokens.
                logging.warning('Terminal %s setup failed (%s)', stage, type(error).__name__)
                self.messages.put(('setup', (generation, 'error', 'server' if stage == 'server' else None)))
        threading.Thread(target=setup_worker, daemon=True).start()

    def setup_result(self, generation, kind, result):
        """Commit enrollment only on the UI thread and only for the still-current setup generation."""
        if generation != self.generation or self.closed:
            return
        self.setup_busy = False
        self.setup_feedback = kind == 'error'
        if kind == 'forgot':
            self.enrollment.cleanup_done()
        elif kind == 'wifi':
            self.enrollment.set_wifi(result)
            self.stop_scanner()
            self.setup_stage = 'wifi_ready'
            self.setup_continue_at = time.monotonic() + 10
            self.setup_confirmation_seconds = None
            self.last_qr = ('', 0)
        elif kind == 'server':
            candidate, config = result
            candidate.persist(config)
            self.enrollment.set_server(candidate.bootstrap)
            self.stop_scanner()
            self.configuration = candidate
            self.setup_stage = None
            self.server_seen = time.monotonic()
            self.last_poll = 0
            if not self.begin_tv_setup(config):
                self.apply_config(config)
                self.maintenance = self.make_maintenance(candidate)
        elif kind == 'error':
            self.setup_error_until = time.monotonic() + 3
            if result == 'server':
                self.setup_feedback = 'server_unavailable'
        self.render()
        if kind == 'forgot':
            self.start_scanner()
