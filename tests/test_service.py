"""The full response for each path, the waiting list, and the agent's confirmation."""
from datetime import date, datetime
from decimal import Decimal

import pytest

from app.db import AlreadyConfirmed, InMemoryRepo
from app.service import RebookingService, SuggestionChanged
from tests.fakes import make_booking, make_flight

REQ = date(2026, 11, 18)
KEYS = {
    "booking_id", "lead_passenger_name", "party_size", "origin_airport", "destination_airport",
    "earliest_acceptable_departure", "cancellation_time", "waiver_eligible", "path", "suggestion_status",
    "message", "family_must_agree", "agent_checks", "party", "suggestion", "fare", "documentation_lines",
    "split_notes", "checklist", "ai", "agent_context", "confirmation",
}
FLIGHT_KEYS = {"flight_no", "departure_datetime", "open_seats_total", "open_seats_adjacent_max", "seated_together", "flight_status"}


def svc(bookings, flights):
    return RebookingService(InMemoryRepo(bookings, flights), picker=None)


def test_waiver_booking_gets_full_response():
    b = make_booking(booking_id="BKG-1", party_size=2)
    s = svc([b], [make_flight()]).suggest("BKG-1", REQ, use_ai=False)
    assert KEYS <= s.keys()
    assert FLIGHT_KEYS <= s["suggestion"]["flights"][0].keys()
    assert s["path"] == "waiver" and s["suggestion_status"] == "ready_to_confirm" and s["waiver_eligible"] is True
    assert s["fare"]["result"] == "no fare difference"
    assert s["documentation_lines"] == [f"{s['suggestion']['flights'][0]['flight_no']}: STORM WAIVER DEN NOV26 BKG-1"]
    assert s["family_must_agree"] is False and s["confirmation"] is None
    assert all(c["passed"] for c in s["checklist"])
    assert {c["rule"][:2] for c in s["checklist"]} >= {"R1", "R2", "R3", "R4", "F1", "F2", "F3", "F4", "F5", "F6", "P1", "P2", "P3"}


def test_non_covered_booking_gets_a_suggestion_and_a_collect_amount():
    b = make_booking(booking_id="BKG-1", waiver_eligible=False, fare_paid_usd=Decimal("100.00"))
    s = svc([b], [make_flight(base_fare_usd=Decimal("180.00"))]).suggest("BKG-1", REQ, use_ai=False)
    assert s["path"] == "non_covered" and s["suggestion_status"] == "ready_to_confirm" and s["waiver_eligible"] is False
    assert s["fare"]["result"] == "collect $80.00"
    assert s["documentation_lines"] == []


def test_revenue_management_is_no_option_found_with_a_reason():
    b = make_booking(booking_id="BKG-1")
    s = svc([b], [make_flight()]).suggest("BKG-1", date(2026, 11, 24), use_ai=False)
    assert s["path"] == "revenue_management" and s["suggestion_status"] == "no_option_found"
    assert s["suggestion"] is None and s["fare"] is None
    assert "Revenue Management" in s["message"] and "R1" in s["message"]


def test_no_valid_flight_is_no_option_found_and_says_why():
    b = make_booking(booking_id="BKG-1")
    s = svc([b], [make_flight(flight_status="cancelled")]).suggest("BKG-1", REQ, use_ai=False)
    assert s["suggestion_status"] == "no_option_found" and s["suggestion"] is None
    assert s["message"].startswith("No flight met the rules") and "cancelled" in s["message"]


def test_unknown_booking_returns_none():
    assert svc([], []).suggest("NOPE", REQ) is None


def test_suggest_all_covers_every_booking():
    bookings = [make_booking(booking_id=f"BKG-{i}") for i in range(3)]
    out = svc(bookings, [make_flight()]).suggest_all(REQ, use_ai=False)
    assert [s["booking_id"] for s in out] == ["BKG-0", "BKG-1", "BKG-2"]


def three_bookings():
    return [
        make_booking(booking_id="BKG-OLD", cancellation_time=datetime(2026, 11, 16, 1, 0)),
        make_booking(booking_id="BKG-NEW", cancellation_time=datetime(2026, 11, 16, 9, 0)),
        make_booking(booking_id="BKG-MID", cancellation_time=datetime(2026, 11, 16, 5, 0)),
    ]


def test_waiting_list_is_newest_cancellation_first():
    out = svc(three_bookings(), [make_flight()]).waiting(REQ, use_ai=False)
    assert [s["booking_id"] for s in out] == ["BKG-NEW", "BKG-MID", "BKG-OLD"]


def test_confirm_records_who_when_and_which_suggestion_and_leaves_the_waiting_list():
    service = svc(three_bookings(), [make_flight(flight_no="WN5001")])
    record = service.confirm("BKG-MID", "Rosalind Mkhize", REQ, option_id="OPT-1")
    assert record["confirmed_by"] == "Rosalind Mkhize" and record["confirmed_at"]
    assert record["suggestion_status"] == "ready_to_confirm" and record["option_id"] == "OPT-1"
    assert record["flight_nos"] == ["WN5001"] and record["suggestion"]["booking_id"] == "BKG-MID"
    assert [s["booking_id"] for s in service.waiting(REQ, use_ai=False)] == ["BKG-NEW", "BKG-OLD"]
    assert service.suggest("BKG-MID", REQ, use_ai=False)["confirmation"]["confirmed_by"] == "Rosalind Mkhize"


def test_confirm_twice_is_refused():
    service = svc(three_bookings(), [make_flight()])
    service.confirm("BKG-NEW", "R. Mkhize", REQ)
    with pytest.raises(AlreadyConfirmed):
        service.confirm("BKG-NEW", "R. Mkhize", REQ)


def test_confirm_is_refused_when_the_suggestion_has_changed():
    service = svc(three_bookings(), [make_flight()])
    with pytest.raises(SuggestionChanged):
        service.confirm("BKG-NEW", "R. Mkhize", REQ, option_id="OPT-3")


def test_no_option_found_booking_can_be_confirmed_too():
    # The agent decides on every row, including one with no option (e.g. handled by hand or escalated).
    b = make_booking(booking_id="BKG-1")
    service = svc([b], [make_flight(flight_status="cancelled")])
    record = service.confirm("BKG-1", "R. Mkhize", REQ)
    assert record["suggestion_status"] == "no_option_found" and record["option_id"] is None and record["flight_nos"] == []
    assert service.waiting(REQ, use_ai=False) == []
