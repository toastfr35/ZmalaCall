"""Opt-in installed-SDK check of applied sizes and packet repair, without calls.

Run using the terminal Python runtime. Linux requires the installed C20 plugin
and devices; this never starts camera preview or microphone capture.
"""
import ctypes as C
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from zmala_terminal.common.engine import Engine

for preset, expected in [('360p', (640, 480)), ('480p', (640, 480)),
                         ('720p', (1280, 720)), ('1080p', (1920, 1080))]:
    engine = Engine({'video_resolution': preset}, lambda *args: None,
                    lambda *args: None, profile='video-settings-native')
    try:
        actual = engine.core_get_preferred_video_size(engine.core)
        nack = engine.dll.linphone_core_retransmission_on_nack_enabled
        nack.argtypes, nack.restype = [C.c_void_p], C.c_int
        assert (actual.width, actual.height) == expected, preset
        assert nack(engine.core), preset
        print(f'{preset}: {actual.width}x{actual.height}; NACK enabled', flush=True)
    finally:
        engine.close()
