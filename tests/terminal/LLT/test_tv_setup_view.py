# @test T-LLT-059
# @requirements LLR-TERM-TV-019, LLR-TERM-TV-020, LLR-TERM-TV-021, LLR-TERM-TV-022, LLR-TERM-TV-023, LLR-TERM-TV-024
# @environment portable
# @plan Run the real TV setup view with recording canvas/text renderers and a fake TVCheck/transport. Verify enrollment-only entry, selected language, maintenance suspension, remote-only actions, independent power/source capability restoration and localized retry/help/summary controls. Exercise narrow-screen text fitting, busy/error states and redraw caching without sending TV commands.
# @pass Setup surfaces and button hints match each stage; completion enables only user-passed capabilities and resumes maintenance once. Pixel quality and actual CEC behavior are outside this unit test.
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from zmala_terminal.common.ui import tv_setup
from tests.terminal.LLT.test_display_states import widget


class TVViewTests(unittest.TestCase):
    def fixture(self):
        v=tv_setup.TVSetupView(); v.root=widget(); v.maintenance=Mock(); v.setup_stage=None
        v.enrollment=SimpleNamespace(path=Path('private/enrollment.json')); v.available_fonts=set()
        v.tv_control=Mock(); v.render=Mock(); v.apply_config=Mock(); v.make_maintenance=Mock(); v.configuration=Mock()
        v.text_renderer=Mock(); v.text_renderer.photo.return_value=Mock(height=lambda:30)
        v.icon_renderer=Mock(); v.language='en'; v.font_family='Sans'
        for name in ('video','confirmation','settings_canvas','remote_help'): setattr(v,name,widget())
        with patch.object(tv_setup.tk,'Canvas',return_value=widget()): v.build_tv_setup()
        return v

    def test_entry_is_once_after_enrollment_and_suspends_maintenance(self):
        v=self.fixture()
        with patch.dict(tv_setup.os.environ,{},clear=True): self.assertFalse(v.begin_tv_setup({}))
        v=self.fixture(); old=v.maintenance
        with patch.dict(tv_setup.os.environ,{'ZMALA_PAIRING_STATUS':'pairing.json'}), \
                patch.object(tv_setup,'TVCheck') as check, patch.object(tv_setup,'CheckTransport') as transport:
            self.assertTrue(v.begin_tv_setup({'language':'fr'})); self.assertFalse(v.begin_tv_setup({}))
        old.stop.assert_called_once(); self.assertIsNone(v.maintenance)
        self.assertEqual(v.language,'fr'); self.assertEqual(v.setup_stage,'tv')
        check.assert_called_once_with(Path('private/tv-check.json'),transport.return_value)
        check.return_value.start.assert_called_once()
        check.return_value.poll.return_value=True; check.return_value.page='power_ready'
        v.tick_tv_setup(); v.render.assert_called_once()
        self.assertTrue(v.tv_setup_button('red')); check.return_value.button.assert_called_once_with('red')
        v.setup_stage=None; self.assertFalse(v.tv_setup_button('green'))

    def test_completion_restores_only_confirmed_capabilities_and_resumes_once(self):
        for power,source in (('passed','failed'),('skipped','passed')):
            v=self.fixture(); v.setup_stage='tv'; v.tv_check_config={'language':'fr'}
            check=Mock(page='done',record={'power':{'status':power},'source':{'status':source}})
            check.poll.return_value=False; v.tv_check=check
            with patch.object(tv_setup.time,'monotonic',return_value=100): v.tick_tv_setup()
            self.assertEqual(v.tv_control.power_enabled,power=='passed')
            self.assertEqual(v.tv_control.source_enabled,source=='passed')
            check.close.assert_called_once(); self.assertIsNone(v.tv_check); self.assertIsNone(v.setup_stage)
            v.apply_config.assert_called_once_with({'language':'fr'})
            v.make_maintenance.assert_called_once_with(v.configuration); self.assertEqual(v.last_button,100)
            v.tick_tv_setup(); v.make_maintenance.assert_called_once()

    def test_modal_hides_other_surfaces_and_is_removed_outside_setup(self):
        v=self.fixture(); self.assertFalse(v.render_tv_setup())
        v.tv_check=Mock(); v.setup_stage='tv'
        with patch.object(tv_setup.tk.Misc,'lift'), patch.object(v,'draw_tv_setup') as draw:
            self.assertTrue(v.render_tv_setup()); draw.assert_called_once()
        for name in ('video','confirmation','settings_canvas','remote_help'):
            getattr(v,name).place_forget.assert_called_once()
        v.tv_check_page.place.assert_called_with(x=0,y=0,relwidth=1,relheight=1)

    def test_localized_prompts_controls_and_summary_match_stage(self):
        expected={
            'power_ready':('start','skip'),'source_ready':('start','skip'),
            'power_confirm':('yes','no'),'source_confirm':('yes','no'),
            'retry_power':('retry','without'),'retry_source':('retry','without'),
            'paired':('retry','without'),'unavailable':('retry','without'),
            'samsung_help':('continue','back'),'sony_help':('continue','back'),
            'no_tv':('continue','back'),'choose_tv':('select','back'),
            'save_error':('retry',),'summary':('continue',),'source_timeout':('continue',)}
        for language in ('en','fr','unknown'):
            for page,buttons in expected.items():
                with self.subTest(language=language,page=page):
                    v=self.fixture(); v.language=language; v.setup_stage='tv'
                    v.tv_check=SimpleNamespace(page=page,selection=0,error=False,busy=False,
                        record={'power':{'status':'passed'},'source':{'status':'failed'}},
                        candidates=[{'name':'Living room','host':'192.0.2.1'}])
                    v.draw_tv_setup()
                    messages=tv_setup.MESSAGES.get(language,tv_setup.MESSAGES['en'])
                    labels=[c.args[0] for c in v.text_renderer.photo.call_args_list]
                    self.assertEqual(labels[-len(buttons):],[messages[key] for key in buttons])
                    if page=='choose_tv': self.assertIn('Living room\n192.0.2.1',labels[1])
                    if page=='summary': self.assertIn(messages['failed'],labels[1])
                    calls=v.text_renderer.photo.call_count; v.draw_tv_setup()
                    self.assertEqual(v.text_renderer.photo.call_count,calls)

    def test_probe_busy_errors_and_text_height_remain_bounded(self):
        v=self.fixture(); v.draw_tv_setup(); v.text_renderer.photo.assert_not_called()
        v.setup_stage='tv'
        for page in ('probe','done','power_confirm'):
            v.tv_check=SimpleNamespace(page=page,selection=0,error=True,record={},busy=True)
            v.tv_check_signature=None; v.icon_renderer.rounded_button.reset_mock()
            v.text_renderer.photo.side_effect=lambda value,family,size,*args: Mock(height=lambda:1000 if size>13 else 20)
            v.draw_tv_setup(); v.icon_renderer.rounded_button.assert_not_called()
        self.assertIn(tv_setup.MESSAGES['en']['error'],[c.args[0] for c in v.text_renderer.photo.call_args_list])
        self.assertEqual(v.text_renderer.photo.call_args.args[2],13)
