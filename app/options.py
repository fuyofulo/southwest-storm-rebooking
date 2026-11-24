"""Section 3: build the list of valid options the AI may choose from.

1. Together: one valid flight whose adjacent block fits the whole party. Earliest first.
2. Safe split, only if no together option exists and the party's make-up is stated:
   the fewest flights, every child/infant in a flight's adjacent block with at least
   one adult, and only adults in the other (non-adjacent) seats.
3. Otherwise no options, with a reason, and the booking is flagged for the agent.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from .models import Booking, Flight, Option, Party, Passenger, Segment
from .rules import fits_together, valid_flights, why_no_flight

MAX_OPTIONS = 5


@dataclass(frozen=True)
class OptionSet:
    options: tuple[Option, ...]
    together_available: bool
    min_flights: int | None  # fewest flights any option needs
    reason: str | None = None  # why there are no options


def build_options(b: Booking, party: Party, flights: list[Flight], limit: int = MAX_OPTIONS) -> OptionSet:
    valid = valid_flights(b, flights)
    if not valid:
        return OptionSet((), False, None, f"No suggestion: {why_no_flight(b, flights)}")

    together = [f for f in valid if fits_together(f, party.size)]
    if together:
        options = tuple(
            Option(f"OPT-{i}", "together", (Segment(f, party.passengers),)) for i, f in enumerate(together[:limit], 1)
        )
        return OptionSet(options, True, 1)

    if not party.make_up_known:
        return OptionSet(
            (), False, None,
            f"No suggestion, flagged for agent: no valid flight has {party.size} adjacent open seats, and the "
            f"party's make-up is not stated ({party.source}), so a split can't be checked against the child rule. "
            "Confirm who in the party is a child before splitting.",
        )

    plans = find_splits(party, valid, limit)
    if not plans:
        seats = sum(f.open_seats_total for f in valid)
        if seats < party.size:
            why = f"only {seats} open seats across all {len(valid)} valid flights for a party of {party.size}"
        else:
            why = "every way to split the party would leave a child or infant without an adult (§3.3)"
        return OptionSet((), False, None, f"No suggestion, flagged for agent: {why}.")

    options = tuple(Option(f"OPT-{i}", "split", segs) for i, segs in enumerate(plans, 1))
    return OptionSet(options, False, len(plans[0]))


def _compositions(total: int, parts: int):
    """All ways to write `total` as an ordered sum of `parts` non-negative integers."""
    if parts == 1:
        yield (total,)
        return
    for first in range(total + 1):
        for rest in _compositions(total - first, parts - 1):
            yield (first, *rest)


def _seat(flights: tuple[Flight, ...], adults: list[Passenger], minors: list[Passenger]) -> tuple[Segment, ...] | None:
    """Best safe seating of the party on exactly these flights (each used), or None."""
    best = None
    for ms in _compositions(len(minors), len(flights)):
        for ads in _compositions(len(adults), len(flights)):
            apart = 0
            for f, m, a in zip(flights, ms, ads):
                n = m + a
                if n == 0 or n > f.open_seats_total:
                    break
                # minors sit in the adjacent block with at least one adult
                if m and (a == 0 or m + 1 > f.open_seats_adjacent_max):
                    break
                apart += n - min(n, f.open_seats_adjacent_max)
            else:
                # fewest people seated apart, then more people on the earlier flight
                key = (apart, tuple(-(m + a) for m, a in zip(ms, ads)))
                if best is None or key < best[0]:
                    best = (key, ms, ads)
    if best is None:
        return None

    _, ms, ads = best
    segments, mi, ai = [], 0, 0
    for f, m, a in zip(flights, ms, ads):
        seg_minors, seg_adults = minors[mi : mi + m], adults[ai : ai + a]
        mi, ai = mi + m, ai + a
        room = f.open_seats_adjacent_max - m  # block seats left for adults
        segments.append(Segment(f, tuple(seg_adults[:room]) + tuple(seg_minors), tuple(seg_adults[room:])))
    return tuple(segments)


def find_splits(party: Party, valid: list[Flight], limit: int = MAX_OPTIONS) -> list[tuple[Segment, ...]]:
    """Safe splits on the fewest flights, best first (earliest the whole party has left)."""
    adults = [p for p in party.passengers if p.is_adult]
    minors = [p for p in party.passengers if p.is_minor]
    if sum(f.open_seats_total for f in valid) < party.size:
        return []
    for k in range(1, min(party.size, len(valid)) + 1):
        plans = [plan for combo in combinations(valid, k) if (plan := _seat(combo, adults, minors))]
        if plans:
            plans.sort(
                key=lambda segs: (
                    max(s.flight.departure_datetime for s in segs),
                    sum(len(s.apart) for s in segs),
                    [s.flight.departure_datetime for s in segs],
                )
            )
            return plans[:limit]
    return []
