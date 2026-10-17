"""Expose Avalonia ANGLE's prefixed exports under the names Liblinphone loads.

The SDK initializes its renderer before it receives a per-window resolver.
The bridges forward exports and count successful frame presentations for the
native video self-test. They have no C runtime dependency.
"""
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent
DEST = ROOT / 'runtime/angle-desktop/runtimes/win-x64/native'
HEADER = ROOT / 'runtime/linphone/linphone-sdk/win64/include/mediastreamer2/msogl_functions.h'


def build():
    compiler = shutil.which('gcc.exe')
    if not compiler:
        raise RuntimeError('A Windows x64 GCC is needed to build the ANGLE export forwarders.')
    architecture = subprocess.check_output([compiler, '-dumpmachine'], text=True).strip()
    if architecture != 'x86_64-w64-mingw32':
        raise RuntimeError(f'Expected Windows x64 GCC; found {architecture}')
    fields = re.findall(r'^\s*(?:resolve\w+|gl\w+Signature)\s+((?:gl|egl)\w+)\s*;', HEADER.read_text(), re.M)
    for prefix, filename in [('egl', 'libEGL'), ('gl', 'libGLESv2')]:
        exports = []
        for name in fields:
            if name.startswith(prefix) and (prefix == 'egl' or not name.startswith('egl')):
                avalonia = ('EGL_' if prefix == 'egl' else 'GL_') + name[len(prefix):]
                if name == 'glGetQueryObjectui64v':
                    avalonia += 'EXT'
                custom = {'eglSwapBuffers':'family_swap', 'eglGetProcAddress':'family_get_proc'}
                exports.append(f'{name}={custom[name]}' if name in custom else f'{name}=av_libglesv2.{avalonia}')
        definition = DEST / f'{filename}.def'
        definition.write_text(f'LIBRARY {filename}\nEXPORTS\n' + '\n'.join(exports) + '\n')
        inputs = [str(ROOT / 'native/angle_bridge.c'), '-lkernel32'] if prefix == 'egl' else []
        subprocess.run([compiler, '-shared', '-nostdlib', '-Wl,--entry,0', str(definition), *inputs,
                        '-o', str(DEST / f'{filename}.dll')], check=True)


if __name__ == '__main__':
    build()
