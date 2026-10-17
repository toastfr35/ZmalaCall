"""Build the QR-aware camera preview adapter against the installed SDK headers."""
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'native/qr_preview.c'
TARGET = ROOT / 'runtime/zmala-qr-preview.dll'

def build():
    compiler = shutil.which('gcc.exe')
    if not compiler:
        raise RuntimeError('Windows x64 GCC is required to build the QR preview adapter.')
    architecture = subprocess.check_output([compiler, '-dumpmachine'], text=True).strip()
    if architecture != 'x86_64-w64-mingw32':
        raise RuntimeError(f'Expected Windows x64 GCC; found {architecture}')
    subprocess.run([compiler, '-shared', '-O2', '-I', str(ROOT / 'runtime/linphone/linphone-sdk/win64/include'),
                    str(SOURCE), '-o', str(TARGET), '-lkernel32'], check=True)

if __name__ == '__main__':
    build()
