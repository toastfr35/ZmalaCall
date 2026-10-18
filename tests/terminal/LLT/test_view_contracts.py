# @test T-LLT-048
# @requirements TLLR003, TLLR007, TLLR036, TLLR037, TLLR075
# @environment portable
# @plan Record drawing calls at small and full-HD dimensions; check in-frame contact labels, portrait margins, localized rounded affirmative/negative controls, settings-only chrome and serial footer. Inject Pango to verify unchanged Unicode text and bounded shaping, and test absolute carousel deadlines under delayed frames.
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
from zmala_terminal.common.model import TerminalModel
from zmala_terminal.common.theme import BUTTON_GREEN, BUTTON_RED
from tests.terminal.LLT.test_terminal import config

ROOT = Path(__file__).resolve().parents[3]


class ViewContractTests(unittest.TestCase):
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
        view.contact_online = lambda person: True
        view.contact_image = Mock(return_value=object())
        view.draw_contact_status = Mock()
        label = Mock(); label.height.return_value = 24
        view.text_renderer = Mock(); view.text_renderer.photo.return_value = label
        for slot in (-1, 0, 1):
            view.avatar.reset_mock()
            person = view.model.contacts[0]
            view.draw_card(person, slot, 640, 300, 1280, 600, True)
            frame = view.avatar.create_rectangle.call_args.args
            calls = view.avatar.create_image.call_args_list
            name = next(call for call in calls if 'contact-name' in call.kwargs.get('tags', ()))
            portrait = calls[0]
            size = view.contact_image.call_args.args[1]
            self.assertGreater(name.args[1]-12, portrait.args[1]+size/2)
            self.assertLess(name.args[1]+12, frame[3]-39)
            self.assertGreater(name.args[0], frame[0]); self.assertLess(name.args[0], frame[2])

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
