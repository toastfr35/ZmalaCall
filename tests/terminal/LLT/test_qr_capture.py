# @test T-LLT-058
# @requirements LLR-TERM-SETUP-027, LLR-TERM-SETUP-028
# @environment portable
# @plan Stub V4L2, X11, ZBar and Tk at their API boundaries while executing the real Linux QR capture/decoder. Check 640x480/15fps requests, wrapper embedding and bounded preview, independent frame/decode throttles, repeated-code suppression and exact UTF-8 symbol bounds. Inject missing camera/display/tree, invalid image/UTF-8 and capture/decode failures; assert acquired resources are released on startup failure and close.
# @pass Decode and cleanup assertions pass without a camera/display or native libraries. Pixel quality and real USB/X11 interoperability remain system tests.
import ctypes as C
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch, call


class QRNativeTests(unittest.TestCase):
    def setUp(self):
        self.cv = Mock(CAP_V4L2=1,CAP_PROP_FRAME_WIDTH=2,CAP_PROP_FRAME_HEIGHT=3,CAP_PROP_FPS=4,
                       COLOR_BGR2GRAY=5,COLOR_BGR2RGB=6)
        path=Path(__file__).resolve().parents[3]/'zmala_terminal/linux/qr.py'
        spec=importlib.util.spec_from_file_location('qr_capture_fixture',path)
        self.qr=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,{'cv2':self.cv}): spec.loader.exec_module(self.qr)

    def widgets(self):
        root=Mock(); root.winfo_id.return_value=21
        for patcher in (patch.object(self.qr.tk,'Tk',return_value=root),patch.object(self.qr.tk,'Label'),
                        patch.object(self.qr,'QRDecoder'),patch.object(self.qr.ImageTk,'PhotoImage'),
                        patch.object(self.qr.Image,'fromarray')):
            patcher.start(); self.addCleanup(patcher.stop)
        return root

    def x11(self, opened=1, found=1):
        library=Mock(); library.XOpenDisplay.return_value=opened
        children=(C.c_ulong*1)(34)
        def query(display,window,top,wrapper,output,count):
            C.cast(wrapper,C.POINTER(C.c_ulong))[0]=22
            C.cast(output,C.POINTER(C.POINTER(C.c_ulong)))[0]=C.cast(children,C.POINTER(C.c_ulong))
            return found
        library.XQueryTree.side_effect=query
        def geometry(display,parent,root,x,y,w,h,border,depth):
            C.cast(w,C.POINTER(C.c_uint))[0]=320
            C.cast(h,C.POINTER(C.c_uint))[0]=180
            return 1
        library.XGetGeometry.side_effect=geometry
        return library

    def test_camera_requests_and_embedded_wrapper_preview_geometry(self):
        root=self.widgets(); x=self.x11()
        with patch.object(self.qr.C,'CDLL',return_value=x):
            scanner=self.qr.NativeQRScanner(Mock(),101,camera='ZmalaMJPEG: /dev/video2')
        self.cv.VideoCapture.assert_called_once_with('/dev/video2',1)
        self.cv.VideoCapture.return_value.set.assert_has_calls([call(2,640),call(3,480),call(4,15)])
        x.XReparentWindow.assert_called_once_with(1,22,101,0,0); x.XFree.assert_called_once()
        scanner.capture.read.return_value=(True,object()); scanner.decoder.decode.return_value=[]
        with patch.object(self.qr.time,'monotonic',return_value=1): scanner.iterate()
        root.geometry.assert_called_with('320x180+0+0')
        self.qr.Image.fromarray.return_value.thumbnail.assert_called_once_with((320,180),self.qr.Image.Resampling.BILINEAR)
        scanner.close(); x.XCloseDisplay.assert_called_once_with(1)
        self.cv.VideoCapture.return_value.release.assert_called_once()

    def test_static_frame_decode_cadence_and_repeat_suppression(self):
        self.widgets(); callback=Mock(); scanner=self.qr.NativeQRScanner(callback,camera='StaticImage: Static picture')
        self.cv.VideoCapture.assert_not_called()
        scanner.iterate(); scanner.decoder.decode.assert_not_called()
        scanner.next_frame=0
        scanner.set_static_picture('qr.png'); scanner.decoder.decode.return_value=['code']
        for now in (1,1.05,1.2,1.41,4.5):
            with patch.object(self.qr.time,'monotonic',return_value=now): scanner.iterate()
        self.assertEqual(scanner.decoder.decode.call_count,3)
        self.assertEqual(callback.call_args_list,[call('code'),call('code')])
        scanner.decoder.decode.return_value=['new-code']
        with patch.object(self.qr.time,'monotonic',return_value=5): scanner.iterate()
        callback.assert_called_with('new-code')
        self.cv.imread.return_value=None
        with self.assertRaisesRegex(RuntimeError,'unavailable'): scanner.set_static_picture('missing')
        scanner.close()

    def test_capture_failure_and_initialization_failure_release_camera(self):
        self.widgets()
        self.cv.VideoCapture.return_value.isOpened.return_value=False
        with self.assertRaisesRegex(RuntimeError,'No V4L2'): self.qr.NativeQRScanner(Mock())
        self.cv.VideoCapture.return_value.release.assert_called_once()
        self.qr.QRDecoder.return_value.close.assert_called_once(); self.qr.tk.Tk.return_value.destroy.assert_called_once()
        self.cv.VideoCapture.return_value.isOpened.return_value=True
        scanner=self.qr.NativeQRScanner(Mock(),camera='V4L2: /dev/video3')
        scanner.capture.read.return_value=(False,None)
        with self.assertRaisesRegex(RuntimeError,'stopped delivering'): scanner.iterate()
        scanner.close()

    def test_embedding_failure_releases_decoder_and_window(self):
        for opened,found in ((0,1),(1,0)):
            with self.subTest(opened=opened,found=found):
                root=self.widgets(); x=self.x11(opened,found)
                with patch.object(self.qr.C,'CDLL',return_value=x), self.assertRaises(RuntimeError):
                    self.qr.NativeQRScanner(Mock(),101)
                self.qr.QRDecoder.return_value.close.assert_called_once()
                root.destroy.assert_called_once()
                if opened: x.XCloseDisplay.assert_called_once_with(1)
                self.doCleanups()

    def test_decoder_qr_only_symbol_bounds_and_finally_cleanup(self):
        library=Mock(); library.zbar_image_scanner_create.return_value=10
        library.zbar_image_create.return_value=11
        gray=SimpleNamespace(shape=(480,640),ctypes=SimpleNamespace(data=1234),nbytes=307200)
        self.cv.cvtColor.return_value=gray
        with patch.object(self.qr.C,'CDLL',return_value=library): decoder=self.qr.QRDecoder()
        library.zbar_image_scanner_set_config.assert_has_calls([call(10,0,0,0),call(10,64,0,1)])
        library.zbar_image_first_symbol.return_value=1
        library.zbar_symbol_next.side_effect=[2,3,4,0]
        library.zbar_symbol_get_data_length.side_effect=[0,8193,4,8192]
        texts=[C.create_string_buffer('éé'.encode()),C.create_string_buffer(b'a'*8192)]
        library.zbar_symbol_get_data.side_effect=[C.addressof(value) for value in texts]
        self.assertEqual(list(decoder.decode(object())),['éé','a'*8192])
        library.zbar_image_set_size.assert_called_once_with(11,640,480)
        library.zbar_image_set_data.assert_called_once_with(11,1234,307200,None)
        library.zbar_image_destroy.assert_called_once_with(11)
        library.zbar_scan_image.side_effect=RuntimeError('decoder failure')
        with self.assertRaisesRegex(RuntimeError,'decoder failure'): list(decoder.decode(object()))
        self.assertEqual(library.zbar_image_destroy.call_count,2)
        library.zbar_scan_image.side_effect=None
        library.zbar_symbol_get_data_length.side_effect=None
        library.zbar_symbol_get_data_length.return_value=1
        invalid=C.create_string_buffer(b'\xff')
        library.zbar_symbol_get_data.side_effect=None
        library.zbar_symbol_get_data.return_value=C.addressof(invalid)
        with self.assertRaises(UnicodeDecodeError): list(decoder.decode(object()))
        self.assertEqual(library.zbar_image_destroy.call_count,3)
        decoder.close(); decoder.close(); library.zbar_image_scanner_destroy.assert_called_once_with(10)
