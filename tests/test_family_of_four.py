"""Demo: a family of four (two adults, two children) whose best flight has three seats
side by side. Offline (stub model). To see it printed:
    pytest -s tests/test_family_of_four.py
To run the same scenario through the real model:
    python -m scripts.demo_family
"""
from app.ai import AIPicker
from app.db import InMemoryRepo
from app.service import RebookingService
from scripts.demo_family import REQUEST_DATE, family_scenario, proof_lines, run
from tests.fakes import make_flight


def stub_model(system: str, user: str) -> str:
    # Stands in for the OpenRouter call. The service still validates this reply
    # and re-checks the pick against every rule.
    return '{"option_id": "OPT-1", "reason": "Both children sit beside Adult 1 on WN2103; Adult 2 follows on WN2106 the same evening."}'


def test_family_of_four_is_split_party_confirm_on_two_different_flights():
    s = run(AIPicker(stub_model, "stub-model (test)"))

    assert s["suggestion_status"] == "split_party_confirm"
    assert s["family_must_agree"] is True and "family must agree" in s["message"]
    first, second = s["suggestion"]["flights"]
    assert first["flight_no"] != second["flight_no"]

    # three passengers including the lead, side by side on the three-seat flight
    assert first["flight_no"] == "WN2103" and first["open_seats_adjacent_max"] == 3
    assert sorted(first["seated_together"]) == ["Adult 1 (M. Rivera)", "Child 1", "Child 2"]
    assert first["includes_lead_passenger"] is True

    # the fourth passenger, an adult, on another valid flight that passed every rule
    assert second["flight_no"] == "WN2106" and second["seated_together"] == ["Adult 2"]
    assert second["departure_datetime"] == "2026-11-18T21:05"
    assert all(c["passed"] for c in s["checklist"])
    assert any(c["rule"].startswith("F4 WN2106") and c["passed"] for c in s["checklist"])

    # never all four on the three-seat flight, never more people than open seats
    for f in s["suggestion"]["flights"]:
        assert f["passengers"] <= f["open_seats_total"] and f["passengers"] <= f["open_seats_adjacent_max"]
    assert s["documentation_lines"] == ["WN2103: STORM WAIVER DEN NOV26 BKG-DEMO4", "WN2106: STORM WAIVER DEN NOV26 BKG-DEMO4"]
    assert s["fare"]["result"] == "no fare difference"
    assert len(proof_lines(s)) == 4  # raises if a child is without an adult or a flight is over-full


def test_family_of_four_with_no_second_valid_flight_gets_no_option_found():
    # Only the three-seat flight passes the rules: the fourth passenger has nowhere to go.
    family, flights = family_scenario()
    flights = [f for f in flights if f.flight_no != "WN2106"]
    s = RebookingService(InMemoryRepo([family], flights)).suggest("BKG-DEMO4", REQUEST_DATE, use_ai=False)
    assert s["suggestion_status"] == "no_option_found"
    assert s["suggestion"] is None and s["message"].startswith("No flight met the rules")


def test_family_of_four_never_put_on_a_flight_with_too_few_seats():
    # The later flight is full: the only way left would be all four on WN2103, which is refused.
    family, flights = family_scenario()
    flights[1] = make_flight("2026-11-18T21:05", flight_no="WN2106", open_seats_total=0, open_seats_adjacent_max=0)
    s = RebookingService(InMemoryRepo([family], flights)).suggest("BKG-DEMO4", REQUEST_DATE, use_ai=False)
    assert s["suggestion_status"] == "no_option_found"
