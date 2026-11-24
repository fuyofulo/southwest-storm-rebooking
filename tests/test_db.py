"""Data loading: CSV quirks and the Supabase repo (with a fake client, no network)."""
import logging

from app.config import get_settings
from app.db import SupabaseRepo, load_flights_csv
from app.models import ADULT, CHILD
from app.party import derive_party, party_to_rows
from tests.fakes import make_booking


def test_truncated_flight_row_is_skipped_with_a_warning(caplog):
    with caplog.at_level(logging.WARNING):
        flights = load_flights_csv(get_settings().data_dir)
    assert len(flights) == 153
    assert "WN1154" not in {f.flight_no for f in flights}
    assert "WN1154" in caplog.text


class FakeQuery:
    def __init__(self, rows, calls):
        self.rows, self.calls = rows, calls

    def select(self, _):
        return self

    def eq(self, col, val):
        self.rows = [r for r in self.rows if r[col] == val]
        return self

    def execute(self):
        self.calls.append(1)
        return type("Resp", (), {"data": self.rows})()


class FakeClient:
    """Mimics supabase-py's table().select().eq().execute().data with typed JSON values."""

    def __init__(self, tables):
        self.tables, self.calls = tables, []

    def table(self, name):
        return FakeQuery(list(self.tables[name]), self.calls)


def supabase_rows():
    booking = {
        "booking_id": "BKG-1", "party_size": 4, "lead_passenger_name": "A. B", "cancelled_flight_no": "WN3001",
        "origin_airport": "DEN", "destination_airport": "PHX", "scheduled_departure": "2026-11-16T07:40:00",
        "cancellation_time": "2026-11-16T04:12:00", "fare_class": "Anytime", "fare_paid_usd": 418.6,
        "waiver_eligible": True, "onward_connection_flight_no": None, "has_checked_bags": False,
        "needs_wheelchair_assist": False, "travels_with_infant": False, "loyalty_tier": "None",
        "hotel_voucher_issued": False, "earliest_acceptable_departure": "2026-11-18T12:00:00",
        "agent_note": "Two children in party of 4.",
    }
    flight = {
        "flight_no": "WN1001", "origin_airport": "DEN", "destination_airport": "PHX",
        "departure_datetime": "2026-11-18T13:00:00", "arrival_datetime": "2026-11-18T15:00:00",
        "aircraft_type": "737-800", "open_seats_total": 5, "open_seats_adjacent_max": 3,
        "fare_class_open": "Anytime", "base_fare_usd": 289, "flight_status": "scheduled", "weather_risk_flag": True,
    }
    party = derive_party(make_booking(booking_id="BKG-1", party_size=4, agent_note="Two children in party of 4."))
    return {"bookings": [booking], "flights": [flight], "passengers": party_to_rows("BKG-1", party)}


def test_supabase_repo_reads_typed_rows_and_prefetches_passengers():
    client = FakeClient(supabase_rows())
    repo = SupabaseRepo(client=client)
    [b] = repo.bookings()
    assert str(b.fare_paid_usd) == "418.60" and b.waiver_eligible is True
    [f] = repo.flights()
    assert f.open_seats_adjacent_max == 3 and str(f.base_fare_usd) == "289.00" and f.weather_risk_flag
    calls_before = len(client.calls)
    party = repo.party(b)
    assert len(client.calls) == calls_before  # served from the prefetched rows
    assert party.make_up_known and party.count(ADULT) == 2 and party.count(CHILD) == 2


def test_supabase_repo_rederives_party_when_rows_are_missing(caplog):
    tables = supabase_rows()
    tables["passengers"] = []
    repo = SupabaseRepo(client=FakeClient(tables))
    [b] = repo.bookings()
    with caplog.at_level(logging.WARNING):
        party = repo.party(b)
    assert party.count(CHILD) == 2 and "re-deriving" in caplog.text
