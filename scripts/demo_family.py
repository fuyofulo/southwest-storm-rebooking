"""Demo: a family of four (two adults, two children) where the only valid flight has
three seats together. Runs through the real model when OPENROUTER_API_KEY is set.

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
    only_valid = make_flight("2026-11-18T18:40", flight_no="WN2103", open_seats_total=5, open_seats_adjacent_max=3)
    decoys = [
        make_flight("2026-11-18T09:00", flight_no="WN2101", open_seats_adjacent_max=4),  # before earliest acceptable departure
        make_flight("2026-11-18T15:00", flight_no="WN2102", open_seats_adjacent_max=4, flight_status="cancelled"),
        make_flight("2026-11-18T19:00", flight_no="WN2104", open_seats_adjacent_max=4, destination_airport="LAS"),
        make_flight("2026-11-24T08:00", flight_no="WN2105", open_seats_adjacent_max=4),  # after the waiver window
    ]
    return family, [only_valid, *decoys]


def proof_lines(s: dict) -> list[str]:
    """Explain, child by child, which adult they sit with. Raises if any child is left without one."""
    lines = []
    for f in s["suggestion"]["flights"]:
        adults_beside = [p for p in f["seated_together"] if p.startswith("Adult")]
        for child in [p for p in f["seated_together"] + f["seated_apart"] if p.startswith(MINORS)]:
            if child not in f["seated_together"]:
                raise AssertionError(f"{child} is seated apart")
            if not adults_beside:
                raise AssertionError(f"{child} has no adult beside them")
            lines.append(f"  {child}: on {f['flight_no']}, in the block of {len(f['seated_together'])} with {', '.join(adults_beside)}")
        for p in f["seated_apart"]:
            if not p.startswith("Adult"):
                raise AssertionError(f"{p} seated apart is not an adult")
            lines.append(f"  {p}: seated apart on {f['flight_no']} (adults only)")
    return lines


def run(picker: AIPicker | None) -> dict:
    family, flights = family_scenario()
    s = RebookingService(InMemoryRepo([family], flights), picker).suggest("BKG-DEMO4", REQUEST_DATE)
    print("=" * 100)
    print("FAMILY OF FOUR (2 adults, 2 children). Only valid flight: WN2103 with 5 open seats, 3 side by side.")
    print("Decoys rejected by the filter: WN2101 too early, WN2102 cancelled, WN2104 wrong route, WN2105 outside window.")
    print("=" * 100)
    print(format_suggestion(s))
    print("\nProof, no child without an adult:")
    print("\n".join(proof_lines(s)))
    print("=" * 100)
    return s


def main() -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    s = run(make_picker(get_settings()))
    ok = s["status"] == "suggested" and all(c["passed"] for c in s["checklist"])
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
