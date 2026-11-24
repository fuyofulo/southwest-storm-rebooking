"""Section 2 valid-flight filter F1-F6."""
from datetime import datetime

from app.rules import (
    check_f1_route,
    check_f2_status,
    check_f3_window,
    check_f4_not_early,
    check_f5_seats,
    check_f6_connection,
    valid_flights,
    why_no_flight,
)
from tests.fakes import make_booking, make_flight


def test_f1_rejects_other_route():
    b = make_booking()
    assert check_f1_route(b, make_flight()).passed
    assert not check_f1_route(b, make_flight(destination_airport="TUS")).passed
    assert not check_f1_route(b, make_flight(origin_airport="PHX", destination_airport="DEN")).passed


def test_f2_scheduled_and_delayed_ok_cancelled_never():
    assert check_f2_status(make_flight(flight_status="scheduled")).passed
    assert check_f2_status(make_flight(flight_status="delayed")).passed
    assert not check_f2_status(make_flight(flight_status="cancelled")).passed


def test_f3_window_is_18_to_23_nov_inclusive():
    assert check_f3_window(make_flight("2026-11-18T00:05")).passed
    assert check_f3_window(make_flight("2026-11-23T23:30")).passed
    assert not check_f3_window(make_flight("2026-11-17T23:55")).passed
    assert not check_f3_window(make_flight("2026-11-24T06:00")).passed


def test_f4_never_earlier_than_earliest_acceptable_departure():
    b = make_booking(earliest_acceptable_departure=datetime(2026, 11, 18, 12, 0))
    assert check_f4_not_early(b, make_flight("2026-11-18T12:00")).passed  # at = ok
    assert check_f4_not_early(b, make_flight("2026-11-18T15:00")).passed
    assert not check_f4_not_early(b, make_flight("2026-11-18T11:59", open_seats_total=50)).passed


def test_f5_needs_a_real_seat_per_person_and_an_adjacent_block_for_the_together_group():
    f = make_flight(open_seats_total=4, open_seats_adjacent_max=3)
    assert check_f5_seats(f, seated=4, together=3).passed
    assert not check_f5_seats(f, seated=5, together=3).passed  # short a seat
    assert not check_f5_seats(f, seated=4, together=4).passed  # block too small


def test_f6_direct_flights_have_no_connection_to_make():
    assert check_f6_connection(make_flight()).passed


def test_fare_class_open_does_not_need_to_match():
    b = make_booking(fare_class="Business Select")
    f = make_flight(fare_class_open="Wanna Get Away")
    assert valid_flights(b, [f]) == [f]


def test_valid_flights_applies_all_rules_and_sorts_by_departure():
    b = make_booking(earliest_acceptable_departure=datetime(2026, 11, 18, 10, 0))
    late = make_flight("2026-11-19T08:00")
    early = make_flight("2026-11-18T10:30")
    rejected = [
        make_flight("2026-11-18T09:00"),  # before earliest acceptable
        make_flight("2026-11-18T11:00", flight_status="cancelled"),
        make_flight("2026-11-24T08:00"),  # outside window
        make_flight("2026-11-18T12:00", destination_airport="LAS"),
        make_flight("2026-11-18T13:00", open_seats_total=0, open_seats_adjacent_max=0),
    ]
    assert valid_flights(b, [late, *rejected, early]) == [early, late]


def test_why_no_flight_explains_rejections():
    b = make_booking()
    msg = why_no_flight(b, [make_flight(flight_status="cancelled"), make_flight("2026-11-24T08:00")])
    assert "1 cancelled" in msg and "1 outside 18-23 Nov" in msg
