"""Read carrier state without privilege or an external network dependency."""
from pathlib import Path


# @llr LLR-TERM-MAINT-007
def network_link_available(wifi_only=False):
    try:
        for device in Path('/sys/class/net').iterdir():
            if device.name == 'lo':
                continue
            if wifi_only and not ((device / 'wireless').exists() or (device / 'phy80211').exists()):
                continue
            try:
                if (device / 'operstate').read_text().strip() == 'up':
                    return True
            except OSError:
                continue
        return False
    except OSError:
        return None


def wifi_link_available():
    """Association state of a wireless interface, never inferred from Ethernet."""
    return network_link_available(wifi_only=True)
