"""Opt-in Windows SDK regression; synthetic pictures only, no devices or calls.

Run after setup-runtime.py: python build_tools/tests/h264_decoder_native.py
The compressed fixture is three gray 1080p frames encoded by the Pi's V4L2
encoder at 15 fps, 2440 kbit/s, baseline, GOP 30. Its SPS contains the valid
emulation-prevention sequence that the bundled SDK decoder corrupts.
"""
import base64
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = (
    'eNrt3L9KQgEUx/Fz9dINw6HRxT+D6AsERqHS4ugLVKKbINSm0OCdxLYiWlxyaIhaBUeTBKkhqK1JB9EaAnGTLvekryAODt/lcPjwO2c4D3BExIgd2fHbZlAu53kRrxjLEhw2JVpIS+707MKuXO/JIhd/9xzbyyZat7Oqr6o3qjF1s+rc6Tyls6qOYBiGYRiGYRiGYRiGYRiGYRiGYRiGYRiGYRiGYRiGYRiGYRiGYRiGYRiGYRiGYRiGYRiGYRiGYRiGYRiGYRiGYRiG4Q3g/ou5m5aBbD+OW8UDVTMpvt5f8aesna7lPjU+7r9bX21LJ53FiHPetSTsS5Tear9bRsYfOBmkuOe6+EpWeQgeaXgOJfnZcwPT/ENouu+suMXcefY6oX+vAbLN'
)


def main():
    sdk = ROOT / 'runtime/linphone/linphone-sdk/win64'
    compiler = shutil.which('gcc.exe')
    if not compiler:
        raise RuntimeError('Windows x64 GCC is required.')
    with tempfile.TemporaryDirectory(prefix='zmala-h264-') as directory:
        folder = Path(directory)
        stream = folder / 'gray.h264'
        stream.write_bytes(zlib.decompress(base64.b64decode(FIXTURE)))
        executable = folder / 'test.exe'
        subprocess.run([compiler, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                        '-isystem', str(sdk / 'include'), str(ROOT / 'native/test_h264_decoder.c'),
                        *[str(sdk / 'lib' / (name + '.lib')) for name in ('mediastreamer2', 'ortp', 'bctoolbox')],
                        '-o', str(executable)], check=True)
        environment = dict(os.environ, PATH=str(sdk / 'bin') + os.pathsep + os.environ['PATH'])
        subprocess.run([str(executable), str(ROOT / 'runtime/zmala-h264-decoder.dll'), str(stream)],
                       env=environment, check=True, timeout=20)


if __name__ == '__main__':
    main()
