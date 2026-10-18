"""Load the pinned Windows SDK and keep its DLL search directories alive."""
import ctypes as C
import os
from zmala_terminal.common.paths import ROOT

SDK = ROOT.parent / 'build_tools/runtime/linphone/linphone-sdk/win64'

def library(name):
    return C.CDLL(str(SDK / 'bin' / (name + '.dll')))

def load_linphone(owner):
    # Retain search handles: closing them invalidates internal plugin loads.
    os.chdir(SDK)
    directories = [SDK / 'bin', SDK / 'lib/mediastreamer/plugins',
                   ROOT.parent / 'build_tools/runtime/angle-desktop/runtimes/win-x64/native']
    owner._dll_dirs = [os.add_dll_directory(str(directory)) for directory in directories]
    kernel = C.WinDLL('kernel32', use_last_error=True)
    kernel.SetDefaultDllDirectories.argtypes = [C.c_uint]
    kernel.SetDefaultDllDirectories(0x1000)
    owner._preloaded = [library(name) for name in ('openh264', 'soci_sqlite3_4_0')]
    owner._preloaded += [C.CDLL(str(directories[-1] / name)) for name in ('libGLESv2.dll', 'libEGL.dll')]
    return library('liblinphone')

def resource(kind):
    relative = {'msplugins': 'lib/mediastreamer/plugins',
                'sound_resources': 'share/sounds/linphone',
                'ring_resources': 'share/sounds/linphone/rings',
                'image_resources': 'share/images'}[kind]
    path = SDK / relative
    return path if path.is_dir() else None

def process_options():
    return {'creationflags': 0x08000000}
