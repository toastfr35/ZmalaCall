# @test T-LLT-091
# @requirements LLR-TERM-VIDEO-020
# @environment portable
# @plan Decode bounded JPEGs and reject oversized/wrong-format images. Feed current/stale worker results and expired leases through recording Tk widgets; ensure call changes and stop remove photo state without media calls.
# @pass Pixels preserve their aspect ratio; stale results never display; clearing and expiry release the overlay without altering audio or video handles.
import io
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from PIL import Image
from zmala_terminal.common.call_photo import CallPhoto, decode_photo
from zmala_terminal.common.model import State


class CallPhotoTests(unittest.TestCase):
    def test_bounded_decode(self):
        for fmt, size, valid in [('JPEG', (800, 400), True), ('PNG', (20, 20), False), ('JPEG', (1700, 2), False)]:
            output=io.BytesIO(); Image.new('RGB',size).save(output,fmt)
            if valid: self.assertEqual(decode_photo(output.getvalue()).size,size)
            else:
                with self.assertRaises(ValueError): decode_photo(output.getvalue())
        with self.assertRaises(ValueError): decode_photo(b'x'*(2097152+1))

    def fixture(self):
        root=Mock()
        with patch('zmala_terminal.common.call_photo.tk.Label'):
            view=CallPhoto(root)
        view.draw=Mock()
        engine=Mock(); engine.call_id.return_value='call'
        app=SimpleNamespace(engine=engine,configuration=Mock(),model=SimpleNamespace(state=State.IN_CALL,config={'call_photo_sharing':True}))
        view.owner=(engine,'call',app.configuration); view.next_poll=float('inf')
        return view,app

    def test_current_photo_then_expiry_and_stale_call_result(self):
        view,app=self.fixture(); image=Image.new('RGB',(80,40))
        view.results.put((view.owner,1,image,100))
        with patch('zmala_terminal.common.call_photo.time.monotonic',return_value=10): view.tick(app)
        self.assertIs(view.image,image); view.layer.place.assert_called_once()
        with patch('zmala_terminal.common.call_photo.time.monotonic',return_value=101): view.tick(app)
        self.assertIsNone(view.image)
        view.results.put((view.owner,1,image,1000)); app.model.state=State.HOME
        view.tick(app); self.assertIsNone(view.image)
        app.engine.end.assert_not_called(); app.engine.video.assert_not_called()

    def test_stop_snapshot_hides_overlay(self):
        view,app=self.fixture(); view.image=Image.new('RGB',(80,40));view.revision=1
        view.results.put((view.owner,2,None,0));view.tick(app)
        self.assertIsNone(view.image);view.layer.place_forget.assert_called()
