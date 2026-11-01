"""Pure TV viewing/restoration policy; no CEC, network, clocks or threads.

None means unobserved power/input. Sending a command never promotes an unknown
state to an observed one. The transport supplies fresh observations and owns its
cancellation tokens; the UI owns the inactivity countdown.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class RestorePlan:
    release_source: bool
    power_off: bool


class ViewingSession:
    def __init__(self):
        self.previous = None
        self.browsing = None
        self.changed = False

    def reset(self):
        self.previous = self.browsing = None
        self.changed = False

    # @llr LLR-TERM-TV-026
    @staticmethod
    def control_allowed(off, power_enabled, source_enabled):
        return source_enabled if off is False else power_enabled

    # @llr LLR-TERM-TV-028
    def begin_wake(self, restore, restoring):
        if restore and self.browsing:
            # Consecutive calls inherit the original baseline, not our HDMI view.
            self.previous, self.browsing = self.browsing, None
            self.changed = True
        elif not restore and restoring and self.browsing:
            # A new identity restarts an idle countdown even between UI ticks.
            self.browsing = dict(self.browsing)
        elif not restore:
            self.browsing = None

    @staticmethod
    def restorable(previous):
        return previous and (previous['off'] is True or previous['source'] is not None)

    # @llr LLR-TERM-TV-028
    def defer(self, now):
        if self.changed and self.restorable(self.previous):
            self.browsing = dict(self.previous, idle_started=now)
        self.previous = None
        self.changed = False

    # @llr LLR-TERM-TV-027, LLR-TERM-TV-028
    def observe_browsing(self, observed):
        if self.browsing:
            source = observed.get('active_source')
            if observed.get('off') is True or (source is not None and source != self.browsing['address']):
                self.browsing = None  # Never undo a manual source/power change.
        return self.browsing

    def capture_browsing(self, previous):
        if self.browsing is None and self.restorable(previous):
            self.browsing = previous

    # @llr LLR-TERM-TV-028
    @staticmethod
    def restore_plan(previous, power_enabled, source_enabled):
        return RestorePlan(source_enabled and previous['source'] != previous['address'],
                           power_enabled and previous['off'] is True)
