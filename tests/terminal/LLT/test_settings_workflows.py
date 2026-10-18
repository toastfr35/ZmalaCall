# @test T-LLT-071
# @requirements LLR-TERM-SETUP-032, LLR-TERM-CONFIG-019, LLR-TERM-CONFIG-020, LLR-TERM-CONFIG-021, LLR-TERM-CONFIG-022
# @environment portable
# @plan Exercise settings navigation, acknowledged writes and timeout reconciliation with real drafts and recording HTTP/Tk boundaries. Verify busy and cancelled drafts, captured enrollment generation, keyboard repeat release coalescing and stale-result rejection. Draw every setting with controlled image metrics; check serial footer, hint placement only on the active side, localized values, hold progress, busy feedback and bounded font size.
# @pass Every navigation, request, state and drawing assertion passes without a display or server; no mocked pixel output is claimed as physical readability evidence.
import queue
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from zmala_terminal.common import settings_control
from zmala_terminal.common.local_settings import FIELDS, SettingsDraft, SettingsHold
from zmala_terminal.common.ui import settings
from tests.terminal.LLT import test_local_settings
from tests.terminal.LLT.test_display_states import widget


class SettingsWorkflowTests(unittest.TestCase):
    def controller(self):
        c=test_local_settings.LocalSettingsTests().controller(); c.settings_draft=SettingsDraft(); c.settings_open=True
        c.messages=queue.Queue(); c.configuration=Mock(); c.generation=3; c.closed=False; c.apply_poll_config=Mock()
        return c

    def test_navigation_draft_cancel_accept_and_busy_guard(self):
        c=self.controller(); d=c.settings_draft; c.settings_button('right'); self.assertEqual(d.row,1)
        c.settings_button('left'); self.assertEqual(d.row,0); c.settings_button('green'); self.assertTrue(d.editing)
        d.error=True; c.settings_button('red'); self.assertFalse(d.editing); self.assertFalse(d.error); self.assertTrue(c.settings_open)
        c.settings_button('green'); c.save_local_setting=Mock(); c.settings_button('green'); c.save_local_setting.assert_called_once()
        d.busy=True; c.render.reset_mock(); c.settings_button('red'); self.assertTrue(c.settings_open); c.render.assert_not_called()
        d.busy=False; d.editing=False; c.settings_button('red'); self.assertFalse(c.settings_open)

    def test_write_reconciliation_preserves_generation_and_expected_values(self):
        for outcome in ['accepted','timeout-applied','timeout-rejected','offline']:
            c=self.controller(); d=c.settings_draft; d.row=FIELDS.index('carousel_portraits'); d.open(c.model.config); d.move(1)
            changes=d.change(c.model.config); expected=dict(d.expected); reply=c.model.config | changes
            if outcome=='accepted': c.configuration.update_settings.return_value=reply
            else:
                c.configuration.update_settings.side_effect=TimeoutError()
                c.configuration.fetch.return_value=reply if outcome=='timeout-applied' else c.model.config
                if outcome=='offline': c.configuration.fetch.side_effect=OSError()
            work=[]
            with patch.object(settings_control.threading,'Thread',side_effect=lambda **kw:Mock(start=lambda:work.append(kw['target']))): c.save_local_setting()
            self.assertTrue(d.busy); c.generation=4; work[0]()
            c.configuration.update_settings.assert_called_once_with(changes,expected)
            kind,value=c.messages.get_nowait(); self.assertEqual(kind,'local-settings'); self.assertEqual(value[0],3)
            self.assertEqual(value[2],outcome in ['accepted','timeout-applied']); c.local_settings_result(*value); self.assertTrue(d.busy)
            c.generation=3; c.local_settings_result(*value); self.assertFalse(d.busy); self.assertEqual(d.error,outcome in ['timeout-rejected','offline'])
            if outcome in ['accepted','timeout-applied']: self.assertFalse(d.editing)
            elif outcome=='timeout-rejected': self.assertEqual(d.expected,expected)
        c=self.controller(); c.settings_draft.open(c.model.config); c.save_local_setting(); self.assertFalse(c.settings_draft.editing); c.configuration.update_settings.assert_not_called()
        c.settings_draft.open(c.model.config); c.settings_draft.move(1); c.configuration=None; c.save_local_setting(); self.assertTrue(c.settings_draft.error)

    def test_repeat_release_is_deferred_once_and_setup_cancels_hold(self):
        c=self.controller(); c.settings_open=False; c.keys_down={'red'}; c.settings_hold.start(100)
        c.queue_keyrelease('red'); c.queue_keyrelease('red'); c.root.after_idle.assert_called_once()
        callback=c.root.after_idle.call_args.args[0]
        with patch.object(settings_control.time,'monotonic',return_value=100.5): callback()
        self.assertFalse(c.keys_down); self.assertEqual(c.key_release_jobs,{}); c._press_action.assert_called_once_with('red')
        c.settings_hold.start(100); c.setup_stage='wifi'; c.tick_settings_access(111); self.assertIsNone(c.settings_hold.started)
        c.setup_stage='tv'; c.tv_setup_button=Mock(return_value=True); c._press_action.reset_mock(); c.press('green'); c._press_action.assert_not_called()

    def view(self):
        v=settings.SettingsView(); v.root=widget(); v.model=self.controller().model; v.language='en'; v.available_fonts=['Sans']
        v.text=lambda key:key; v.settings_open=True; v.settings_hold=SettingsHold(); v.settings_draft=SettingsDraft()
        v.text_renderer=Mock(); v.text_renderer.photo.return_value=SimpleNamespace(height=lambda:20)
        v.icon_renderer=Mock()
        with patch.object(settings.tk,'Canvas',side_effect=lambda *a,**kw:widget()): v.build_settings()
        return v

    def test_settings_render_each_field_and_keep_hints_on_active_side(self):
        v=self.view(); c=v.settings_canvas
        for row,key in enumerate(FIELDS):
            for editing in ([False] if key=='reset' else [False,True]):
                v.settings_draft=SettingsDraft(); v.settings_draft.row=row
                if editing: v.settings_draft.open(v.model.config)
                v.settings_signature=None; c.reset_mock(); v.draw_settings()
                hints=[call.args[0] for call in c.create_image.call_args_list if call.kwargs.get('tags')=='settings-hint']
                self.assertTrue(hints); split=int(1280*.39)
                self.assertTrue(all(x>split for x in hints) if editing else all(x<split for x in hints))
                self.assertTrue(any(call.kwargs.get('tags')=='settings-serial' for call in c.create_image.call_args_list))
                c.delete.reset_mock(); v.draw_settings(); c.delete.assert_not_called()
        v.settings_draft.busy=True; c.reset_mock(); v.draw_settings()
        self.assertFalse(any(call.kwargs.get('tags')=='settings-hint' for call in c.create_image.call_args_list))
        v.settings_draft.busy=False; v.settings_draft.error=True; v.draw_settings()
        self.assertIn('help',[call.args[0] for call in v.text_renderer.photo.call_args_list])

    def test_hold_progress_bounded_labels_and_localized_values(self):
        v=self.view(); v.settings_open=False; v.settings_hold.start(100); v.settings_hold.update(105)
        with patch.object(settings.tk.Misc,'lift'): self.assertTrue(v.render_settings())
        progress=[call for call in v.settings_canvas.create_rectangle.call_args_list if call.kwargs.get('tags')=='settings-progress']; self.assertEqual(len(progress),1)
        self.assertAlmostEqual(progress[0].args[2]-progress[0].args[0],(1280*.6-10)*.5)
        v.text_renderer.photo.return_value=SimpleNamespace(height=lambda:999)
        v.settings_label('long text',0,0,200,size=16,max_height=20); self.assertEqual(v.text_renderer.photo.call_args.args[2],11)
        v.text_renderer.photo.reset_mock(); v.settings_label('',0,0,200); v.text_renderer.photo.assert_not_called()
        self.assertEqual(v.settings_value('auto_answer',None),'Never'); self.assertEqual(v.settings_value('tv_idle_seconds',120),'2 min')
        self.assertEqual(v.settings_value('auto_answer',10),'10 s'); self.assertEqual(v.settings_value('auto_framing',False),'no')
        v.language='unsupported'; self.assertEqual(v.settings_text('settings'),'Settings'); self.assertEqual(v.settings_text('reset'),'reset')
        v.settings_hold.clear(); self.assertFalse(v.render_settings()); self.assertIsNone(v.settings_signature)


if __name__=='__main__': unittest.main()
