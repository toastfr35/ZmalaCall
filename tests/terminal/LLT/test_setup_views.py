# @test T-LLT-067
# @requirements LLR-TERM-SETUP-022, LLR-TERM-SETUP-024, LLR-TERM-SETUP-025, LLR-TERM-REMOTE-013, LLR-TERM-REMOTE-017, LLR-TERM-REMOTE-018, LLR-TERM-UI-023
# @environment portable
# @plan Execute USB, remote recovery and button-test drawing against recording Tk widgets using the shipped artwork and real PIL resampling. Verify the missing-device delay, call/settings priority, image caching and aspect ratio, localized labels, pairing/test-page transitions, exclusively active-button outlines and input consumption through the final release.
# @pass Assertions verify image sizes, selected text, drawing commands and gating without a real display or remote; physical readability is not inferred from mocked Tk calls.
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch
from PIL import ImageTk
from zmala_terminal.common.ui import remote_help, remote_test, usb_setup
from zmala_terminal.common.model import State
from zmala_terminal.common.remote_test import BUTTONS
from zmala_terminal.common.theme import GREEN
from tests.terminal.LLT.test_display_states import widget


class SetupViewTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup); self.folder=Path(temp.name)
        self.uploads=[]
        def upload(image,**kwargs): self.uploads.append(image.copy()); return SimpleNamespace(width=lambda:image.width,height=lambda:image.height)
        patcher=patch.object(ImageTk,'PhotoImage',side_effect=upload); patcher.start(); self.addCleanup(patcher.stop)

    def view(self):
        v=remote_help.RemoteHelpView(); v.root=widget(); v.model=Mock(state=State.HOME); v.setup_stage=None
        v.enrollment=SimpleNamespace(path=self.folder/'enrollment.json'); v.font_family='Sans'; v.language='fr'
        v.text=lambda key:'translated:'+key; v.text_renderer=Mock(); v.text_renderer.photo.return_value=None
        v.icon_renderer=Mock(); v.presenter_input=Mock(status='disconnected'); v.render=Mock(); v.stop_scanner=Mock()
        v.needs_c20=Mock(return_value=False); v.update_usb_setup=Mock(return_value=False)
        with patch.object(remote_help.tk,'Frame',side_effect=lambda *a,**kw:widget()),patch.object(remote_help.tk,'Label',side_effect=lambda *a,**kw:widget()),patch.object(remote_test.tk,'Canvas',side_effect=lambda *a,**kw:widget()): v.build_remote_help()
        v.pairing_status=Mock(bond='test-bond'); v.pairing_status.read.return_value=None
        return v

    def test_missing_remote_delay_and_call_settings_priority(self):
        v=self.view()
        with patch.object(remote_help.time,'monotonic',return_value=100): v.update_remote_help()
        v.remote_help.place.assert_not_called(); self.assertEqual(v.remote_missing_since,100)
        with patch.object(remote_help.time,'monotonic',return_value=105): v.update_remote_help()
        self.assertIn('remote_disconnected_title',v.remote_help_title.cget('text')); self.assertEqual(len(self.uploads),1)
        self.assertIsNone(v.carousel_motion)
        with patch.object(remote_help.time,'monotonic',return_value=106): v.update_remote_help()
        self.assertEqual(len(self.uploads),1)
        for field,value in [('settings_open',True),('settings_hold',Mock(capturing=True))]:
            setattr(v,field,value); v.remote_help.place.reset_mock(); v.update_remote_help(); v.remote_help.place.assert_not_called(); setattr(v,field,False)
        v.model.state=State.RINGING; v.remote_help.place.reset_mock(); v.update_remote_help(); v.remote_help.place.assert_not_called()
        v.model.state=State.HOME; v.presenter_input.status='connected'; v.update_remote_help(); self.assertIsNone(v.remote_missing_since)
        self.assertIsNone(v.remote_help_signature)

    def test_recovery_status_artwork_and_localized_labels_are_bounded(self):
        v=self.view(); v.remote_missing_since=0
        for status in ['unpaired','bluetooth_unavailable','blocked','input_unavailable','unknown']:
            v.presenter_input.status=status
            with patch.object(remote_help.time,'monotonic',return_value=10): v.update_remote_help()
            key=status if status!='unknown' else 'disconnected'
            self.assertEqual(v.remote_help_title.cget('text'),'translated:remote_'+key+'_title')
        v.text_renderer.photo.return_value=SimpleNamespace(height=lambda:1000)
        v.label_remote_picture(200,True,True)
        for label in v.remote_picture_labels:
            self.assertEqual(label.cget('font')[1],12); self.assertIsNotNone(label.image)
        self.assertIn('pairing',v.remote_picture_labels[-1].cget('text'))
        v.label_remote_picture(200,False)
        for label in v.remote_picture_labels: label.place_forget.assert_called()

    def test_pairing_gate_transitions_to_button_test_and_releases_setup_when_verified(self):
        v=self.view(); v.setup_stage='wifi'; v.pairing_status.read.return_value='unpaired'
        self.assertTrue(v.update_pairing_page()); v.stop_scanner.assert_called_once(); self.assertEqual(len(self.uploads),1)
        self.assertIn('remote_unpaired_title',v.remote_help_title.cget('text')); self.assertTrue(v.pairing_page_visible)
        # Pairing alone is insufficient: the connected HID input must also pass the button test.
        v.pairing_status.read.return_value='paired'; v.presenter_input.status='disconnected'
        self.assertTrue(v.update_pairing_page()); self.assertIn('remote_disconnected_title',v.remote_help_title.cget('text'))
        v.presenter_input.status='connected'; v.draw_remote_test=Mock(); self.assertTrue(v.update_pairing_page()); v.draw_remote_test.assert_called_once()
        v.remote_test.verified='test-bond'; self.assertFalse(v.update_pairing_page()); self.assertFalse(v.pairing_page_visible)
        v.root.after_idle.assert_called_with(v.render); self.assertIsNone(v.remote_help_signature)
        v.presenter_input.status='input_unavailable'; self.assertTrue(v.update_pairing_page()); self.assertIn('remote_input_unavailable',v.remote_help_title.cget('text'))

    def test_button_page_highlights_only_expected_button_and_uses_sticker_colors(self):
        v=self.view(); v.remote_test.sync('test-bond',True); c=v.remote_test_page
        for index,button in enumerate(BUTTONS):
            v.remote_test.index=index; c.reset_mock(); v.draw_remote_test()
            outlines=[item for item in c.create_oval.call_args_list if item.kwargs.get('outline')==GREEN]
            self.assertEqual(len(outlines),1)
            fills=[item.kwargs.get('fill') for item in c.create_oval.call_args_list]
            self.assertIn('#15db2b',fills); self.assertIn('#ff252b',fills)
            labels=[item.kwargs['text'] for item in c.create_text.call_args_list]
            self.assertIn('Press: '+remote_test.NAMES[button],labels)
            c.delete.reset_mock(); v.draw_remote_test(); c.delete.assert_not_called()
        v.remote_test.armed=True; v.draw_remote_test(); self.assertIn('Now release: Middle',[x.kwargs['text'] for x in c.create_text.call_args_list])
        v.remote_test.error=True; v.draw_remote_test(); self.assertTrue(any('Could not save' in x.kwargs['text'] for x in c.create_text.call_args_list))

    def test_physical_button_events_are_consumed_until_test_completes(self):
        v=self.view(); v.pairing_status.read.return_value='paired'; v.presenter_input.status='connected'
        v.needs_c20.return_value=True; self.assertTrue(v.remote_test_event('left',True)); self.assertEqual(v.remote_test.index,0)
        v.needs_c20.return_value=False
        for button in BUTTONS:
            self.assertTrue(v.remote_test_event(button,True)); self.assertTrue(v.remote_test_event(button,False))
        self.assertTrue(v.remote_test.complete); self.assertFalse(v.remote_test_event('green',True))
        self.assertEqual(v.render.call_count,10)

    def test_usb_artwork_fits_viewport_reuses_image_and_hides_when_camera_returns(self):
        v=usb_setup.UsbSetupView(); v.root=widget(); v.model=Mock(state=State.HOME); v.setup_stage='wifi'; v.stop_scanner=Mock(); v.render=Mock()
        with patch.object(usb_setup.tk,'Frame',side_effect=lambda *a,**kw:widget()),patch.object(usb_setup.tk,'Label',side_effect=lambda *a,**kw:widget()): v.build_usb_setup()
        v.c20_status=Mock(); v.c20_status.read.return_value=False
        self.assertTrue(v.update_usb_setup()); self.assertTrue(v.update_usb_setup()); self.assertEqual(len(self.uploads),1)
        self.assertLessEqual(self.uploads[0].width,1280); self.assertLessEqual(self.uploads[0].height,720)
        v.root.winfo_width.return_value=640; v.root.winfo_height.return_value=480; v.update_usb_setup()
        self.assertEqual(len(self.uploads),2); self.assertLessEqual(self.uploads[-1].width,640)
        v.c20_status.read.return_value=True; self.assertFalse(v.update_usb_setup()); v.usb_setup.place_forget.assert_called_once(); v.root.after_idle.assert_called_once_with(v.render)


if __name__=='__main__': unittest.main()
