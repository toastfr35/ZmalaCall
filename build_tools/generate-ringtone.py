"""Synthesize the classic Nokia melody with a rounded monophonic phone tone.

The melody comes from Francisco Tarrega's public-domain Gran Vals (1902),
with the familiar ringtone ending. No Nokia recording is used.
"""
import math
from pathlib import Path
import struct
import wave

ROOT = Path(__file__).resolve().parents[1]
RATE = 16000
DURATION = 4
# MIDI pitches and lengths in eighth notes, at 240 quarter notes per minute.
MELODY = ((76, 1), (74, 1), (66, 2), (68, 2),
          (73, 1), (71, 1), (62, 2), (64, 2),
          (71, 1), (69, 1), (61, 2), (64, 2), (69, 4))
EIGHTH = 0.125


def sample(seconds):
    """Short gaps articulate the melody; smooth edges avoid audible clicks."""
    start = 0.1
    for pitch, eighths in MELODY:
        duration = eighths * EIGHTH
        sounding = duration - 0.018
        elapsed = seconds - start
        if 0 <= elapsed < sounding:
            attack = min(elapsed / 0.008, 1.0)
            release = min((sounding - elapsed) / 0.025, 1.0)
            envelope = attack * release
            frequency = 440 * 2 ** ((pitch - 69) / 12)
            phase = 2 * math.pi * frequency * elapsed
            tone = math.sin(phase) + 0.12 * math.sin(3 * phase) + 0.04 * math.sin(5 * phase)
            # Keep call volume unchanged and leave ample headroom below clipping.
            return round(32767 * 0.62 * envelope * tone)
        start += duration
    return 0


if __name__ == '__main__':
    # Preserve the asset path used by already-deployed terminals.
    destination = ROOT / 'zmala_terminal/assets/gentle-chime.wav'
    with wave.open(str(destination), 'wb') as audio:
        audio.setparams((1, 2, RATE, 0, 'NONE', 'not compressed'))
        audio.writeframes(b''.join(struct.pack('<h', sample(index / RATE))
                                  for index in range(RATE * DURATION)))
    print(destination)
