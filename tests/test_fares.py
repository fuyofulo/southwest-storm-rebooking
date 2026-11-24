"""Sections 4 and 5: fare result and documentation line come from code."""
from decimal import Decimal

from app.fares import documentation_lines, fare_result, split_notes
from app.options import build_options
from app.rules import NON_COVERED, WAIVER
from tests.fakes import make_booking, make_flight, make_party


def one_option(b, party, flights):
    return build_options(b, party, flights).options[0]


def test_waiver_no_fare_difference_even_when_new_fare_is_higher():
    b = make_booking(fare_paid_usd=Decimal("100.00"))
    opt = one_option(b, make_party(), [make_flight(base_fare_usd=Decimal("450.00"))])
    r = fare_result(b, WAIVER, opt)
    assert r.result == "no fare difference" and r.collect_usd == 0
    assert r.fare_paid_usd == Decimal("100.00")


def test_non_covered_collects_the_difference_for_every_seat():
    b = make_booking(party_size=2, waiver_eligible=False, fare_paid_usd=Decimal("300.00"))
    opt = one_option(b, make_party(adults=2), [make_flight(base_fare_usd=Decimal("189.00"))])
    r = fare_result(b, NON_COVERED, opt)
    assert r.new_open_fare_usd == Decimal("378.00")
    assert r.collect_usd == Decimal("78.00")
    assert r.result == "collect $78.00"


def test_non_covered_lower_fare_collects_nothing_and_computes_no_refund():
    b = make_booking(waiver_eligible=False, fare_paid_usd=Decimal("500.00"))
    opt = one_option(b, make_party(), [make_flight(base_fare_usd=Decimal("150.00"))])
    r = fare_result(b, NON_COVERED, opt)
    assert r.collect_usd == 0 and r.result == "no fare difference to collect"
    assert "not calculated" in r.detail


def test_loyalty_tier_does_not_change_the_fare():
    flights = [make_flight(base_fare_usd=Decimal("250.00"))]
    results = {
        tier: fare_result(b, NON_COVERED, one_option(b, make_party(), flights)).collect_usd
        for tier in ("None", "A-List", "A-List Preferred")
        for b in [make_booking(waiver_eligible=False, loyalty_tier=tier)]
    }
    assert len(set(results.values())) == 1


def test_waiver_documentation_line_on_every_flight_of_a_split():
    b = make_booking(booking_id="BKG-42", party_size=4)
    party = make_party(adults=2, children=2)
    flights = [
        make_flight("2026-11-18T08:00", open_seats_total=2, open_seats_adjacent_max=2),
        make_flight("2026-11-18T09:00", open_seats_total=2, open_seats_adjacent_max=2),
    ]
    opt = one_option(b, party, flights)
    lines = documentation_lines(b, WAIVER, opt)
    assert len(lines) == 2
    assert all(line.endswith("STORM WAIVER DEN NOV26 BKG-42") for line in lines)
    notes = split_notes(b, opt)
    assert flights[1].flight_no in notes[0] and flights[0].flight_no in notes[1]


def test_no_documentation_line_on_non_covered():
    b = make_booking(waiver_eligible=False)
    opt = one_option(b, make_party(), [make_flight()])
    assert documentation_lines(b, NON_COVERED, opt) == []
