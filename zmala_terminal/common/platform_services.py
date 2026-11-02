"""Construction boundary for terminal hardware services.

Select desktop substitutes without importing Linux power and television code. Callers own shutdown; this module does not start a second event
loop or hide device lifetime behind global singletons.
"""
from dataclasses import dataclass
from pathlib import Path
import sys
import logging
from typing import Protocol


class FanService(Protocol):
    def update(self, active: bool) -> None: ...
    def close(self) -> None: ...


class PowerService(Protocol):
    enabled: bool
    ready: bool
    power_state: bool | None
    state: str
    ringing: bool
    playback_active: bool
    ringtone_preview_status: str

    def require(self, urgent: bool = False) -> bool: ...
    def refresh(self, engine) -> None: ...
    def update(self, active, battery, ringing=False) -> None: ...
    def set_ringtone(self, file, percent=50) -> None: ...
    def preview_tone(self, file) -> None: ...
    def stop_preview(self) -> None: ...
    def stop_ringing(self) -> None: ...
    def close(self) -> None: ...


class TelevisionService(Protocol):
    power_enabled: bool
    source_enabled: bool

    def handle_button(self, on_visible, preserve_restore=False) -> bool: ...
    def wake(self, restore=True, initial=None, ringing=None) -> None: ...
    def cancel(self, defer=False) -> None: ...
    def pause_for_setup(self) -> None: ...
    def browsing_session(self) -> dict | None: ...
    def restore_browsing(self, session) -> None: ...
    def ready(self, now) -> bool: ...
    def close(self) -> None: ...


@dataclass(frozen=True)
class PlatformServices:
    fan: FanService
    usb_power: PowerService
    television: TelevisionService


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


def create_remote(root, press, release, pointer=None, motion=None, observe=None):
    if sys.platform == 'win32':
        from zmala_terminal.windows.platform_services import DesktopRemote
        return DesktopRemote()
    from zmala_terminal.linux.presenter_input import PresenterInput
    return PresenterInput(root, press, release, pointer, motion, observe)


def create_action_sounds():
    if sys.platform == 'win32':
        from zmala_terminal.windows.platform_services import DesktopSounds
        return DesktopSounds()
    from zmala_terminal.linux.action_sounds import ActionSounds
    return ActionSounds()


def create_pairing_status():
    if sys.platform == 'win32':
        from zmala_terminal.windows.platform_services import DesktopPairing
        return DesktopPairing()
    from zmala_terminal.linux.pairing_status import PairingStatus
    return PairingStatus()


def create_camera_status():
    if sys.platform == 'win32':
        from zmala_terminal.windows.platform_services import DesktopCameraStatus
        return DesktopCameraStatus()
    from zmala_terminal.linux.c20_status import C20Status
    return C20Status()


def create_tv_check_transport(television):
    # Called only after the television capability check; desktop setup skips it.
    if sys.platform == 'win32':
        raise RuntimeError('TV installation checks are not supported on Windows')
    from zmala_terminal.linux.tv_check import CheckTransport
    return CheckTransport(television)
