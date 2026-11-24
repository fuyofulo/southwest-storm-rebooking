"""Demo: a family of four (two adults, two children) whose best flight has only three seats
side by side. Runs through the real model when OPENROUTER_API_KEY is set.

    python -m scripts.demo_family
"""
from __future__ import annotations

import logging
from datetime import date, datetime

from app.ai import AIPicker, make_picker
from app.config import get_settings
from app.db import InMemoryRepo
from app.render import format_suggestion
from app.service import RebookingService
from tests.fakes import make_booking, make_flight

REQUEST_DATE = date(2026, 11, 18)
MINORS = ("Child", "Lap infant")


def family_scenario():
    family = make_booking(
        booking_id="BKG-DEMO4",
        party_size=4,
        lead_passenger_name="M. Rivera",
        origin_airport="DEN",
        destination_airport="PHX",
        earliest_acceptable_departure=datetime(2026, 11, 18, 12, 0),
        agent_note="Two children in party of 4.",
    )
    three_together = make_flight("2026-11-18T18:40", flight_no="WN2103", open_seats_total=5, open_seats_adjacent_max=3)
    one_more_seat = make_flight("2026-11-18T21:05", flight_no="WN2106", open_seats_total=2, open_seats_adjacent_max=1)
    decoys = [
        make_flight("2026-11-18T09:00", flight_no="WN2101", open_seats_adjacent_max=4),  # before earliest acceptable departure
        make_flight("2026-11-18T15:00", flight_no="WN2102", open_seats_adjacent_max=4, flight_status="cancelled"),
        make_flight("2026-11-18T19:00", flight_no="WN2104", open_seats_adjacent_max=4, destination_airport="LAS"),
        make_flight("2026-11-24T08:00", flight_no="WN2105", open_seats_adjacent_max=4),  # after the waiver window
    ]
    return family, [three_together, one_more_seat, *decoys]


def proof_lines(s: dict) -> list[str]:
    """Explain who flies where. Raises if a child has no adult, a flight is over-full, or the split shares a flight."""
    flights = s["suggestion"]["flights"]
    if len({f["flight_no"] for f in flights}) != len(flights):
        raise AssertionError("two groups on the same flight")
    lines = []
    for f in flights:
        group = f["seated_together"]
        if len(group) > f["open_seats_total"] or len(group) > f["open_seats_adjacent_max"]:
            raise AssertionError(f"{len(group)} placed on {f['flight_no']}, more than its seats")
        adults = [p for p in group if p.startswith("Adult")]
        for child in [p for p in group if p.startswith(MINORS)]:
            if not adults:
                raise AssertionError(f"{child} has no adult beside them")
            lines.append(f"  {child}: on {f['flight_no']}, side by side with {', '.join(adults)}")
        for adult in adults:
            lines.append(f"  {adult}: on {f['flight_no']} departing {f['departure_datetime'].replace('T', ' ')}")
    return lines


def run(picker: AIPicker | None) -> dict:
    family, flights = family_scenario()
    s = RebookingService(InMemoryRepo([family], flights), picker).suggest("BKG-DEMO4", REQUEST_DATE)
    print("=" * 100)
    print("FAMILY OF FOUR (2 adults, 2 children). Best flight WN2103: 5 open seats, only 3 side by side.")
    print("Also valid: WN2106 later the same evening (2 open seats). No flight seats all four side by side.")
    print("Rejected by the filter: WN2101 too early, WN2102 cancelled, WN2104 wrong route, WN2105 outside the window.")
    print("=" * 100)
    print(format_suggestion(s))
    print("\nProof (who flies where; no child without an adult, no flight over its seats):")
    print("\n".join(proof_lines(s)))
    print("=" * 100)
    return s


def main() -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    s = run(make_picker(get_settings()))
    ok = s["suggestion_status"] == "split_party_confirm" and all(c["passed"] for c in s["checklist"])
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
