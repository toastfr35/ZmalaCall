"""Select the CEC adapter belonging to a connected DRM output, including Pi 4."""
from pathlib import Path
import struct


def connector(device):
    """Read the kernel mapping; adapter and DRM card numbers need not match."""
    import fcntl  # Linux only; keep Windows imports usable.
    data = bytearray(68)  # cec_connector_info: type + 16 uint32 union words.
    with open(device, 'rb', buffering=0) as stream:
        fcntl.ioctl(stream, 0x8044610a, data, True)  # CEC_ADAP_G_CONNECTOR_INFO
    kind, card, identifier = struct.unpack_from('=III', data)
    return (card, identifier) if kind == 1 else None


# @llr LLR-TERM-TV-009
def select_device(current=None, devices=Path('/dev'), drm=Path('/sys/class/drm')):
    """Prefer a detected display, then scanout, retaining the current port on ties.

    A disconnected fallback allows standby TVs to be woken. Older adapters
    without connector-info support retain the original first-device behavior.
    """
    candidates = sorted(str(p) for p in devices.glob('cec[0-9]*'))
    connected = []
    for device in candidates:
        try:
            mapping = connector(device)
            if mapping is None:
                continue
            card, identifier = mapping
            for output in drm.glob(f'card{card}-HDMI-A-*'):
                if (int((output / 'connector_id').read_text()) == identifier and
                        (output / 'status').read_text().strip() == 'connected'):
                    # A forced boot mode can report an empty HDMI socket as
                    # connected. Do not let it pin the observer to the wrong TV.
                    try:
                        detected = bool((output / 'edid').read_bytes())
                    except OSError:
                        detected = False
                    try:
                        enabled = (output / 'enabled').read_text().strip() == 'enabled'
                    except OSError:
                        enabled = False
                    connected.append(((detected, enabled), device))
                    break
        except (OSError, ValueError):
            continue
    if connected:
        best = max(score for score, device in connected)
        preferred = [device for score, device in connected if score == best]
        return current if current in preferred else preferred[0]
    return current if current in candidates else next(iter(candidates), '/dev/cec0')
