"""Locate native libraries and SDK resources on either operating system."""
import ctypes as C
import ctypes.util
import os
from pathlib import Path
import sys

WINDOWS = sys.platform == 'win32'
ROOT = Path(__file__).resolve().parents[1]
SDK = (ROOT.parent / 'build_tools/runtime/linphone/linphone-sdk/win64' if WINDOWS
       else Path(os.environ.get('ZMALA_LINPHONE_PREFIX', '/usr')))


def library(name):
    if WINDOWS:
        return C.CDLL(str(SDK / 'bin' / (name + '.dll')))
    if SDK != Path('/usr'):
        for directory in (SDK / 'lib', SDK / 'lib64'):
            path = directory / ('lib' + name + '.so')
            if path.exists():
                return C.CDLL(str(path))
    path = ctypes.util.find_library(name)
    if not path:
        raise RuntimeError(f'Missing native library {name}; run build_tools/linux/install-terminal.sh')
    return C.CDLL(path)


def load_linphone(owner):
    if WINDOWS:
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
    return library('linphone')


def resource(kind):
    relative = {'msplugins': 'lib/mediastreamer/plugins',
                'sound_resources': 'share/sounds/linphone',
                'ring_resources': 'share/sounds/linphone/rings',
                'image_resources': 'share/images'}[kind]
    path = SDK / relative
    if not WINDOWS and kind == 'msplugins' and SDK == Path('/usr'):
        candidates = list((SDK / 'lib').glob('*/mediastreamer/plugins'))
        if candidates:
            path = candidates[0]
    # Leave the distro runtime's built-in defaults alone if a resource is absent.
    return path if path.is_dir() else None


def process_options():
    return {'creationflags': 0x08000000} if WINDOWS else {'start_new_session': True}
