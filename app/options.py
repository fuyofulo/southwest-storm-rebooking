"""Section 3: build the list of valid options the AI may choose from.

1. Together: one valid flight whose adjacent block fits the whole party. Earliest first.
2. Split party, only if no together option exists: the party is split into groups, each
   group side by side in the adjacent block of its OWN valid flight (never more people on a
   flight than its open seats, never part of the party seated apart on the same plane).
   - the fewest flights possible;
   - the lead passenger's group is as large as the best flight allows (a party of 4 whose
     best flight has 3 seats together: the lead + 2 on that flight, the 4th on another one);
   - every child/infant is in a group with an adult. When the make-up isn't stated, the
     agent must confirm that every group without the lead passenger is adults only.
3. Otherwise no options, with a reason.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import permutations

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
        return OptionSet((), False, None, f"No flight met the rules. {why_no_flight(b, flights)}")

    together = [f for f in valid if fits_together(f, party.size)]
    if together:
        options = tuple(
            Option(f"OPT-{i}", "together", (Segment(f, party.passengers),)) for i, f in enumerate(together[:limit], 1)
        )
        return OptionSet(options, True, 1)

    plans = find_splits(party, valid, limit)
    if not plans:
        seats = sum(f.open_seats_total for f in valid)
        if seats < party.size:
            why = f"only {seats} open seats across all {len(valid)} valid flights for a party of {party.size}"
        elif party.size == 1:
            why = "no valid flight has an open seat"
        else:
            why = (
                f"no valid flight seats all {party.size} side by side, and the {len(valid)} valid flight(s) can't take "
                "the party in side-by-side groups on different flights"
                + (" with every child next to an adult" if any(p.is_minor for p in party.passengers) else "")
            )
        return OptionSet((), False, None, f"No flight met the rules: {why}.")

    options = tuple(Option(f"OPT-{i}", "split", segs, _agent_checks(party, segs)) for i, segs in enumerate(plans, 1))
    return OptionSet(options, False, len(plans[0]))


def _agent_checks(party: Party, segments: tuple[Segment, ...]) -> tuple[str, ...]:
    if party.make_up_known:
        return ()
    return tuple(
        f"Make-up not stated: confirm {', '.join(p.label for p in seg.together)} on {seg.flight.flight_no} "
        f"{'is an adult' if len(seg.together) == 1 else 'are all adults'} (no child may fly without an adult)."
        for seg in segments[1:]
    )


def _group_sizes(n: int, k: int):
    """Sizes for k groups: the lead's group first and largest (biggest first), the rest non-increasing."""

    def rest(total: int, parts: int, cap: int):
        if parts == 0:
            if total == 0:
                yield ()
            return
        for size in range(min(cap, total - (parts - 1)), 0, -1):
            for tail in rest(total - size, parts - 1, size):
                yield (size, *tail)

    for lead in range(n - (k - 1), 0, -1):
        for tail in rest(n - lead, k - 1, lead):
            yield (lead, *tail)


def _fill(party: Party, sizes: tuple[int, ...]) -> list[tuple[Passenger, ...]] | None:
    """Put people into groups of these sizes, the lead in group 1, every child with an adult. None if impossible."""
    lead, *others = party.passengers
    if not party.make_up_known:  # nothing to place by type; the agent confirms the other groups are adults
        people = list(others)
        groups = [(lead, *people[: sizes[0] - 1])]
        people = people[sizes[0] - 1 :]
        for size in sizes[1:]:
            groups.append(tuple(people[:size]))
            people = people[size:]
        return groups

    adults = [p for p in others if p.is_adult]
    minors = [p for p in others if p.is_minor]
    groups = []
    for i, size in enumerate(sizes):
        group = [lead] if i == 0 else []
        if minors and not group:  # a group with children needs an adult first
            if not adults:
                return None
            group.append(adults.pop(0))
        while len(group) < size and minors and group:
            group.append(minors.pop(0))
        while len(group) < size and adults:
            group.append(adults.pop(0))
        if len(group) < size:  # only children left for a group with no adult
            return None
        groups.append(tuple(group))
    return groups


def find_splits(party: Party, valid: list[Flight], limit: int = MAX_OPTIONS) -> list[tuple[Segment, ...]]:
    """Split plans on the fewest flights, the lead's group as large as possible, best first.

    Best first = the whole party has left soonest, then the party's flights are closest together in time.
    """
    if party.size < 2 or sum(f.open_seats_total for f in valid) < party.size:
        return []
    for k in range(2, min(party.size, len(valid)) + 1):
        plans = []
        for sizes in _group_sizes(party.size, k):
            groups = _fill(party, sizes)
            if groups is None:
                continue
            for flights in permutations(valid, k):
                if all(len(g) <= f.open_seats_adjacent_max for g, f in zip(groups, flights)):
                    plans.append(tuple(Segment(f, g) for f, g in zip(flights, groups)))
        if plans:
            biggest = max(len(p[0].together) for p in plans)
            plans = [p for p in plans if len(p[0].together) == biggest]
            plans.sort(key=_rank)
            unique, seen = [], set()
            for p in plans:
                key = frozenset((s.flight.flight_no, s.together) for s in p)
                if key not in seen:
                    seen.add(key)
                    unique.append(p)
            return unique[:limit]
    return []


def _rank(segs: tuple[Segment, ...]):
    deps = [s.flight.departure_datetime for s in segs]
    return (max(deps), max(deps) - min(deps), deps[0], [s.flight.flight_no for s in segs])
