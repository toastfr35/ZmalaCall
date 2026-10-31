"""Construction boundary for terminal hardware services.

Select desktop substitutes without importing Linux power and television code. Callers own shutdown; this module does not start a second event
loop or hide device lifetime behind global singletons.
"""
from dataclasses import dataclass
from pathlib import Path
import sys
import logging


@dataclass(frozen=True)
class PlatformServices:
    fan: object
    usb_power: object
    television: object


# @llr LLR-TERM-START-003
def create_platform_services(root: Path) -> PlatformServices:
    """Construct the existing adapters at startup, rather than at module import.

    Imports stay here so the composition root no longer selects hardware classes.
    Windows substitutes do not load Linux modules or start hardware workers.
    """
    if sys.platform == 'win32':
        from zmala_terminal.windows.platform_services import DesktopFan, DesktopPower, DesktopTelevision
        return PlatformServices(DesktopFan(), DesktopPower(root), DesktopTelevision())

    from zmala_terminal.linux.argon_fan import ArgonFan
    from zmala_terminal.linux.usb_power import UsbPower
    from zmala_terminal.linux.tv_control import TVControl

    created = []
    try:
        fan = ArgonFan()
        created.append(fan)
        power = UsbPower(root)
        created.append(power)
        television = TVControl()
        return PlatformServices(fan, power, television)
    except BaseException:
        # Do not leak worker-owning services when a later constructor fails.
        # Cleanup failures must not obscure the original startup exception.
        for service in reversed(created):
            try:
                service.close()
            except Exception:
                logging.exception('Could not close partially constructed platform service')
        raise
