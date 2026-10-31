"""Application composition and resource lifetimes; controllers own individual workflows."""
import argparse
import logging
from pathlib import Path
import queue
import re
import threading
import tkinter as tk
import tkinter.font as tkfont

from zmala_terminal.common.configuration import Configuration, ROOT
from zmala_terminal.common.engine import Engine, QRScanner
from zmala_terminal.common.provisioning import Enrollment
from zmala_terminal.common.maintenance import MaintenanceAgent
from zmala_terminal.common.wifi import forget_wifi
from zmala_terminal.common.model import TerminalModel
from zmala_terminal.common.localization import LANGUAGES, font_family
from zmala_terminal.common.local_settings import SettingsHold, SettingsDraft
from zmala_terminal.common.idle_return import IdleReturn, IdleCountdown
from zmala_terminal.common.settings_control import SettingsControl
from zmala_terminal.common.text_renderer import TextRenderer
from zmala_terminal.common.icons import IconRenderer
from zmala_terminal.common.portrait_animation import PortraitAnimation
from zmala_terminal.common.missed_calls import MissedCallsStore
from zmala_terminal.common.platform_services import create_platform_services

from zmala_terminal.common.theme import BG
from zmala_terminal.common.ui.display import TerminalDisplay
from zmala_terminal.common.setup_flow import ProvisioningFlow
from zmala_terminal.common.call_control import CallControl
from zmala_terminal.common.management import ManagementLoop
from zmala_terminal.common.input_control import InputControl
from zmala_terminal.common.configuration_control import ConfigurationControl

class Terminal(InputControl, ConfigurationControl, IdleReturn, SettingsControl,
               TerminalDisplay, ProvisioningFlow, CallControl, ManagementLoop):
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
        self.product_icon = tk.PhotoImage(file=str(ROOT / 'common/assets/zmala-icon.png'))
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
        services = self.make_platform_services()
        self.case_fan = services.fan
        self.usb_power = services.usb_power
        self.tv_control = services.television
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
        self.portrait_animation_target = None
        self.portrait_animation = PortraitAnimation(self, ROOT / 'data')
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
    def make_platform_services(self):
        return create_platform_services(ROOT)

    def make_configuration(self, bootstrap):
        return Configuration(bootstrap=bootstrap, cache=self.cache_path)

    def make_engine(self, config):
        return Engine(config, self.call_event, self.registration_event, self.video_window,
                      profile=self.profile, on_message=self.message_event, preview_window=self.preview_window)

    def make_scanner(self):
        return QRScanner(self.qr_found, self.video_window, self.profile)

    def make_maintenance(self, configuration):
        return MaintenanceAgent(configuration)

    def close(self):
        """Cancel workers and release native consumers before destroying their Tk surfaces."""
        if self.closed:
            return
        self.closed = True
        self.portrait_animation.close()
        if getattr(self, 'action_sounds', None):
            self.action_sounds.close()
        self.case_fan.close()
        self.usb_power.close()
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

# @llr LLR-TERM-START-005
def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--fullscreen', action='store_true')
    parser.add_argument('--bootstrap', type=Path, default=ROOT / 'data/terminal.json')
    parser.add_argument('--profile', default='terminal', help='Separate runtime/cache profile for an additional terminal')
    parser.add_argument('--unconfigured', action='store_true', help='Start fresh in this profile, with camera QR setup')
    parser.add_argument('--wifi-mode', choices=['existing-link', 'connect'], default='existing-link', help='Shared-PC test link, or actually join scanned Wi-Fi using the operating system network manager')
    args = parser.parse_args(argv)
    if not re.fullmatch(r'[a-z][a-z0-9_-]{0,40}', args.profile):
        parser.error('Profile must use lowercase letters, digits, - or _.')
    (ROOT / 'data').mkdir(exist_ok=True)
    from zmala_terminal.common.runtime_logging import configure
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


if __name__ == '__main__':
    main()
