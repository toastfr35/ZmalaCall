"""Build the Windows H.264 receive adapter against the pinned SDK."""
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent


def build():
    compiler = shutil.which('gcc.exe')
    if not compiler:
        raise RuntimeError('Windows x64 GCC is required to build the H.264 decoder adapter.')
    architecture = subprocess.check_output([compiler, '-dumpmachine'], text=True).strip()
    if architecture != 'x86_64-w64-mingw32':
        raise RuntimeError(f'Expected Windows x64 GCC; found {architecture}')
    sdk = ROOT / 'runtime/linphone/linphone-sdk/win64'
    target = ROOT / 'runtime/zmala-h264-decoder.dll'
    temporary = target.with_suffix('.new.dll')
    subprocess.run([compiler, '-std=c11', '-shared', '-O2', '-Wall', '-Wextra', '-Werror',
                    '-isystem', str(sdk / 'include'), str(ROOT / 'native/h264_decoder.c'),
                    *[str(sdk / 'lib' / (name + '.lib')) for name in
                      ('mediastreamer2', 'ortp', 'bctoolbox', 'openh264_dll')],
                    '-o', str(temporary)], check=True)
    temporary.replace(target)


if __name__ == '__main__':
    build()
