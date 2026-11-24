"""Section 1 routing checks R1-R4."""
from datetime import date, datetime

from app.rules import NON_COVERED, REVENUE_MANAGEMENT, WAIVER, route
from tests.fakes import make_booking

OK_DATE = date(2026, 11, 18)


def test_r1_request_on_23_nov_passes():
    assert route(make_booking(), date(2026, 11, 23)).path == WAIVER


def test_r1_request_after_23_nov_goes_to_revenue_management():
    r = route(make_booking(), date(2026, 11, 24))
    assert r.path == REVENUE_MANAGEMENT
    assert "R1" in r.reason
    assert len(r.checks) == 1  # stops at the first failure


def test_r2_alternate_airport_goes_to_revenue_management():
    r = route(make_booking(), OK_DATE, requested_destination="TUS")
    assert r.path == REVENUE_MANAGEMENT
    assert "R2" in r.reason


def test_r2_same_pair_passes():
    r = route(make_booking(), OK_DATE, requested_origin="DEN", requested_destination="PHX")
    assert r.path == WAIVER


def test_r3_customer_only_accepts_after_window_goes_to_revenue_management():
    b = make_booking(earliest_acceptable_departure=datetime(2026, 11, 24, 6, 0))
    r = route(b, OK_DATE)
    assert r.path == REVENUE_MANAGEMENT
    assert "R3" in r.reason


def test_r3_last_day_of_window_passes():
    b = make_booking(earliest_acceptable_departure=datetime(2026, 11, 23, 20, 0))
    assert route(b, OK_DATE).path == WAIVER


def test_r4_waiver_true_goes_to_waiver_path():
    r = route(make_booking(waiver_eligible=True), OK_DATE)
    assert r.path == WAIVER
    assert r.reason is None


def test_r4_waiver_false_is_not_skipped_it_goes_to_non_covered_path():
    r = route(make_booking(waiver_eligible=False), OK_DATE)
    assert r.path == NON_COVERED
    assert r.reason is None
    assert all(c.passed for c in r.checks)


def test_checks_run_in_order_and_first_failure_decides():
    # Fails R1 and R3; R1 is reported because it runs first.
    b = make_booking(earliest_acceptable_departure=datetime(2026, 11, 25, 6, 0))
    r = route(b, date(2026, 11, 30))
    assert "R1" in r.reason
