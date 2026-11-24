"""Small fake bookings and flights for unit tests."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal
from itertools import count

from app.models import ADULT, CHILD, LAP_INFANT, Booking, Flight, Party, Passenger

_flight_no = count(9001)


def make_booking(**kw) -> Booking:
    base = Booking(
        booking_id="BKG-TEST",
        party_size=1,
        lead_passenger_name="T. Tester",
        cancelled_flight_no="WN3000",
        origin_airport="DEN",
        destination_airport="PHX",
        scheduled_departure=datetime(2026, 11, 16, 7, 0),
        cancellation_time=datetime(2026, 11, 16, 3, 0),
        fare_class="Wanna Get Away",
        fare_paid_usd=Decimal("200.00"),
        waiver_eligible=True,
        onward_connection_flight_no=None,
        has_checked_bags=False,
        needs_wheelchair_assist=False,
        travels_with_infant=False,
        loyalty_tier="None",
        hotel_voucher_issued=False,
        earliest_acceptable_departure=datetime(2026, 11, 18, 6, 0),
        agent_note=None,
    )
    return replace(base, **kw)


def make_flight(dep: str = "2026-11-18T09:00", **kw) -> Flight:
    departure = datetime.fromisoformat(dep)
    base = Flight(
        flight_no=f"WN{next(_flight_no)}",
        origin_airport="DEN",
        destination_airport="PHX",
        departure_datetime=departure,
        arrival_datetime=departure + timedelta(hours=2),
        aircraft_type="737-800",
        open_seats_total=10,
        open_seats_adjacent_max=4,
        fare_class_open="Wanna Get Away",
        base_fare_usd=Decimal("150.00"),
        flight_status="scheduled",
        weather_risk_flag=False,
    )
    return replace(base, **kw)


def make_party(adults: int = 1, children: int = 0, infants: int = 0) -> Party:
    pax = [Passenger(f"Adult {i}", ADULT) for i in range(1, adults + 1)]
    pax += [Passenger(f"Child {i}", CHILD) for i in range(1, children + 1)]
    pax += [Passenger(f"Lap infant {i}", LAP_INFANT) for i in range(1, infants + 1)]
    return Party(tuple(pax), make_up_known=True, source="test")
