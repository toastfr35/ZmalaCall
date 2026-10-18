"""Server-controlled C20 speech processing; Windows uses its SDK audio path."""
import logging


def requested_profile(config):
    return config.get('audio_profile', 'normal')


# @llr LLR-TERM-AUDIO-003
def configure(engine):
    from zmala_terminal.common.native_runtime import WINDOWS
    profile = engine.audio_profile = requested_profile(engine.config)
    engine.applied_audio_profile = 'normal'
    if profile == 'normal':
        return
    if profile != 'speech':
        raise ValueError('Audio profile must be normal or speech')
    if WINDOWS:
        logging.warning('Audio profile %s requires Linux; using normal audio', profile)
        return
    from zmala_terminal.linux.audio_processing import configure as configure_linux
    configure_linux(engine)
