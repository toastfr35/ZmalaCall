"""Time-based carousel motion, independent of Tk and the call engine."""
from dataclasses import dataclass
import math

# @llr LLR-TERM-UI-015
CONTACT_STATUS_HEIGHT = 56


@dataclass(frozen=True)
class CarouselLayout:
    slots: int
    portrait_size: float
    spacing: float

    def offset(self, slot):
        """Interpolate unequal centre distances for equal gaps between edges.

        The first neighbour needs room for the selected portrait; subsequent
        neighbours are smaller and therefore sit closer to one another.
        """
        distance = abs(slot)
        offset = self.spacing*min(1, distance) + (self.spacing-self.portrait_size*.25)*max(0, distance-1)
        return offset if slot >= 0 else -offset

    # @llr LLR-TERM-NAV-003, LLR-TERM-UI-014
    @classmethod
    def fit(cls, width, height, contacts, portraits=3):
        """Fit the chosen layout, using three slots for smaller contact lists."""
        wide = portraits == 5 and contacts >= 5
        spacing = width*(.19 if wide else .29)
        # Neighbours are half the selected portrait size. Their combined
        # half-widths occupy 3/4 of this size; leave room for borders and a gap.
        horizontal_limit = (spacing-32)/.75
        size = min(460, width*.24, height-92-CONTACT_STATUS_HEIGHT, horizontal_limit) if wide else min(
            400 if width >= 1100 else 300, height-92-CONTACT_STATUS_HEIGHT, horizontal_limit)
        slots = 5 if wide else 3
        # Five portraits must also fit on a 720p TV or a narrow window.
        available = width-140-slots*28-(slots-1)*12
        size = max(40, min(size, available/(1+(slots-1)*.5)))
        # Card padding adds 28 px to each width. Reserve the outer 70 px
        # for each arrow and spread the remaining space into equal edge gaps.
        gap = max(12, (width-140-size*(1+(slots-1)*.5)-slots*28)/(slots-1))
        return cls(slots, size, size*.75+28+gap)


def carousel_contacts(contacts, index, slots=3):
    """Centered cyclic selection, without repeating people in sparse lists."""
    radius = slots//2
    result = [None]*slots
    if not contacts:
        return result
    used = set()
    offsets = [0] + [offset for distance in range(1, radius+1) for offset in (distance, -distance)]
    for offset in offsets:
        position = (index+offset) % len(contacts)
        if position not in used:
            result[radius+offset] = contacts[position]
            used.add(position)
    return result


# @llr LLR-TERM-NAV-004
@dataclass
class CarouselMotion:
    contacts: list
    index: int
    direction: int
    started: float
    duration: float = .55
    start_offset: float = 0
    end_offset: float | None = None

    def __post_init__(self):
        if self.end_offset is None:
            self.end_offset = self.direction

    def progress(self, now):
        return max(0.0, min(1.0, (now - self.started) / self.duration))

    def position(self, now):
        progress = self.progress(now)
        eased = progress * progress * (3 - 2 * progress)
        return self.start_offset + (self.end_offset - self.start_offset) * eased

    def retarget(self, direction, now):
        """Count another press without jumping or waiting for earlier animation.

        Keep the displayed position, but move the destination one more slot.
        Selection updates separately and immediately, so green confirms the
        contact reached by every press even before the animation settles.
        """
        self.start_offset = self.position(now)
        self.end_offset += direction
        self.direction = direction
        self.started = now

    def next_frame_delay(self, now):
        """Keep a 60 Hz cadence without accumulating draw/timer overhead.

        Skip missed deadlines rather than scheduling a burst of catch-up
        frames that would starve Tk's idle redraws and input handling.
        """
        elapsed = max(0.0, now - self.started)
        deadline = self.started + (math.floor(elapsed * 60) + 1) / 60
        return max(1, math.ceil((deadline - now) * 1000 - 1e-6))

    def frames(self, now, slots=3):
        position = self.position(now)
        if len(self.contacts) == 2:
            # Two people exchange the center/right slots without duplicate cards.
            phase = position % 2
            exchange = phase if phase <= 1 else 2 - phase
            return [(None, -1.0), (self.contacts[self.index], exchange),
                    (self.contacts[(self.index + 1) % 2], 1 - exchange)]
        radius = slots//2
        first = math.floor(position) - radius
        offsets = range(first, first + slots + 1)
        return [(self.contacts[(self.index + offset) % len(self.contacts)], offset - position)
                for offset in offsets]
