# @test T-LLT-053
# @requirements LLR-TERM-SETUP-027, LLR-TERM-SETUP-029, LLR-TERM-SETUP-032, LLR-TERM-NET-005, LLR-TERM-UI-015, LLR-TERM-UI-023, LLR-TERM-UI-024, LLR-TERM-UI-025, LLR-TERM-CALL-013, LLR-TERM-CALL-014, LLR-TERM-VIDEO-012, LLR-TERM-POWER-017
# @environment portable
# @plan Use recording Tk widgets and controlled font/image metrics to exercise the display controller across call, setup and modal states. Verify persistent video handles, self-view geometry, an eight-second neutral first-video wait, its exact warning boundary, first-frame/stall behaviour, reset for a new call, localized text bounds, setup error visibility and modal precedence. Independently vary Wi-Fi, registration freshness, remote health and USB power and assert icon values/positions and cached redraws without opening a display or media devices.
# @pass Each state must select its specified surface and labels, preserve native surfaces and keep text bounded; drawing-command checks do not establish physical font quality or HDMI behavior.

from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from zmala_terminal.common.ui import display
from zmala_terminal.common.model import TerminalModel, State
from tests.terminal.LLT.test_terminal import config


def widget(**values):
    result = Mock()
    values = {'text': '', **values}
    result.configure.side_effect = lambda **kwargs: values.update(kwargs)
    result.cget.side_effect = lambda key: values.get(key, '')
    result.winfo_width.return_value = 1280
    result.winfo_height.return_value = 720
    result.winfo_manager.return_value = ''
    result.winfo_id.return_value = 101
    return result


def font(*args, **kwargs):
    size = [kwargs['size']]
    result = Mock()
    result.configure.side_effect = lambda **opts: size.__setitem__(0, opts['size'])
    result.measure.side_effect = lambda text: len(text)*size[0]/2
    return result


def fixture():
    v = display.TerminalDisplay()
    v.root = widget(); v.model = TerminalModel(); v.model.configure(config())
    v.setup_stage = None; v.language = 'fr'; v.font_family = 'Sans'; v.closed = False
    v.status_width = 246; v.layout_signature = None; v.missing_video_visible = False
    v.video_started_at = None; v.video_seen = False; v.video_message_key = 'no_remote_video'
    v.engine = Mock(registered=True); v.engine.incoming_video_active.return_value = True
    v.text_renderer = Mock(); v.text_renderer.photo.return_value = Mock(height=lambda: 30)
    for name in ('title', 'name', 'subtitle', 'call_name', 'video_message', 'video_reassurance',
                 'video', 'local_video', 'missing_video', 'missing_video_bottom', 'body', 'home',
                 'confirmation', 'avatar', 'setup_feedback_label', 'video_status_icon'):
        setattr(v, name, widget())
    v.text = lambda key, **values: key + (':'+str(values['seconds']) if values else '')
    return v


class DisplayStateTests(unittest.TestCase):
    def test_build_keeps_two_native_surfaces_and_routes_resize_events(self):
        v = fixture()
        for name in ('draw_corner_notification', 'build_remote_help', 'build_settings', 'build_usb_setup',
                     'build_tv_setup', 'draw_reset', 'draw_wifi_confirmation', 'draw_avatar', 'draw_confirmation'):
            setattr(v, name, Mock())
        v.usb_power = SimpleNamespace(enabled=True)
        with patch.object(display.tk, 'Frame', side_effect=lambda *a, **k: widget(**k)), \
                patch.object(display.tk, 'Canvas', side_effect=lambda *a, **k: widget(**k)), \
                patch.object(display.tk, 'Label', side_effect=lambda *a, **k: widget(**k)):
            v.build_ui()
        self.assertEqual(v.status_width, 306)
        self.assertIsNot(v.video, v.local_video)
        v.video.winfo_id.assert_called_once(); v.local_video.winfo_id.assert_called_once()
        callback = v.avatar.bind.call_args.args[1]
        for stage, target in [('reset', v.draw_reset), ('wifi_ready', v.draw_wifi_confirmation), (None, v.draw_avatar)]:
            v.setup_stage = stage; callback(None); target.assert_called_once()
        v.confirmation.bind.call_args.args[1](None)
        v.draw_confirmation.assert_called_once()
        for name in ('build_remote_help', 'build_settings', 'build_usb_setup', 'build_tv_setup'):
            getattr(v, name).assert_called_once()

    def test_installation_language_is_english_then_selected_language(self):
        v = fixture()
        with patch.object(display, 'translate', side_effect=lambda lang, key, **values: lang) as translate:
            for stage in ('wifi', 'wifi_ready', 'server'):
                v.setup_stage = stage
                self.assertEqual(display.TerminalDisplay.text(v, 'choose'), 'en')
            for stage in (None, 'reset'):
                v.setup_stage = stage
                self.assertEqual(display.TerminalDisplay.text(v, 'choose'), 'fr')
            self.assertEqual(translate.call_count, 5)

    def test_resize_ignores_children_and_closed_windows(self):
        v = fixture(); v.fit_text = Mock(); v.draw_confirmation = Mock()
        v.resize(SimpleNamespace(widget=object())); v.fit_text.assert_not_called()
        v.closed = True; v.resize(SimpleNamespace(widget=v.root)); v.fit_text.assert_not_called()
        v.closed = False; v.model.state = State.CONFIRMING
        v.resize(SimpleNamespace(widget=v.root))
        v.fit_text.assert_called_once(); v.draw_confirmation.assert_called_once()

    def test_long_text_reflows_once_and_language_changes_preserve_media(self):
        v = fixture(); v.title.configure(text='Long text '*80); v.name.configure(text='Long name '*80)
        with patch.object(display.tkfont, 'Font', side_effect=font):
            v.fit_text()
            calls = v.text_renderer.photo.call_count
            v.fit_text(); self.assertEqual(v.text_renderer.photo.call_count, calls)
            v.language = 'en'; v.fit_text()
            self.assertGreater(v.text_renderer.photo.call_count, calls)
            self.assertEqual(v.title.cget('font')[1], 19)
            self.assertEqual(v.title.cget('wraplength'), 1200)
            v.setup_stage = 'wifi_ready'; v.layout_signature = None
            v.text_renderer.photo.return_value = None; v.fit_text()
            self.assertEqual(v.name.cget('font')[1], 19)
            self.assertEqual(v.name.cget('image'), '')
        v.engine.end.assert_not_called(); v.video.destroy.assert_not_called()

    def test_call_name_limits_both_measured_width_and_shaped_height(self):
        for width in (700, 1920):
            v = fixture(); v.root.winfo_width.return_value = width
            v.call_name.configure(text='Name with many characters '*20)
            v.text_renderer.photo.side_effect = lambda text, family, size, *args: Mock(height=lambda: 80 if size > 18 or len(text) > 4 else 30)
            with patch.object(display.tkfont, 'Font', side_effect=font):
                v.fit_call_name()
            self.assertLessEqual(v.call_name.image.height(), 52)
            self.assertEqual(v.call_name.cget('font')[1], 18)
            rendered = v.text_renderer.photo.call_args.args[0]
            self.assertTrue(rendered.endswith('…'))
            self.assertLessEqual(len(rendered), 4)
        v = fixture(); v.call_name.configure(text='Name')
        v.text_renderer.photo.side_effect = lambda text, family, size, *args: Mock(height=lambda: 80 if size > 20 else 30)
        with patch.object(display.tkfont, 'Font', side_effect=font):
            v.fit_call_name()
        self.assertEqual(v.call_name.cget('font')[1], 20)
        self.assertEqual(v.text_renderer.photo.call_args.args[0], 'Name')

    def test_status_icons_are_independent_and_usb_space_is_reserved(self):
        v = fixture(); v.connectivity = widget(); v.icon_renderer = Mock()
        v.update_remote_help = Mock(); v.connection_drawn = None; v.server_seen = 90
        v.presenter_input = SimpleNamespace(connected=True, battery=45, charger_connected=True)
        v.usb_power = SimpleNamespace(enabled=True, power_state=False)
        cases = [(False, True, display.RED, display.GREEN),
                 (True, False, display.GREEN, display.RED),
                 (None, True, display.MUTED, display.GREEN)]
        with patch.object(display.time, 'monotonic', return_value=100):
            for network, registered, network_color, server_color in cases:
                v.network_connected = network; v.draw_connectivity(registered)
                v.icon_renderer.connectivity.assert_called_with(168, 30, [display.GREEN, network_color, server_color], display.BG)
            v.icon_renderer.battery.assert_called_with(45, display.BG, True)
            v.icon_renderer.bluetooth.assert_called_with(22, display.GREEN, display.BG, True)
            v.icon_renderer.usb_power.assert_called_with(False, display.BG)
            positions = {c.kwargs['tags']: c.args[0] for c in v.connectivity.create_image.call_args_list}
            self.assertEqual(positions, {'usb-power': 0, 'remote-battery': 60, 'remote-status': 96, 'network-status': 138})
            draws = v.connectivity.delete.call_count
            v.draw_connectivity(True); self.assertEqual(v.connectivity.delete.call_count, draws)
            v.server_seen = 84; v.draw_connectivity(True)
            self.assertEqual(v.icon_renderer.connectivity.call_args.args[2][-1], display.RED)
            for connected, color in ((False, display.RED), (None, display.MUTED)):
                v.presenter_input.connected = connected; v.draw_connectivity(True)
                v.icon_renderer.bluetooth.assert_called_with(22, color, display.BG, connected)
            v.usb_power.power_state = None; v.draw_connectivity(True)
            v.icon_renderer.usb_power.assert_called_with(None, display.BG)
            v.usb_power.enabled = False
            v.icon_renderer.usb_power.reset_mock(); v.connectivity.create_image.reset_mock()
            v.draw_connectivity(True); v.icon_renderer.usb_power.assert_not_called()
            positions = {c.kwargs['tags']: c.args[0] for c in v.connectivity.create_image.call_args_list}
            self.assertEqual(positions, {'remote-battery': 0, 'remote-status': 36, 'network-status': 78})

    def test_missing_video_preserves_inset_and_does_not_stop_media(self):
        v = fixture(); v.model.state = State.IN_CALL
        v.engine.incoming_video_active.return_value = False
        v.update_video_message()
        self.assertTrue(v.missing_video_visible)
        v.local_video.place.assert_called_with(relx=1, rely=1, relwidth=.2, relheight=.2, anchor='se')
        v.missing_video.place.assert_called_with(x=0, y=0, relwidth=1, relheight=.8)
        v.missing_video_bottom.place.assert_called_with(x=0, rely=.8, relwidth=.8, relheight=.2)
        v.update_video_message(); self.assertEqual(v.missing_video.place.call_count, 1)
        v.engine.incoming_video_active.return_value = True; v.update_video_message()
        self.assertFalse(v.missing_video_visible); v.missing_video.place_forget.assert_called_once()
        v.model.state = State.HOME; v.update_video_message(); v.local_video.place_forget.assert_called_once()
        v.engine.end.assert_not_called(); v.video.destroy.assert_not_called()

    @patch.object(display.time, 'monotonic')
    def test_first_video_has_neutral_grace_then_warning_without_extending_on_redraw(self, clock):
        v = fixture(); v.model.state = State.IN_CALL
        v.engine.incoming_video_active.return_value = False
        clock.return_value = 100; v.update_video_message()
        self.assertEqual(v.video_message_key, 'starting_video')
        v.video_status_icon.itemconfigure.assert_called_with('unavailable', state='hidden')
        clock.return_value = 107.99; v.update_video_message()
        self.assertEqual(v.video_message_key, 'starting_video')
        clock.return_value = 108; v.update_video_message()
        self.assertEqual(v.video_message_key, 'no_remote_video')
        v.video_status_icon.itemconfigure.assert_called_with('unavailable', state='normal')
        self.assertEqual(v.video_started_at, 100)
        self.assertEqual(v.missing_video.place.call_count, 1)
        v.model.state = State.HOME; v.update_video_message()
        self.assertIsNone(v.video_started_at)
        v.model.state = State.IN_CALL; clock.return_value = 200; v.update_video_message()
        self.assertEqual(v.video_message_key, 'starting_video')
        self.assertEqual(v.video_started_at, 200)

    @patch.object(display.time, 'monotonic')
    def test_first_frame_ends_startup_grace_and_a_later_loss_is_not_disguised(self, clock):
        v = fixture(); v.model.state = State.IN_CALL
        v.engine.incoming_video_active.return_value = False
        clock.return_value = 100; v.update_video_message()
        self.assertEqual(v.video_message_key, 'starting_video')
        v.engine.incoming_video_active.return_value = True
        clock.return_value = 101; v.update_video_message()
        self.assertTrue(v.video_seen)
        self.assertFalse(v.missing_video_visible)
        v.engine.incoming_video_active.return_value = False
        clock.return_value = 105; v.update_video_message()
        self.assertEqual(v.video_message_key, 'no_remote_video')
        self.assertTrue(v.missing_video_visible)
        v.setup_stage = 'server'; v.update_video_message()
        self.assertIsNone(v.video_started_at)
        self.assertFalse(v.video_seen)

    def test_setup_error_and_confirmation_feedback_are_bounded(self):
        v = fixture(); v.setup_feedback = True
        v.render_setup_feedback(); v.setup_feedback_label.pack_forget.assert_called_once()
        for stage, error, text in [('wifi', True, 'help'), ('server', True, 'server — help'),
                                   ('server', 'server_unavailable', 'server — offline')]:
            v.setup_stage = stage; v.setup_feedback = error; v.render_setup_feedback()
            self.assertEqual(v.setup_feedback_label.cget('text'), text)
            v.setup_feedback_label.pack.assert_called_with(before=v.body, pady=(0, 10))
        v.setup_continue_at = 102.1
        with patch.object(display.time, 'monotonic', return_value=100): v.draw_wifi_confirmation()
        self.assertEqual(v.setup_confirmation_seconds, 3)
        with patch.object(display.time, 'monotonic', return_value=110): v.draw_wifi_confirmation()
        self.assertEqual(v.setup_confirmation_seconds, 0)
        v.draw_reset()
        self.assertEqual(len(v.current_text_images), 2)
        self.assertEqual([c.args[0] for c in v.text_renderer.photo.call_args_list[-2:]], ['reset', 'keep_configuration'])

    def test_render_precedence_and_call_setup_surface_selection(self):
        v = fixture()
        for name in ('update_usb_setup', 'update_pairing_page', 'render_tv_setup', 'render_settings'):
            setattr(v, name, Mock(return_value=False))
        for name in ('update_remote_help', 'render_setup_feedback', 'draw_corner_notification', 'fit_text',
                     'draw_connectivity', 'draw_avatar', 'draw_reset', 'draw_wifi_confirmation', 'draw_confirmation'):
            setattr(v, name, Mock())
        v.settings_hold = Mock(); v.settings_open = False; v.notice = ''; v.callback_alert = None
        v.contact_online = Mock(return_value=True)
        v.closed = True; v.render(); v.update_usb_setup.assert_not_called(); v.closed = False
        for gate in ('update_usb_setup', 'update_pairing_page', 'render_tv_setup', 'render_settings'):
            getattr(v, gate).return_value = True; v.render()
            v.draw_avatar.assert_not_called(); getattr(v, gate).return_value = False
        for state in State:
            with self.subTest(state=state), patch.object(display.tk.Misc, 'lift'):
                v.model.state = state; v.render()
                if state in (State.CONFIRMING, State.CONFIRM_CALLBACK, State.REQUESTING_CALLBACK):
                    v.confirmation.place.assert_called_with(x=0, y=0, relwidth=1, relheight=1)
                elif state == State.IN_CALL:
                    v.video.pack.assert_called_with(fill='both', expand=True)
                    self.assertEqual(v.call_name.cget('text'), 'Alice')
                else:
                    v.home.pack.assert_called_with(fill='both', expand=True)
        v.model.state = State.RINGING; v.model.deadline = 103
        with patch.object(display.time, 'monotonic', return_value=100): v.render()
        self.assertEqual(v.subtitle.cget('text'), 'countdown:3')
        v.model.state = State.HOME
        for notice, alert, title in [('offline', None, 'choose'), ('callback_requested', None, 'callback_requested'),
                                     ('', ['Alice'], '↩ Alice · online')]:
            v.notice = notice; v.callback_alert = alert; v.render(); self.assertEqual(v.title.cget('text'), title)
        v.engine.registered = False; v.notice = ''; v.callback_alert = None; v.render()
        self.assertEqual(v.subtitle.cget('text'), 'connecting')
        v.model.configure(config() | {'contacts': []}); v.render()
        self.assertEqual(v.subtitle.cget('text'), 'empty')
        for stage, title in [('reset', 'factory_reset'), ('wifi_ready', 'wifi_connected'),
                             ('wifi', 'Scan the Wi-Fi QR code'), ('server', 'Scan the server QR code')]:
            v.setup_stage = stage; v.render(); self.assertEqual(v.title.cget('text'), title)
        v.video.destroy.assert_not_called(); v.engine.end.assert_not_called()
