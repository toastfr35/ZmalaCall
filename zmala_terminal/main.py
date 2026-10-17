"""Application composition, configuration changes and physical-button input."""
import argparse
import logging
from pathlib import Path
import queue
import re
import threading
import time
import tkinter as tk
import tkinter.font as tkfont

from configuration import Configuration, ROOT
from engine import Engine, QRScanner
from provisioning import Enrollment
from maintenance import MaintenanceAgent
from wifi import forget_wifi
from model import State, TerminalModel
from localization import LANGUAGES, font_family
from carousel import CarouselMotion
from local_settings import SettingsHold, SettingsDraft
from idle_return import IdleReturn, IdleCountdown
from settings_control import SettingsControl
from text_renderer import TextRenderer
from icons import IconRenderer
from missed_calls import MissedCallsStore
from platforms.tv_control import TVControl
from platforms.presenter_input import PresenterInput
from volume_control import VolumeControl
from platforms.argon_fan import ArgonFan

from theme import BG
from ui.display import TerminalDisplay
from setup_flow import ProvisioningFlow
from call_control import CallControl
from management import ManagementLoop

class Terminal(IdleReturn, SettingsControl, TerminalDisplay, ProvisioningFlow, CallControl, ManagementLoop):
    """Own terminal state/lifetimes; compose display, setup, calls and polling."""
    def __init__(self, fullscreen=False, bootstrap=ROOT / 'data/terminal.json', profile='terminal', unconfigured=False, wifi_mode='existing-link'):
        self.create_window(fullscreen)
        self.initialize_state(profile, wifi_mode)
        self.restore_enrollment(bootstrap, unconfigured)
        self.build_ui()
        self.bind_inputs()
        self.start_services()

    def create_window(self, fullscreen):
        self.root = tk.Tk()
        self.root.title('ZmalaCall')
        self.product_icon = tk.PhotoImage(file=str(ROOT / 'assets/zmala-icon.png'))
        self.root.iconphoto(True, self.product_icon)
        self.root.geometry('1100x800')
        self.root.minsize(900, 620)
        self.root.configure(bg=BG)
        self.root.attributes('-fullscreen', fullscreen)
        self.root.protocol('WM_DELETE_WINDOW', self.close)
    def initialize_state(self, profile, wifi_mode):
        """Initialize owned state before creating controllers or starting workers."""
        self.model = TerminalModel()
        self.settings_open = False
        self.idle_countdown = IdleCountdown()
        self.settings_draft = SettingsDraft()
        self.settings_hold = SettingsHold()
        self.key_release_jobs = {}
        self.pointer_serial = 0
        self.engine = None
        self.case_fan = ArgonFan()
        self.pending_config = None
        self.engine_retry_at = 0
        self.current_settings = {}
        self.current_photos = []
        self.network_connected = None
        self.network_worker_busy = False
        self.server_seen = 0
        self.dial_serial = 0
        self.presence_stale = True
        self.connection_drawn = None
        self.carousel_motion = None
        self.ringing_started = None
        self.language = 'en'
        self.available_fonts = set(tkfont.families(self.root))
        self.font_family = font_family(self.language, self.available_fonts)
        self.layout_signature = None
        self.text_renderer = TextRenderer(self.root)
        self.icon_renderer = IconRenderer(self.text_renderer)
        self.current_text_images = []
        self.closed = False
        self.messages = queue.Queue()
        self.worker_busy = False
        self.last_poll = 0
        self.diagnostics = {}
        self.profile = profile
        self.cache_path = ROOT / 'data' / ('config-cache.json' if profile == 'terminal' else f'config-cache-{profile}.json')
        self.enrollment = Enrollment(ROOT / 'data' / profile)
        self.missed_calls_store = MissedCallsStore(self.enrollment.path.parent / 'missed-calls.json')
        self.wifi_mode = wifi_mode
        self.generation = 0
        self.setup_stage = self.enrollment.stage
        self.scanner = None
        self.setup_busy = False
        self.setup_cancelled = threading.Event()
        self.setup_error_until = 0
        self.setup_continue_at = None
        self.setup_confirmation_seconds = None
        self.last_qr = ('', 0)
        self.tv_control = TVControl()
        self.keys_down = set()
        self.configuration = None
        self.maintenance = None
        self.notice = ''
        self.last_registration = False
        self.outgoing_deadline = None
        self.callback_requests = []
        self.callback_seen = set()
        self.callback_alert = None
        self.last_button = 0
        self.callback_serial = 0
        self.callback_notice_until = 0
        self.last_key = {}
    def restore_enrollment(self, bootstrap, unconfigured):
        if unconfigured:
            # The test launcher always starts fresh, within its own profile.
            if self.enrollment.value and self.enrollment.value.get('wifi'):
                forget_wifi(self.enrollment.value['wifi'], self.profile)
            self.enrollment.reset()
            self.missed_calls_store.clear()
            self.cache_path.unlink(missing_ok=True)
            self.setup_stage = 'wifi'
        saved_language = (self.enrollment.value or {}).get('language')
        if isinstance(saved_language, str) and saved_language in LANGUAGES:
            self.language = saved_language
            self.font_family = font_family(self.language, self.available_fonts)
        if not self.setup_stage:
            saved = (self.enrollment.value or {}).get('bootstrap')
            if saved or Path(bootstrap).exists():
                self.configuration = self.make_configuration(saved or bootstrap)
            else:
                self.enrollment.reset()
                self.setup_stage = 'wifi'
    def bind_inputs(self):
        self.root.bind('<Configure>', self.resize)
        for key, button in [('Left', 'left'), ('Prior', 'left'), ('Right', 'right'), ('Next', 'right'), ('Return', 'green'), ('Escape', 'red')]:
            self.root.bind_all('<' + key + '>', lambda event, b=button: self.keypress(b))
            self.root.bind_all('<KeyRelease-' + key + '>', lambda event, b=button: self.queue_keyrelease(b))
        self.root.bind('<FocusOut>', lambda e: self.input_focus_lost())
        self.root.bind_all('<KeyPress>', self.other_key)
        self.root.bind('<F11>', self.toggle_fullscreen)
        self.volume_control = VolumeControl(self.root,
                                            lambda: bool(self.engine) and not self.setup_stage and not self.settings_open,
                                            self.volume_activity)
        self.presenter_input = PresenterInput(self.root, self.keypress, self.keyrelease,
                                               self.pointer_button, self.volume_control.motion,
                                               self.remote_test_event)

    def pointer_button(self, held):
        """Pointer follows the same wake-only first press as the other buttons."""
        if self.setup_stage == 'tv' or self.remote_setup_blocked():
            return
        if held and 'pointer' in self.keys_down:
            return
        self.pointer_serial += 1
        if not held:
            self.keys_down.discard('pointer')
            self.volume_control.pointer(False)
            return
        self.keys_down.add('pointer')
        self.cancel_settings_hold()
        self.last_button = time.monotonic()
        generation, state, serial = self.generation, self.model.state, self.pointer_serial
        if not self.tv_control.handle_button(
                lambda: self.messages.put(('tv-pointer', (generation, state, serial))),
                preserve_restore=state in (State.RINGING, State.CONNECTING, State.IN_CALL)):
            self.volume_control.pointer(True)

    def pointer_visible(self, generation, state, serial):
        # A released/repressed pointer or a newly arrived call invalidates a
        # delayed visibility check; it must never start volume by itself.
        if (not self.closed and generation == self.generation and state == self.model.state
                and serial == self.pointer_serial and 'pointer' in self.keys_down):
            self.volume_control.pointer(True)

    def volume_activity(self):
        self.last_button = time.monotonic()
    def start_services(self):
        cached = self.configuration.cached() if self.configuration else None
        if cached and not self.begin_tv_setup(cached):
            self.apply_config(cached)
        self.render()
        if self.setup_stage:
            self.root.after(100, self.start_scanner)
        elif self.configuration:
            self.maintenance = self.make_maintenance(self.configuration)
        self.root.after(20, self.tick)

    # Keep dependency creation here so real hardware and isolated test engines
    # use the same controllers without importing one another's test substitutes.
    def make_configuration(self, bootstrap):
        return Configuration(bootstrap=bootstrap, cache=self.cache_path)

    def make_scanner(self):
        return QRScanner(self.qr_found, self.video_window, self.profile)

    def make_maintenance(self, configuration):
        return MaintenanceAgent(configuration)

    def other_key(self, event):
        self.cancel_settings_hold()
        if self.settings_open or self.settings_hold.capturing:
            return
        if self.model.state in (State.CONFIRMING, State.CONFIRM_CALLBACK, State.REQUESTING_CALLBACK):
            self.press('cancel')
            return 'break'

    def toggle_fullscreen(self, event):
        if self.model.state in (State.CONFIRMING, State.CONFIRM_CALLBACK, State.REQUESTING_CALLBACK):
            self.press('cancel')
        else:
            self.root.attributes('-fullscreen', not self.root.attributes('-fullscreen'))
        return 'break'

    def keypress(self, button):
        if self.remote_setup_blocked():
            return 'break'  # Keyboard/X11 copies must not pass the physical test.
        now = time.monotonic()
        # Repeated key-downs cannot restart a hold or repeat an action.
        release_job = self.key_release_jobs.pop(button, None)
        if release_job is not None:
            self.root.after_cancel(release_job)
        if button in self.keys_down:
            return 'break'
        self.keys_down.add(button)
        self.last_button = now  # Even a consumed/debounced press resets idle return.
        if self.tv_setup_button(button):
            return 'break'
        if now - self.last_key.get(button, 0) > .08:
            # Only physical input reveals the TV; timer-driven cancellation
            # still reaches press() directly. Workers return through Tk's queue.
            generation, state = self.generation, self.model.state
            if not self.tv_control.handle_button(
                    lambda: self.messages.put(('tv-button', (generation, state, button))),
                    preserve_restore=state in (State.RINGING, State.CONNECTING, State.IN_CALL)):
                self.press(button)
        self.last_key[button] = now
        return 'break'

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
        old_sip = self.model.config.get('sip') if self.model.config else None
        from audio_processing import requested_profile
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

    def configure_engine(self, config, old_sip, audio_profile):
        if (not self.engine or old_sip != config['sip'] or
                ('video_resolution' in config and self.engine.video_settings.resolution != config['video_resolution']) or
                getattr(self.engine, 'audio_profile', 'normal') != audio_profile):
            if self.engine:
                old, self.engine = self.engine, None
                old.close()
            self.engine = Engine(config, self.call_event, self.registration_event, self.video_window,
                                 profile=self.profile, on_message=self.message_event, preview_window=self.preview_window)
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

    def _press_action(self, button):
        self.last_button = time.monotonic()
        self.callback_alert = None
        if self.setup_stage:
            if self.setup_stage == 'reset' and button == 'red':
                self.setup_stage = None
                self.settings_open = True
                self.settings_hold.clear()
                self.render()
            elif self.setup_stage == 'reset' and button == 'green' and not self.setup_busy:
                self.factory_reset()
            return
        moving = self.model.state == State.HOME and button in ('left', 'right') and len(self.model.contacts) > 1
        if moving and self.carousel_motion:
            return
        if moving:
            self.carousel_motion = CarouselMotion(list(self.model.contacts), self.model.index % len(self.model.contacts),
                                                  -1 if button == 'left' else 1, time.monotonic())
        elif button in ('green', 'red'):
            self.carousel_motion = None
        confirming = self.model.state in (State.CONFIRMING, State.CONFIRM_CALLBACK)
        target = next((c for c in self.model.contacts if c['id'] == self.model.contact['id']), None) if confirming else self.model.selected
        unavailable = not self.contact_online(target) or confirming and not (self.engine and self.engine.registered)
        if button == 'green' and self.model.state == State.HOME and target and not self.contact_online(target):
            self.model.confirm_selected(False)
            self.missed_calls_store.save(self.model.config, self.model.notifications)
            self.render()
            return
        if button == 'green' and self.model.state == State.CONFIRMING and unavailable:
            if target:
                self.model.state = State.CONFIRM_CALLBACK
            else:
                self.model.ended()
                self.notice = 'unavailable'
            self.render()
            return
        action = self.model.button(button, bool(self.engine and self.engine.registered))
        if self.model.config:
            self.missed_calls_store.save(self.model.config, self.model.notifications)
        if self.model.state == State.HOME and button in ('left', 'right'):
            self.notice = ''
        self.action(action)
        self.render()

    def close(self):
        """Cancel workers and release native consumers before destroying their Tk surfaces."""
        if self.closed:
            return
        self.closed = True
        self.case_fan.close()
        self.presenter_input.close()
        self.volume_control.close()
        if self.tv_check:
            self.tv_check.close()
        self.tv_control.close()
        self.setup_cancelled.set()
        if self.maintenance:
            self.maintenance.stop()
        if self.configuration:
            self.configuration.deactivate()
        self.stop_scanner()
        if self.engine:
            self.engine.close()
        self.text_renderer.close()
        self.root.destroy()

    def run(self):
        self.root.mainloop()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--fullscreen', action='store_true')
    parser.add_argument('--bootstrap', type=Path, default=ROOT / 'data/terminal.json')
    parser.add_argument('--profile', default='terminal', help='Separate runtime/cache profile for an additional terminal')
    parser.add_argument('--unconfigured', action='store_true', help='Start fresh in this profile, with camera QR setup')
    parser.add_argument('--wifi-mode', choices=['existing-link', 'connect'], default='existing-link', help='Shared-PC test link, or actually join scanned Wi-Fi using the operating system network manager')
    args = parser.parse_args()
    if not re.fullmatch(r'[a-z][a-z0-9_-]{0,40}', args.profile):
        parser.error('Profile must use lowercase letters, digits, - or _.')
    (ROOT / 'data').mkdir(exist_ok=True)
    from runtime_logging import configure
    configure(ROOT / 'data')
    application = None
    try:
        application = Terminal(args.fullscreen, args.bootstrap.resolve(), args.profile, args.unconfigured, args.wifi_mode)
        application.run()
    except Exception:
        logging.exception('Terminal startup failed')
        raise
    finally:
        if application is not None:
            application.close()
