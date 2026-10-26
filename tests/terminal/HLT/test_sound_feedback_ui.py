# @test T-HLT-035
# @requirements HLR-TERM-AUDIO-001, HLR-TERM-AUDIO-002, HLR-TERM-UI-013
# @environment display
# @plan Use real Tk/input/settings/volume controllers with substituted hardware and player.
# Check the 16 native labels and wrap boundaries, independent ringtone/button editors,
# one feedback request for a held key, distinct green/red cues and a compact black volume panel over the carousel
# and simulated call video. Preserve selection and call through adjustments and close.
# @pass Labels/options/wrapping and geometry assertions pass; input requests feedback once
# per distinct press, and opening/closing the overlay preserves the underlying screen.
# This checks UI orchestration, not physical audibility, ALSA mixing or camera stability.
import os
import sys
import unittest
from unittest.mock import Mock,patch
from tests.support.terminal.ui_fixture import terminal_fixture,pump
from zmala_terminal.common.local_settings import FIELDS,SettingsDraft
from zmala_terminal.common.localization import LANGUAGES
from zmala_terminal.common.model import State


@unittest.skipUnless(sys.platform=='linux' and os.environ.get('DISPLAY'),'Linux Tk display required')
class SoundFeedbackUI(unittest.TestCase):
    def test_languages_independent_levels_feedback_and_bounded_overlay(self):
        with terminal_fixture() as (app,directory), \
                patch('zmala_terminal.linux.c20_volume.status',return_value=(50,50,False)), \
                patch('zmala_terminal.linux.c20_volume.request'):
            app.action_sounds=Mock()
            app.keypress('left');app.keypress('left');app.keyrelease('left')
            app.action_sounds.play.assert_called_once_with(20,'left')
            app.keypress('green');app.keyrelease('green')
            app.action_sounds.play.assert_called_with(20,'green')
            self.assertEqual(app.model.state,State.CONFIRMING)
            app.keypress('red');app.keyrelease('red')
            app.action_sounds.play.assert_called_with(20,'red')
            self.assertEqual(app.model.state,State.HOME)
            pump(app)
            draft=SettingsDraft();draft.row=FIELDS.index('language');draft.open(app.model.config)
            self.assertEqual(draft.options,list(LANGUAGES));self.assertEqual(len(draft.options),16)
            draft.index=0;draft.move(-1);self.assertEqual(draft.index,15)
            draft.move(1);self.assertEqual(draft.index,0)
            for key,default in [('ringtone_volume',50),('action_sound_volume',20)]:
                draft.row=FIELDS.index(key);draft.open(app.model.config)
                self.assertEqual(draft.options,list(range(0,101,5)))
                self.assertEqual(draft.options[draft.index],default)
            selected=app.model.selected['id'];engine=app.engine
            for state in (State.HOME,State.IN_CALL):
                app.model.state=state;app.model.contact=app.model.selected if state==State.IN_CALL else None
                engine.call=123 if state==State.IN_CALL else None
                app.render();pump(app)
                app.volume_control.pointer(True);app.volume_control.pointer(False);pump(app)
                panel=app.volume_control.canvas
                self.assertTrue(panel.winfo_ismapped())
                self.assertEqual(panel.cget('background'),'#000000')
                self.assertLess(panel.winfo_width(),app.root.winfo_width())
                self.assertLess(panel.winfo_height(),app.root.winfo_height()/3)
                app.physical_press('right');app.volume_control.refresh()
                self.assertEqual(app.model.selected['id'],selected)
                self.assertIs(app.engine,engine);self.assertEqual(app.model.state,state)
                if state==State.IN_CALL:self.assertTrue(app.video.winfo_ismapped())
                app.volume_control.pointer(True);app.volume_control.pointer(False)
                self.assertFalse(panel.winfo_ismapped())
