"""Demo: a family of four (two adults, two children) where the only valid flight has
three seats together.

Run it with output shown:
    pytest -s tests/test_family_of_four.py
"""
from datetime import date, datetime

from app.ai import AIPicker
from app.db import InMemoryRepo
from app.render import format_suggestion
from app.service import RebookingService
from tests.fakes import make_booking, make_flight

REQ = date(2026, 11, 18)


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


def stub_model(system: str, user: str) -> str:
    # Stands in for the OpenRouter call so the demo runs offline. The service
    # still validates this reply and re-checks the pick against every rule.
    return '{"option_id": "OPT-1", "reason": "Only valid flight tonight; both children sit beside Adult 1, Adult 2 sits elsewhere on the same plane."}'


def test_family_of_four_with_three_seats_together():
    family, flights = family_scenario()
    service = RebookingService(InMemoryRepo([family], flights), AIPicker(stub_model, "stub-model (test)"))

    s = service.suggest("BKG-DEMO4", REQ)

    print("\n" + "=" * 100)
    print("FAMILY OF FOUR (2 adults, 2 children). Only valid flight: WN2103 with 5 open seats, 3 side by side.")
    print("=" * 100)
    print(format_suggestion(s))

    # What the service suggests
    assert s["status"] == "suggested"
    assert s["suggestion"]["kind"] == "split"
    assert s["family_must_agree"] is True
    assert "family's agreement" in s["message"]
    [flight] = s["suggestion"]["flights"]
    assert flight["flight_no"] == "WN2103"
    assert sorted(flight["seated_together"]) == ["Adult 1 (M. Rivera)", "Child 1", "Child 2"]
    assert flight["seated_apart"] == ["Adult 2"]
    assert s["documentation_lines"] == ["WN2103: STORM WAIVER DEN NOV26 BKG-DEMO4"]
    assert s["fare"]["result"] == "no fare difference"
    assert all(c["passed"] for c in s["checklist"])

    # Proof that no child is left without an adult
    print("\nProof, no child without an adult:")
    for f in s["suggestion"]["flights"]:
        adults_beside = [p for p in f["seated_together"] if p.startswith("Adult")]
        for child in [p for p in f["seated_together"] + f["seated_apart"] if p.startswith(("Child", "Lap infant"))]:
            assert child in f["seated_together"], f"{child} is seated apart"
            assert adults_beside, f"{child} has no adult beside them"
            print(f"  {child}: on {f['flight_no']}, in the block of {len(f['seated_together'])} with {', '.join(adults_beside)}")
        for p in f["seated_apart"]:
            assert p.startswith("Adult"), f"{p} seated apart is not an adult"
            print(f"  {p}: seated apart on {f['flight_no']} (adults only)")
    print("=" * 100)


def test_family_of_four_if_the_flight_had_only_three_seats_in_total():
    # Same family, but the only valid flight has exactly 3 open seats: no safe way to fly all four.
    family, flights = family_scenario()
    flights[0] = make_flight("2026-11-18T18:40", flight_no="WN2103", open_seats_total=3, open_seats_adjacent_max=3)
    s = RebookingService(InMemoryRepo([family], flights)).suggest("BKG-DEMO4", REQ, use_ai=False)
    assert s["status"] == "no_suggestion" and s["flagged_for_agent"]
    assert s["suggestion"] is None
