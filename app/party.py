"""Who is in the party: adults, children, lap infants.

The data has no per-passenger field. A party's make-up counts as *stated* only when:
  - the agent note gives a child count ("Two children in party of 4"); a flagged
    infant (travels_with_infant) counts as one more child, or
  - the note says "Lap infant" (one lap infant, the rest adults), or
  - there is no child, infant or family hint at all (everyone is an adult).
Any other hint ("Family of 4", or the infant flag with no count) means the make-up
is unknown. An unknown party can still be split, but the agent must confirm that every
group without the lead passenger is adults only (see app/options.py).

Every person in party_size needs a seat, lap infants included.
"""
from __future__ import annotations

import re

from .models import ADULT, CHILD, LAP_INFANT, UNKNOWN, Booking, Party, Passenger

_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}
_CHILD_COUNT = re.compile(r"\b(\d+|one|two|three|four|five|six)\s+(?:child|children|kids?)\b", re.I)
_PARTY_OF = re.compile(r"\b(?:party|family|group) of (\d+)\b", re.I)
_LAP_INFANT = re.compile(r"\blap infant\b", re.I)
_HINT = re.compile(r"\b(child|children|kid|kids|family|infant|baby|minor|son|daughter|teen)\b", re.I)


def _number(word: str) -> int:
    return int(word) if word.isdigit() else _NUMBERS[word.lower()]


def _unknown(b: Booking, why: str) -> Party:
    pax = tuple(
        Passenger(f"Passenger 1 ({b.lead_passenger_name})" if i == 1 else f"Passenger {i}", UNKNOWN)
        for i in range(1, b.party_size + 1)
    )
    return Party(pax, make_up_known=False, source=f"make-up unknown: {why}")


def derive_party(b: Booking) -> Party:
    note = b.agent_note or ""

    stated = _PARTY_OF.search(note)
    if stated and int(stated.group(1)) != b.party_size:
        return _unknown(b, f"note says '{stated.group(0)}' but party_size is {b.party_size}")

    count = _CHILD_COUNT.search(note)
    if count:
        children = _number(count.group(1))
        infants = 1 if b.travels_with_infant else 0
        source = f"agent note: '{count.group(0)}'" + (" + travels_with_infant" if infants else "")
    elif _LAP_INFANT.search(note):
        children, infants = 0, 1
        source = "agent note: 'Lap infant'"
    elif b.travels_with_infant:
        return _unknown(b, "travels_with_infant is true but the note gives no child count")
    elif _HINT.search(note):
        return _unknown(b, f"note '{note}' mentions family/children without a count")
    else:
        children, infants = 0, 0
        source = "no child, infant or family hint: all adults"

    adults = b.party_size - children - infants
    if adults < 1:
        return _unknown(b, f"stated make-up ({children} children, {infants} infants) leaves no adult")

    pax = [Passenger(f"Adult 1 ({b.lead_passenger_name})", ADULT)]
    pax += [Passenger(f"Adult {i}", ADULT) for i in range(2, adults + 1)]
    pax += [Passenger(f"Child {i}", CHILD) for i in range(1, children + 1)]
    pax += [Passenger(f"Lap infant {i}", LAP_INFANT) for i in range(1, infants + 1)]
    return Party(tuple(pax), make_up_known=True, source=source)


def party_from_rows(rows: list[dict]) -> Party:
    """Rebuild a Party from `passengers` table rows."""
    rows = sorted(rows, key=lambda r: int(r["seq"]))
    pax = tuple(Passenger(r["label"], r["passenger_type"]) for r in rows)
    known = all(p.type != UNKNOWN for p in pax)
    return Party(pax, make_up_known=known, source=rows[0]["source"] if rows else "no passenger rows")


def party_to_rows(booking_id: str, party: Party) -> list[dict]:
    return [
        {"booking_id": booking_id, "seq": i, "label": p.label, "passenger_type": p.type, "source": party.source}
        for i, p in enumerate(party.passengers, start=1)
    ]
