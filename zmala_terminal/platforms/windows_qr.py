"""Accountless camera preview; runs only inside the isolated QR worker process."""
import ctypes as C
import time
from engine import Engine
from linphone_api import P, S, I, ROOT, SDK, encoded, VIDEO_EVENT_CB


class NativeQRScanner(Engine):
    """QR-aware accountless preview, used inside the isolated camera worker."""
    def __init__(self, on_qr, video_window=0, profile='terminal', camera=None):
        self.preview = None
        self.next_search = None
        super().__init__({'terminal_settings': {'camera': camera} if camera else {}},
                         lambda *args: None, lambda *args: None, video_window, profile)
        for name, result, arguments in [
                ('factory_is_qrcode_available', I, [P]),
                ('core_get_ms_factory', P, [P]),
                ('core_set_static_picture', I, [P, S])]:
            function = getattr(self.dll, 'linphone_' + name)
            function.restype, function.argtypes = result, arguments
            setattr(self, name, function)
        if not self.factory_is_qrcode_available(self.factory):
            self.close()
            raise RuntimeError('This Liblinphone runtime has no QR decoder')
        def decoded(user, source, event, data):
            # MS_QRCODE_READER_QRCODE_FOUND includes a 255-byte text buffer.
            if event == self.qr_event_id and data:
                value = C.string_at(data, 255).split(b'\0', 1)[0]
                try:
                    text = value.decode('utf-8')
                except UnicodeDecodeError:
                    # The Windows 5.4 decoder can return the local code page.
                    page = C.WinDLL('kernel32').GetACP()
                    text = value.decode('cp' + str(page), errors='replace')
                on_qr(text)
                self.next_search = time.monotonic() + 3
        self.qr_callback = VIDEO_EVENT_CB(decoded)
        self.preview_bridge = C.CDLL(str(ROOT.parent / 'build_tools/runtime/zmala-qr-preview.dll'))
        for name, result, arguments in [('initialize', I, []),
                ('event_id', C.c_uint, []),
                ('start', P, [P, P, P, VIDEO_EVENT_CB]), ('refresh', None, [P]),
                ('reset_search', None, [P]), ('stop', None, [P])]:
            function = getattr(self.preview_bridge, 'zmala_qr_' + name)
            function.restype, function.argtypes = result, arguments
        if not self.preview_bridge.zmala_qr_initialize():
            self.close()
            raise RuntimeError('The camera preview adapter is incompatible with this SDK')
        self.qr_event_id = self.preview_bridge.zmala_qr_event_id()
        media = C.CDLL(str(SDK / 'bin/mediastreamer2.dll'))
        media.ms_factory_get_web_cam_manager.restype, media.ms_factory_get_web_cam_manager.argtypes = P, [P]
        media.ms_web_cam_manager_get_cam.restype, media.ms_web_cam_manager_get_cam.argtypes = P, [P, S]
        factory = self.core_get_ms_factory(self.core)
        manager = media.ms_factory_get_web_cam_manager(factory)
        camera_id = self.core_get_video_device(self.core)
        device = media.ms_web_cam_manager_get_cam(manager, camera_id)
        if not device:
            self.close()
            raise RuntimeError('No camera is available for QR setup')
        self.preview_arguments = (factory, device, C.addressof(self.ogl) if video_window else None, self.qr_callback)
        self.preview = self.preview_bridge.zmala_qr_start(*self.preview_arguments)
        if not self.preview:
            self.close()
            raise RuntimeError('Camera QR preview could not start')

    def set_static_picture(self, image):
        """Use a printed QR test image with the SDK's static camera."""
        self.preview_bridge.zmala_qr_stop(self.preview)
        self.preview = None
        if self.core_set_static_picture(self.core, encoded(image)):
            raise RuntimeError('The static QR test image is unavailable')
        self.preview = self.preview_bridge.zmala_qr_start(*self.preview_arguments)

    def iterate(self):
        super().iterate()
        if self.preview and self.next_search is not None and time.monotonic() >= self.next_search:
            self.next_search = None
            self.preview_bridge.zmala_qr_reset_search(self.preview)

    def close(self):
        if self.preview:
            self.preview_bridge.zmala_qr_stop(self.preview)
            self.preview = None
        super().close()


