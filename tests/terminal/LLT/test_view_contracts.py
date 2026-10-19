# @test T-LLT-048
# @requirements LLR-TERM-NAV-005, LLR-TERM-CONFIG-020, LLR-TERM-UI-014, LLR-TERM-UI-015, LLR-TERM-UI-016, LLR-TERM-UI-017, LLR-TERM-UI-019, LLR-TERM-UI-024, LLR-TERM-HISTORY-016, LLR-TERM-HISTORY-022
# @environment portable
# @plan Record drawing calls at small and full-HD dimensions; check the selected-to-adjacent portrait size ratio, in-frame contact labels, portrait margins, localized rounded affirmative/negative controls, settings-only chrome and serial footer. Inject Pango to verify unchanged Unicode text and bounded shaping; force a tall translated settings label to check minimum-font ellipsis and intact combining marks. Test absolute carousel deadlines under delayed frames. Exercise real carousel composition with recording widgets, controlled shaped-label metrics and image failures; assert pending/missed badges, logo restoration, bounded labels and placeholder/ringing redraws.
# Check three-state contact colours, labels and symbols; expire a six-second live snapshot and confirm push remains callable only while fresh. Change presence at the same configuration version and assert redraws without reconfiguration.
# @pass Geometry, color, text and timing assertions must pass; these unit checks do not replace physical display or font-rendering acceptance.

import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from zmala_terminal.common.carousel import CarouselMotion
from zmala_terminal.common.ui.carousel import CarouselView
from zmala_terminal.common.ui.confirmation import ConfirmationView
from zmala_terminal.common.ui.settings import SettingsView
from zmala_terminal.common.local_settings import SettingsDraft, FIELDS
from zmala_terminal.common.model import TerminalModel, State
from zmala_terminal.common.theme import BUTTON_GREEN, BUTTON_RED
from tests.terminal.LLT.test_terminal import config

ROOT = Path(__file__).resolve().parents[3]


class ViewContractTests(unittest.TestCase):
    def test_same_revision_presence_change_redraws_without_reconfiguring(self):
        import copy
        from zmala_terminal.common.management import ManagementLoop
        loop = ManagementLoop(); loop.model = TerminalModel(); loop.model.configure(config())
        loop.render = Mock(); loop.apply_config = Mock(); loop.callback_requests = []
        original_version = loop.model.config['configuration_version']
        for state in ('push', 'available', 'offline'):
            update = copy.deepcopy(loop.model.config)
            update['contacts'][0].update(online=state != 'offline', presence=state)
            loop.apply_poll_config(update)
            self.assertEqual(loop.model.contacts[0]['presence'], state)
            self.assertEqual(loop.model.config['configuration_version'], original_version)
        self.assertEqual(loop.render.call_count, 3)
        loop.apply_config.assert_not_called()

    def test_three_state_presence_and_stale_snapshot(self):
        from zmala_terminal.common.call_control import CallControl
        from zmala_terminal.common.theme import GREEN, RED
        c = CallControl(); c.server_seen = 100
        view = CarouselView(); view.avatar = Mock(); view.font_family = 'Sans'
        view.carousel_motion = None; view.current_text_images = []; view.text = lambda key: key
        view.text_renderer = Mock(); view.text_renderer.photo.return_value.height.return_value = 20
        for state, color, label in [('available', GREEN, 'available'), ('push', '#388bff', 'try_calling'), ('offline', RED, 'offline')]:
            contact = {'online': state != 'offline', 'presence': state}
            with patch('zmala_terminal.common.call_control.time.monotonic', return_value=105):
                self.assertEqual(c.contact_presence(contact), state)
                self.assertEqual(c.contact_online(contact), state != 'offline')
            with patch('zmala_terminal.common.call_control.time.monotonic', return_value=106):
                self.assertEqual(c.contact_presence(contact), 'offline')
            view.draw_contact_status(200, 300, 180, 12, True, state != 'offline', presence=state)
            self.assertEqual(view.avatar.create_text.call_args.kwargs['fill'], color)
            self.assertEqual(view.text_renderer.photo.call_args.args[0], label)

    def test_settings_labels_elide_without_splitting_combining_marks(self):
        view = SettingsView(); view.language = 'en'; view.available_fonts = ['Sans']
        view.settings_images = []; view.settings_canvas = Mock(); view.text_renderer = Mock()
        rendered = []
        def photo(text, family, size, *args):
            rendered.append((text, size))
            return SimpleNamespace(height=lambda: 24 if len(text) <= 7 else 106)
        view.text_renderer.photo.side_effect = photo
        view.settings_label('Cafe\u0301 Cafe\u0301', 50, 568, 80, max_height=32)
        self.assertEqual(rendered[-1], ('Cafe\u0301…', 11))
        self.assertEqual(view.settings_images[-1].height(), 24)
        self.assertTrue(all(not text.endswith('\u0301…') or text.endswith('e\u0301…') for text, size in rendered))
        view.settings_canvas.create_image.assert_called_once()

    def test_carousel_redraw_keeps_badges_labels_and_placeholder_inside_animated_cards(self):
        from zmala_terminal.common.ui import carousel
        view = CarouselView()
        view.model = TerminalModel(); view.model.configure(config())
        person = view.model.selected
        person['photo'] = '/photos/fixture.png'
        person['name'] = 'Very long translated contact name'
        view.model.mark_notification(person['id'])
        view.model.config['callbacks'] = [{'status':'pending', 'from':view.model.config['sip']['username'], 'to':person['id']}]
        view.avatar = Mock(); view.avatar.winfo_width.return_value = 1280; view.avatar.winfo_height.return_value = 600
        view.avatar.find_all.return_value = (11, 12)
        view.hidden_notifications = Mock(); view.corner_notification_state = None; view.corner_logo = object()
        view.language = 'en'; view.font_family = 'Sans'; view.available_fonts = ['Segoe UI Symbol']
        view.ringing_started = None; view.setup_stage = None
        view.carousel_motion = CarouselMotion(view.model.contacts, 0, 1, 10)
        view.contact_presence = lambda person: 'available' if view.contact_online(person) else 'offline'
        view.contact_online = lambda person: bool(person and person.get('online'))
        view.icon_renderer = Mock(); view.text_renderer = Mock()
        view.text = lambda key: key
        view.text_renderer.photo.side_effect = lambda text, family, size, *args: Mock(height=lambda: 60 if size > 10 or len(text) > 10 else 20)
        with patch.object(carousel.time, 'monotonic', return_value=10.1):
            view.draw_avatar(person)
        self.assertTrue(view.current_photos)
        self.assertTrue(view.current_text_images)
        self.assertTrue(all(image.height() <= 44 for image in view.current_text_images))
        self.assertEqual(view.corner_notification_state, 1)
        self.assertIs(view.corner_badge_image, view.icon_renderer.missed_call.return_value)
        view.avatar.delete.assert_called_once_with(11, 12)
        self.assertTrue(any('callback-pending' in c.kwargs.get('tags', ()) for c in view.avatar.create_image.call_args_list))
        self.assertTrue(view.text_renderer.portrait.call_args.kwargs['fast'])
        # A quiet/static screen shows the logo; absent portraits use a letter/placeholder.
        view.draw_corner_notification(0)
        view.hidden_notifications.create_image.assert_called_with(24, 28, image=view.corner_logo, tags='zmala-logo')
        count = view.hidden_notifications.delete.call_count
        view.draw_corner_notification(0)
        self.assertEqual(view.hidden_notifications.delete.call_count, count)
        view.carousel_motion = None
        view.text_renderer.portrait.side_effect = OSError('missing')
        view.draw_card(person, 0, 640, 300, 1280, 600, True)
        self.assertTrue(any(c.kwargs.get('text') == 'V' for c in view.avatar.create_text.call_args_list))
        view.draw_card(None, -1, 640, 300, 1280, 600, True)
        self.assertTrue(any(c.kwargs.get('text') == '·' for c in view.avatar.create_text.call_args_list))
        view.model.state = State.RINGING
        view.text_renderer.photo.return_value = None
        view.text_renderer.photo.side_effect = lambda *args: Mock(height=lambda: 20)
        view.draw_avatar(person)
        self.assertTrue(any(c.kwargs.get('tags') == 'ring-phone' for c in view.avatar.create_image.call_args_list))

    def test_absolute_frame_deadlines_skip_missed_frames_without_drift(self):
        motion = CarouselMotion([1, 2, 3], 0, 1, 10)
        self.assertEqual(motion.progress(9), 0)
        self.assertAlmostEqual(motion.progress(10.275), .5)
        self.assertEqual(motion.progress(11), 1)
        for elapsed in (.004, .045, .2, .503):
            delay = motion.next_frame_delay(10+elapsed)
            self.assertGreaterEqual(delay, 1)
            self.assertLessEqual(delay, 17)
            deadline = 10+elapsed+delay/1000
            self.assertLessEqual(abs((deadline-10)*60-round((deadline-10)*60)), .061)
        picom = (ROOT/'build_tools/linux/picom.conf').read_text()
        self.assertRegex(picom, r'(?m)^vsync\s*=\s*true;')

    def test_selected_and_neighbour_names_stay_inside_card_above_status(self):
        view = CarouselView()
        view.model = TerminalModel(); view.model.configure(config())
        view.avatar = Mock()
        view.current_photos = []; view.current_text_images = []
        view.font_family = 'Sans'; view.ringing_started = None; view.carousel_motion = None
        view.contact_presence = lambda person: 'available' if view.contact_online(person) else 'offline'
        view.contact_online = lambda person: True
        view.contact_image = Mock(return_value=object())
        view.draw_contact_status = Mock()
        label = Mock(); label.height.return_value = 24
        view.text_renderer = Mock(); view.text_renderer.photo.return_value = label
        sizes = {}
        for slot in (-1, 0, 1):
            view.avatar.reset_mock()
            person = view.model.contacts[0]
            view.draw_card(person, slot, 640, 300, 1280, 600, True)
            frame = view.avatar.create_rectangle.call_args.args
            calls = view.avatar.create_image.call_args_list
            name = next(call for call in calls if 'contact-name' in call.kwargs.get('tags', ()))
            portrait = calls[0]
            size = view.contact_image.call_args.args[1]
            sizes[slot] = size
            self.assertGreater(name.args[1]-12, portrait.args[1]+size/2)
            self.assertLess(name.args[1]+12, frame[3]-39)
            self.assertGreater(name.args[0], frame[0]); self.assertLess(name.args[0], frame[2])
        self.assertEqual(sizes[-1], sizes[1])
        self.assertAlmostEqual(sizes[0], 2*sizes[1], delta=1)

    def test_confirmation_has_margins_and_localized_rounded_color_choices(self):
        for width, height in ((700, 500), (1920, 1080)):
            v = ConfirmationView(); v.model = TerminalModel(); v.model.configure(config())
            v.model.button('green')
            v.root = Mock(); v.root.winfo_width.return_value = width; v.root.winfo_height.return_value = height
            v.confirmation = Mock(); v.language = 'fr'; v.font_family = 'Sans'; v.confirmation_signature = None
            v.text = lambda key, **values: {'yes':'Oui', 'no':'Non'}.get(key, 'Question')
            label = Mock(); label.height.return_value = 32
            v.text_renderer = Mock(); v.text_renderer.photo.return_value = label
            v.contact_image = Mock(return_value=object()); v.icon_renderer = Mock()
            v.draw_confirmation()
            labels = [c.args[0] for c in v.text_renderer.photo.call_args_list]
            self.assertIn('Oui', labels); self.assertIn('Non', labels)
            buttons = v.icon_renderer.rounded_button.call_args_list
            self.assertEqual([c.args[2] for c in buttons], [BUTTON_GREEN, BUTTON_RED])
            picture = next(c for c in v.confirmation.create_image.call_args_list if c.kwargs.get('tags') == 'confirmed-person')
            size = v.contact_image.call_args.args[1]
            self.assertGreaterEqual(picture.args[1]-size/2, 24)
            for call in v.confirmation.create_image.call_args_list:
                self.assertGreaterEqual(call.args[0], 0); self.assertLessEqual(call.args[0], width)
                self.assertLess(call.args[1], height)

    def test_settings_serial_and_reset_are_present_without_connectivity_draws(self):
        v = SettingsView(); v.model = TerminalModel(); v.model.configure(config())
        v.settings_open = True; v.settings_hold = SimpleNamespace(capturing=False, progress=0)
        v.settings_signature = None; v.settings_draft = SettingsDraft(); v.language = 'en'
        v.settings_canvas = Mock(); v.settings_canvas.winfo_width.return_value = 1280; v.settings_canvas.winfo_height.return_value = 720
        v.settings_label = Mock(); v.settings_panel = Mock(); v.text = lambda key: key
        v.draw_connectivity = Mock(); v.draw_settings()
        serial = next(c for c in v.settings_label.call_args_list if c.kwargs.get('tags') == 'settings-serial')
        self.assertEqual(serial.args[0], 'ID : test')
        self.assertEqual(serial.args[2:5], (702, 1216, 11))
        self.assertEqual(FIELDS[-1], 'reset')
        v.draw_connectivity.assert_not_called()
        hints = [c for c in v.settings_panel.call_args_list if c.kwargs.get('tags') == 'settings-hint']
        self.assertEqual(len(hints), 3)
        self.assertTrue(all(c.args[0] < 1280*.39 for c in hints))

    def test_pango_receives_unmodified_bidi_name_with_width_wrap_and_font(self):
        pango = Mock(SCALE=1024)
        pangocairo = Mock(); layout = pangocairo.create_layout.return_value
        gi = Mock()
        with patch.dict(sys.modules, {'gi':gi, 'gi.repository':SimpleNamespace(Pango=pango, PangoCairo=pangocairo), 'cairo':Mock()}):
            spec = importlib.util.spec_from_file_location('shaping_unit', ROOT/'zmala_terminal/linux/text_renderer.py')
            module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
            text = 'عائلة 日本語 Élodie'
            module.layout_for(object(), text, 'TkDefaultFont', 20, 120, True)
        layout.set_text.assert_called_once_with(text, -1)
        layout.set_width.assert_called_once_with(120*1024)
        layout.set_wrap.assert_called_once_with(pango.WrapMode.WORD_CHAR)
        pango.FontDescription.return_value.set_family.assert_called_once_with('Sans')
