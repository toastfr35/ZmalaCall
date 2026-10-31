"""Construction boundary for terminal hardware services.

Keep the existing adapters (including their disabled Windows behaviour) for this
first migration. Callers own shutdown; this module does not start a second event
loop or hide device lifetime behind global singletons.
"""
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PlatformServices:
    fan: object
    usb_power: object
    television: object


# @llr LLR-TERM-START-003
def create_platform_services(root: Path) -> PlatformServices:
    """Construct the existing adapters at startup, rather than at module import.

    Imports stay here so the composition root no longer selects hardware classes.
    Explicit Windows substitutes can replace disabled adapters in a later step.
    """
    from zmala_terminal.linux.argon_fan import ArgonFan
    from zmala_terminal.linux.usb_power import UsbPower
    from zmala_terminal.linux.tv_control import TVControl

    return PlatformServices(ArgonFan(), UsbPower(root), TVControl())
