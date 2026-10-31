"""Supported all-in-one peripherals; legacy c20 configuration keys stay compatible."""
from pathlib import Path
import re

USB_MODELS = {('0525', 'a4ad'): 'C20', ('0525', 'a4b0'): 'C10'}

# @llr LLR-TERM-POWER-010, LLR-TERM-SETUP-022
def supported_name(name):
    if isinstance(name, bytes):
        name = name.decode('utf-8', errors='replace')
    return bool(re.search(r'\bnuroum c(?:10|20)\b', name, re.IGNORECASE))

# @llr LLR-TERM-POWER-010, LLR-TERM-AUDIO-007
def audio_card(root=Path('/proc/asound')):
    """Resolve each time: USB replacement can change the model and card index.

    Refuse missing or ambiguous hardware instead of routing any sound to HDMI.
    """
    cards = []
    for entry in root.glob('card*/id'):
        try:
            name = entry.read_text().strip()
            if name in ('C10', 'C20'):
                cards.append(name)
        except OSError:
            continue
    if len(cards) != 1:
        raise FileNotFoundError('Connect exactly one Nuroum C10 or C20')
    return cards[0]

# @llr LLR-TERM-POWER-010
def playback_device():
    return 'default:' + audio_card()
