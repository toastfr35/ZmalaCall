"""Independent playback gains; retain the C20's existing -28..0 dB level curve."""
import array
import io
import math
import os
from pathlib import Path
import sys
import tempfile
import wave


# @llr LLR-TERM-AUDIO-010
def playback_environment():
    """Audio helpers need the ALSA policy, not the SDK's TURN interposer/dependencies."""
    environment = dict(os.environ)
    environment.pop('LD_PRELOAD', None)
    return environment


# @llr LLR-TERM-AUDIO-010
def gain_db(percent):
    if type(percent) is not int or not 0 <= percent <= 100:
        raise ValueError('Volume must be 0–100 percent')
    return -28 * (100-percent)/100 if percent else -120


def scale_wav(data, percent):
    """Scale validated mono PCM, never a global mixer or microphone control."""
    db = gain_db(percent)
    gain = 10 ** (db/20) if percent else 0
    with wave.open(io.BytesIO(data), 'rb') as source:
        if source.getsampwidth() != 2 or source.getnchannels() != 1 or source.getframerate() != 16000:
            raise ValueError('Expected mono 16-bit 16 kHz sound')
        if source.getnframes() > 16000*30:
            raise ValueError('Sound exceeds thirty seconds')
        samples = array.array('h', source.readframes(source.getnframes()))
    if sys.byteorder != 'little':
        samples.byteswap()
    samples = array.array('h', (round(value*gain) for value in samples))
    if sys.byteorder != 'little':
        samples.byteswap()
    output = io.BytesIO()
    with wave.open(output, 'wb') as target:
        target.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        target.writeframes(samples.tobytes())
    return output.getvalue()


# @llr LLR-TERM-AUDIO-009, LLR-TERM-AUDIO-010
class ToneLevels:
    """One RAM-backed scaled tone per player; delete it on change/shutdown."""
    def __init__(self):
        self.key, self.path = None, None

    def prepare(self, file, percent):
        file = Path(file)
        info = file.stat()
        key = (str(file), info.st_mtime_ns, info.st_size, percent)
        if key != self.key:
            if info.st_size > 44+16000*2*30:
                raise ValueError('Ringtone is too large')
            data = scale_wav(file.read_bytes(), percent)
            self.close()
            # /run is RAM-backed on the Pi; no per-level writes to the microSD.
            folder = Path('/run/zmalacall')
            if not folder.is_dir():
                folder = Path(tempfile.gettempdir())  # Disposable desktop/test host.
            with tempfile.NamedTemporaryFile(prefix='ringtone-', suffix='.wav', dir=folder, delete=False) as output:
                output.write(data)
                self.path = Path(output.name)
            self.key = key
        return self.path

    def close(self):
        if self.path:
            self.path.unlink(missing_ok=True)
        self.key, self.path = None, None


# @llr LLR-TERM-AUDIO-010
def click_pcm(percent, button='left'):
    """Soft navigation tap, rising green cue or low red double tap; never a ringtone."""
    tones = {'left': ((400,960),), 'right': ((400,960),), 'pointer': ((400,960),),
             'green': ((400,960),(600,960)),
             'red': ((250,960),(0,1440),(250,960))}
    if button not in tones:
        raise ValueError('Unknown feedback button')
    db = gain_db(percent)
    gain = 10 ** (db/20) if percent else 0
    samples = array.array('h')
    for frequency, frames in tones[button]:
        for i in range(frames):
            envelope = min(1,i/96)*(1-i/frames)**2
            value = round(14000*gain*math.sin(2*math.pi*frequency*i/48000)*envelope)
            samples.extend((value,value))
    if sys.byteorder != 'little':
        samples.byteswap()
    return samples.tobytes()
