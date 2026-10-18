"""Locate distro or explicitly prefixed Linux SDK libraries and resources."""
import ctypes as C
import os
from pathlib import Path
import ctypes.util

SDK = Path(os.environ.get('ZMALA_LINPHONE_PREFIX', '/usr'))

def library(name):
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
    return library('linphone')

def resource(kind):
    relative = {'msplugins': 'lib/mediastreamer/plugins',
                'sound_resources': 'share/sounds/linphone',
                'ring_resources': 'share/sounds/linphone/rings',
                'image_resources': 'share/images'}[kind]
    path = SDK / relative
    if kind == 'msplugins' and SDK == Path('/usr'):
        candidates = list((SDK / 'lib').glob('*/mediastreamer/plugins'))
        if candidates:
            path = candidates[0]
    # Leave the distro runtime's built-in defaults alone if a resource is absent.
    return path if path.is_dir() else None


def process_options():
    return {'start_new_session': True}
