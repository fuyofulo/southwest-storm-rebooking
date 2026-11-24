"""Plain data types shared by the service.

`from_row` accepts both CSV rows (all strings) and Supabase rows (typed JSON).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

ADULT, CHILD, LAP_INFANT, UNKNOWN = "adult", "child", "lap_infant", "unknown"
MINOR_TYPES = frozenset({CHILD, LAP_INFANT})  # must travel with an adult


def _bool(v) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() == "true"


def _dt(v) -> datetime:
    if isinstance(v, datetime):
        return v
    return datetime.fromisoformat(str(v).strip()).replace(tzinfo=None)


def _money(v) -> Decimal:
    return Decimal(str(v).strip()).quantize(Decimal("0.01"))


def _text(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


@dataclass(frozen=True)
class Booking:
    booking_id: str
    party_size: int
    lead_passenger_name: str
    cancelled_flight_no: str
    origin_airport: str
    destination_airport: str
    scheduled_departure: datetime
    cancellation_time: datetime
    fare_class: str
    fare_paid_usd: Decimal  # total for the whole party
    waiver_eligible: bool
    onward_connection_flight_no: str | None
    has_checked_bags: bool
    needs_wheelchair_assist: bool
    travels_with_infant: bool
    loyalty_tier: str
    hotel_voucher_issued: bool
    earliest_acceptable_departure: datetime
    agent_note: str | None

    @classmethod
    def from_row(cls, r: dict) -> "Booking":
        return cls(
            booking_id=str(r["booking_id"]).strip(),
            party_size=int(r["party_size"]),
            lead_passenger_name=str(r["lead_passenger_name"]).strip(),
            cancelled_flight_no=str(r["cancelled_flight_no"]).strip(),
            origin_airport=str(r["origin_airport"]).strip(),
            destination_airport=str(r["destination_airport"]).strip(),
            scheduled_departure=_dt(r["scheduled_departure"]),
            cancellation_time=_dt(r["cancellation_time"]),
            fare_class=str(r["fare_class"]).strip(),
            fare_paid_usd=_money(r["fare_paid_usd"]),
            waiver_eligible=_bool(r["waiver_eligible"]),
            onward_connection_flight_no=_text(r.get("onward_connection_flight_no")),
            has_checked_bags=_bool(r["has_checked_bags"]),
            needs_wheelchair_assist=_bool(r["needs_wheelchair_assist"]),
            travels_with_infant=_bool(r["travels_with_infant"]),
            loyalty_tier=str(r["loyalty_tier"]).strip(),
            hotel_voucher_issued=_bool(r["hotel_voucher_issued"]),
            earliest_acceptable_departure=_dt(r["earliest_acceptable_departure"]),
            agent_note=_text(r.get("agent_note")),
        )


@dataclass(frozen=True)
class Flight:
    flight_no: str
    origin_airport: str
    destination_airport: str
    departure_datetime: datetime
    arrival_datetime: datetime
    aircraft_type: str
    open_seats_total: int
    open_seats_adjacent_max: int  # largest block of side-by-side open seats
    fare_class_open: str
    base_fare_usd: Decimal  # open fare, per seat
    flight_status: str
    weather_risk_flag: bool

    @classmethod
    def from_row(cls, r: dict) -> "Flight":
        return cls(
            flight_no=str(r["flight_no"]).strip(),
            origin_airport=str(r["origin_airport"]).strip(),
            destination_airport=str(r["destination_airport"]).strip(),
            departure_datetime=_dt(r["departure_datetime"]),
            arrival_datetime=_dt(r["arrival_datetime"]),
            aircraft_type=str(r["aircraft_type"]).strip(),
            open_seats_total=int(r["open_seats_total"]),
            open_seats_adjacent_max=int(r["open_seats_adjacent_max"]),
            fare_class_open=str(r["fare_class_open"]).strip(),
            base_fare_usd=_money(r["base_fare_usd"]),
            flight_status=str(r["flight_status"]).strip().lower(),
            weather_risk_flag=_bool(r["weather_risk_flag"]),
        )


@dataclass(frozen=True)
class Passenger:
    label: str  # e.g. "Adult 1 (D. Whitfield)", "Child 2", "Passenger 3"
    type: str  # adult | child | lap_infant | unknown

    @property
    def is_minor(self) -> bool:
        return self.type in MINOR_TYPES

    @property
    def is_adult(self) -> bool:
        return self.type == ADULT


@dataclass(frozen=True)
class Party:
    passengers: tuple[Passenger, ...]
    make_up_known: bool  # False = we can't tell adults from children
    source: str  # how the make-up was worked out

    @property
    def size(self) -> int:
        return len(self.passengers)

    def count(self, ptype: str) -> int:
        return sum(p.type == ptype for p in self.passengers)


@dataclass(frozen=True)
class Segment:
    """One flight in an option and the group on it. The whole group sits in the flight's adjacent block."""

    flight: Flight
    together: tuple[Passenger, ...]

    @property
    def people(self) -> tuple[Passenger, ...]:
        return self.together


@dataclass(frozen=True)
class Option:
    option_id: str  # "OPT-1" ... ; the only thing the AI may return
    kind: str  # "together" | "split"
    segments: tuple[Segment, ...]  # a split: the lead passenger's group first, each group on its own flight
    agent_checks: tuple[str, ...] = ()  # what the agent must confirm with the customer first

    @property
    def family_must_agree(self) -> bool:
        return self.kind == "split"


@dataclass(frozen=True)
class Check:
    rule: str
    passed: bool
    detail: str
