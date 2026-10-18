"""C20 native speech echo processing."""
import ctypes as C
import logging
from pathlib import Path

# @llr LLR-TERM-AUDIO-003
def configure(engine):
    profile = engine.audio_profile
    path = Path(__file__).parent / 'media/audio/libzmala_speech_audio.so'
    if not path.is_file():
        logging.warning('Audio profile %s plugin is not installed; using normal audio', profile)
        return
    engine.speech_audio_plugin = C.CDLL(str(path))
    factory = engine.dll.linphone_core_get_ms_factory
    factory.argtypes, factory.restype = [C.c_void_p], C.c_void_p
    register = engine.speech_audio_plugin.zmala_speech_audio_register
    register.argtypes, register.restype = [C.c_void_p, C.c_int], C.c_int
    rate = 16000
    if register(factory(engine.core), rate):
        raise RuntimeError('Could not configure speech echo cancellation')
    engine.applied_audio_profile = profile
    # Preserve the verified echo window until acoustic testing supports a
    # shorter one. Device changes alone do not establish that room echo fell.
    engine.config_set_int(engine.core_get_config(engine.core), b'sound', b'ec_tail_len', 500)
    logging.info('Audio profile %s: echo cancellation enabled, DSP capped at %s Hz', profile, rate)
