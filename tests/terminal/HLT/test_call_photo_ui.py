# @test T-HLT-039
# @requirements HLR-TERM-VIDEO-001
# @environment display
# @plan Use real Tk and disposable terminal state with a fake authenticated image API. Share a landscape image, resize portrait/landscape, stop sharing and end the call. Inspect full-window coverage, aspect ratio and preserved native video surface IDs.
# @pass Photo replaces both video views, stays undistorted across resize, clears on stop/end and never invokes media termination; this is not physical audio/video qualification.
import io
import json
import os
import unittest
from PIL import Image
from tests.support.terminal.ui_fixture import terminal_fixture, pump
from zmala_terminal.common.model import State


@unittest.skipUnless(os.environ.get('DISPLAY'), 'Virtual or physical display required')
class CallPhotoUITests(unittest.TestCase):
    def test_photo_overlay_preserves_call_surfaces(self):
        with terminal_fixture() as (app, directory):
            output=io.BytesIO(); Image.new('RGB',(600,300),'blue').save(output,'JPEG')
            state={'revision':1,'sharing':True,'remaining_ms':12000}
            app.model.config['call_photo_sharing']=True
            app.model.state=State.IN_CALL; app.model.contact=app.model.selected
            app.engine.call_id.return_value='fixture-call'
            from unittest.mock import Mock
            app.configuration=Mock()
            app.configuration.request.side_effect=lambda route: output.getvalue() if 'image=1' in route else json.dumps(state).encode()
            app.render();app.root.update()
            handles=(app.video_window,app.preview_window)
            def tick():
                app.shared_photo.tick(app)
                return app.shared_photo.image is not None
            pump(app,tick)
            for geometry in ('900x620','1280x720'):
                app.root.geometry(geometry);app.root.update();app.shared_photo.draw()
                view=app.shared_photo
                self.assertEqual(view.layer.winfo_width(),app.root.winfo_width())
                self.assertEqual(view.layer.winfo_height(),app.root.winfo_height())
                self.assertAlmostEqual(view.picture.width()/view.picture.height(),2,places=2)
                self.assertEqual((app.video_window,app.preview_window),handles)
            state.update(revision=2,sharing=False)
            app.shared_photo.next_poll=0
            def stopped():
                app.shared_photo.tick(app)
                return app.shared_photo.image is None
            pump(app,stopped)
            self.assertFalse(app.shared_photo.layer.winfo_ismapped())
            state.update(revision=3,sharing=True);app.shared_photo.next_poll=0
            pump(app,tick)
            app.model.state=State.HOME;app.shared_photo.tick(app)
            self.assertIsNone(app.shared_photo.image)
            app.engine.end.assert_not_called()
