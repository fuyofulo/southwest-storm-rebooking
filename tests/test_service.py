"""The full response for each path."""
from datetime import date
from decimal import Decimal

from app.db import InMemoryRepo
from app.service import RebookingService
from tests.fakes import make_booking, make_flight

REQ = date(2026, 11, 18)
KEYS = {
    "booking_id", "route", "path", "status", "message", "flagged_for_agent", "family_must_agree",
    "party", "suggestion", "fare", "documentation_lines", "split_notes", "checklist", "ai", "agent_context",
}


def svc(bookings, flights):
    return RebookingService(InMemoryRepo(bookings, flights), picker=None)


def test_waiver_booking_gets_full_response():
    b = make_booking(booking_id="BKG-1", party_size=2)
    s = svc([b], [make_flight()]).suggest("BKG-1", REQ, use_ai=False)
    assert KEYS <= s.keys()
    assert s["path"] == "waiver" and s["status"] == "suggested"
    assert s["fare"]["result"] == "no fare difference"
    assert s["documentation_lines"] == [f"{s['suggestion']['flights'][0]['flight_no']}: STORM WAIVER DEN NOV26 BKG-1"]
    assert s["family_must_agree"] is False
    assert all(c["passed"] for c in s["checklist"])
    assert {c["rule"][:2] for c in s["checklist"]} >= {"R1", "R2", "R3", "R4", "F1", "F2", "F3", "F4", "F5", "F6", "P1", "P2", "P3"}


def test_non_covered_booking_gets_a_suggestion_and_a_collect_amount():
    b = make_booking(booking_id="BKG-1", waiver_eligible=False, fare_paid_usd=Decimal("100.00"))
    s = svc([b], [make_flight(base_fare_usd=Decimal("180.00"))]).suggest("BKG-1", REQ, use_ai=False)
    assert s["path"] == "non_covered" and s["status"] == "suggested"
    assert s["fare"]["result"] == "collect $80.00"
    assert s["documentation_lines"] == []


def test_revenue_management_gets_no_suggestion_only_a_reason():
    b = make_booking(booking_id="BKG-1")
    s = svc([b], [make_flight()]).suggest("BKG-1", date(2026, 11, 24), use_ai=False)
    assert s["path"] == "revenue_management" and s["status"] == "revenue_management"
    assert s["suggestion"] is None and s["fare"] is None
    assert "R1" in s["message"]


def test_no_valid_flight_says_why_and_flags():
    b = make_booking(booking_id="BKG-1")
    s = svc([b], [make_flight(flight_status="cancelled")]).suggest("BKG-1", REQ, use_ai=False)
    assert s["status"] == "no_suggestion" and s["flagged_for_agent"]
    assert "cancelled" in s["message"]


def test_unknown_booking_returns_none():
    assert svc([], []).suggest("NOPE", REQ) is None


def test_suggest_all_covers_every_booking():
    bookings = [make_booking(booking_id=f"BKG-{i}") for i in range(3)]
    out = svc(bookings, [make_flight()]).suggest_all(REQ, use_ai=False)
    assert [s["booking_id"] for s in out] == ["BKG-0", "BKG-1", "BKG-2"]
