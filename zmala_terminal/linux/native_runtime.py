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


# @llr LLR-TERM-AUDIO-003
def load_linphone(owner):
    # ALSA caches its configuration on first use. Apply the C20's asymmetric
    # hardware rates before the SDK can enumerate or open any sound devices.
    # This environment belongs to this process and its playback helpers only.
    policy = Path(__file__).parent / 'media/audio/c20-alsa.conf'
    if not policy.is_file():
        raise RuntimeError('C20 audio policy is missing; repair the terminal installation')
    os.environ['ALSA_CONFIG_PATH'] = str(policy)
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
