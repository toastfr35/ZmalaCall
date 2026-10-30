"""Simple TV driver contract; UI, retries and restoration live in TVControl.

Methods run on the controller worker and must bound every I/O wait. Getters
report observations, never inferred command success. Setters return command
acceptance, not proof of a visible change. Unsupported methods raise
NotImplementedError and are absent from get_capabilities().
"""
from abc import ABC, abstractmethod


# @llr LLR-TERM-TV-033
class TVDriver(ABC):
    def __init__(self, config: dict):
        """Store private configuration; construction must perform no I/O."""
        self.config = dict(config)

    @abstractmethod
    def get_model(self) -> str | None:
        """Return the configured/discovered model, or None if unknown."""

    @abstractmethod
    def get_capabilities(self) -> set[str]:
        """Return supported optional method names; this does not qualify a TV."""

    def get_power_status(self) -> bool | None:
        """True: on; False: standby; None: unknown or transitioning."""
        raise NotImplementedError

    def set_power_on(self) -> bool:
        """Request on without blindly toggling; True means already on or sent."""
        raise NotImplementedError

    def set_power_off(self) -> bool:
        """Request standby without blindly toggling; True means off or sent."""
        raise NotImplementedError

    def get_current_input(self) -> str | None:
        """Return a restorable driver-specific identifier, or None if unknown."""
        raise NotImplementedError

    def set_current_input(self, input_id: str) -> bool:
        """Select a specific input; True means already selected or sent."""
        raise NotImplementedError
