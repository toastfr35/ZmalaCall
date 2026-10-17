"""Keep received H.264 bytes intact before handing them to OpenH264."""
import ctypes as C
from platforms.native_runtime import ROOT


def configure(engine):
    path = ROOT.parent / 'build_tools/runtime/zmala-h264-decoder.dll'
    if not path.is_file():
        raise RuntimeError('H.264 decoder adapter is missing; run build_tools/build-h264-decoder.py')
    engine.video_plugin = C.CDLL(str(path))
    factory = engine.dll.linphone_core_get_ms_factory
    factory.argtypes, factory.restype = [C.c_void_p], C.c_void_p
    register = engine.video_plugin.zmala_h264_decoder_register
    register.argtypes, register.restype = [C.c_void_p], C.c_int
    if register(factory(engine.core)):
        raise RuntimeError('Could not initialize the Windows H.264 decoder')
