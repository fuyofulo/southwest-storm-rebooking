"""Deterministic rules from REBOOKING_SPEC.md.

Section 1: routing checks R1-R4 (run before any search).
Section 2: the valid-flight filter F1-F6.
Section 3: the party seating rules, re-checked on whatever option is finally picked.
Every check returns a `Check` so the agent sees a checklist.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time

from .models import Booking, Check, Flight, Option, Party

WINDOW_FIRST_DAY = date(2026, 11, 18)  # §2.1
WINDOW_LAST_DAY = date(2026, 11, 23)  # §2.1
REQUEST_DEADLINE = date(2026, 11, 23)  # §2.5
USABLE_STATUSES = frozenset({"scheduled", "delayed"})  # §2.3

WAIVER, NON_COVERED, REVENUE_MANAGEMENT = "waiver", "non_covered", "revenue_management"


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M")


# ---------------------------------------------------------------- Section 1


@dataclass(frozen=True)
class Routing:
    path: str  # waiver | non_covered | revenue_management
    checks: tuple[Check, ...]
    reason: str | None = None  # why it went to Revenue Management


def check_r1(request_date: date) -> Check:
    ok = request_date <= REQUEST_DEADLINE
    return Check("R1 request on or before 23 Nov 2026 (§2.5)", ok, f"request date {request_date.isoformat()}")


def check_r2(b: Booking, requested_origin: str | None = None, requested_destination: str | None = None) -> Check:
    origin = requested_origin or b.origin_airport
    dest = requested_destination or b.destination_airport
    ok = (origin, dest) == (b.origin_airport, b.destination_airport)
    detail = f"requested {origin}-{dest}, booked {b.origin_airport}-{b.destination_airport}"
    return Check("R2 same origin and destination pair (§2.2)", ok, detail)


def check_r3(b: Booking) -> Check:
    # The customer accepts travel in the window if their earliest acceptable
    # departure is no later than the last day of the window.
    ok = b.earliest_acceptable_departure.date() <= WINDOW_LAST_DAY
    detail = f"earliest acceptable departure {_fmt(b.earliest_acceptable_departure)}"
    return Check("R3 accepts travel departing 18-23 Nov 2026 (§2.1)", ok, detail)


def check_r4(b: Booking) -> Check:
    path = "waiver path (§3)" if b.waiver_eligible else "non-covered path (§4)"
    detail = f"waiver_eligible = {str(b.waiver_eligible).lower()} read as given -> {path}"
    return Check("R4 waiver_eligible read as given (§1.3, §1.4)", True, detail)


def route(
    b: Booking,
    request_date: date,
    requested_origin: str | None = None,
    requested_destination: str | None = None,
) -> Routing:
    """Run R1-R4 in order. The first failure sends the booking to Revenue Management."""
    checks: list[Check] = []
    for check in (check_r1(request_date), check_r2(b, requested_origin, requested_destination), check_r3(b)):
        checks.append(check)
        if not check.passed:
            reason = f"Send to Revenue Management, no suggestion: {check.rule} failed ({check.detail})."
            return Routing(REVENUE_MANAGEMENT, tuple(checks), reason)
    checks.append(check_r4(b))
    return Routing(WAIVER if b.waiver_eligible else NON_COVERED, tuple(checks))


# ---------------------------------------------------------------- Section 2


def check_f1_route(b: Booking, f: Flight) -> Check:
    ok = (f.origin_airport, f.destination_airport) == (b.origin_airport, b.destination_airport)
    return Check(f"F1 {f.flight_no} same origin and destination (§2.2)", ok, f"{f.origin_airport}-{f.destination_airport}")


def check_f2_status(f: Flight) -> Check:
    ok = f.flight_status in USABLE_STATUSES
    return Check(f"F2 {f.flight_no} scheduled or delayed, not cancelled (§2.3)", ok, f"status {f.flight_status}")


def check_f3_window(f: Flight) -> Check:
    ok = WINDOW_FIRST_DAY <= f.departure_datetime.date() <= WINDOW_LAST_DAY
    return Check(f"F3 {f.flight_no} departs 18-23 Nov 2026 (§2.1)", ok, f"departs {_fmt(f.departure_datetime)}")


def check_f4_not_early(b: Booking, f: Flight) -> Check:
    ok = f.departure_datetime >= b.earliest_acceptable_departure
    detail = f"departs {_fmt(f.departure_datetime)}, earliest acceptable {_fmt(b.earliest_acceptable_departure)}"
    return Check(f"F4 {f.flight_no} at or after earliest acceptable departure (§2.4)", ok, detail)


def check_f5_seats(f: Flight, seated: int, together: int) -> Check:
    """Every person needs a seat (lap infants included); the together group needs an adjacent block."""
    ok = seated <= f.open_seats_total and together <= f.open_seats_adjacent_max
    detail = (
        f"{seated} seats needed ({together} side by side); "
        f"{f.open_seats_total} open, largest adjacent block {f.open_seats_adjacent_max}"
    )
    return Check(f"F5 {f.flight_no} enough real open seats", ok, detail)


def check_f6_connection(f: Flight) -> Check:
    return Check(f"F6 {f.flight_no} connection timing", True, "direct flight: no connection to make (direct-only prototype)")


def flight_basics(b: Booking, f: Flight) -> list[Check]:
    """F1-F4: the checks that don't depend on how many people are placed on the flight."""
    return [check_f1_route(b, f), check_f2_status(f), check_f3_window(f), check_f4_not_early(b, f)]


def valid_flights(b: Booking, flights: list[Flight]) -> list[Flight]:
    """Flights passing F1-F4 with at least one open seat, earliest departure first."""
    ok = [f for f in flights if f.open_seats_total > 0 and all(c.passed for c in flight_basics(b, f))]
    return sorted(ok, key=lambda f: (f.departure_datetime, f.flight_no))


def why_no_flight(b: Booking, flights: list[Flight]) -> str:
    """Plain-language count of why each same-route flight was rejected."""
    same_route = [f for f in flights if check_f1_route(b, f).passed]
    if not same_route:
        return f"No flights at all on {b.origin_airport}-{b.destination_airport}."
    counts = {"cancelled": 0, "outside 18-23 Nov": 0, "before earliest acceptable departure": 0, "no open seats": 0}
    for f in same_route:
        if not check_f2_status(f).passed:
            counts["cancelled"] += 1
        elif not check_f3_window(f).passed:
            counts["outside 18-23 Nov"] += 1
        elif not check_f4_not_early(b, f).passed:
            counts["before earliest acceptable departure"] += 1
        elif f.open_seats_total == 0:
            counts["no open seats"] += 1
    parts = ", ".join(f"{n} {why}" for why, n in counts.items() if n)
    return f"None of the {len(same_route)} {b.origin_airport}-{b.destination_airport} flights pass Section 2 ({parts})."


# ---------------------------------------------------------------- Section 3 re-check


def fits_together(f: Flight, party_size: int) -> bool:
    """The whole party fits in one adjacent block on this flight."""
    return party_size <= f.open_seats_total and party_size <= f.open_seats_adjacent_max


def check_option(
    b: Booking,
    party: Party,
    option: Option,
    flights_by_no: dict[str, Flight],
    together_available: bool,
    min_flights: int | None = None,
) -> list[Check]:
    """Re-check a picked option against every rule. Uses the flight table, not the option's copy."""
    checks: list[Check] = []

    for seg in option.segments:
        live = flights_by_no.get(seg.flight.flight_no)
        if live is None:
            checks.append(Check(f"F0 {seg.flight.flight_no} exists in the flight table", False, "unknown flight"))
            continue
        checks.append(Check(f"F0 {live.flight_no} exists in the flight table", True, "found"))
        checks += flight_basics(b, live)
        checks.append(check_f5_seats(live, len(seg.people), len(seg.together)))
        checks.append(check_f6_connection(live))

    placed = sorted(p.label for seg in option.segments for p in seg.people)
    expected = sorted(p.label for p in party.passengers)
    checks.append(
        Check(
            "P1 every passenger placed exactly once, each with a seat",
            placed == expected,
            f"{len(placed)} placed, party of {party.size}",
        )
    )

    bad = [
        f"no adult in the group on {seg.flight.flight_no}"
        for seg in option.segments
        if any(p.is_minor for p in seg.together) and not any(p.is_adult for p in seg.together)
    ]
    n_minors = sum(p.is_minor for p in party.passengers)
    if bad:
        detail = "; ".join(bad)
    elif not party.make_up_known:
        detail = f"make-up not stated ({party.source}); " + (
            "the agent confirms every group without the lead passenger is adults only" if option.kind == "split"
            else "the whole party sits together"
        )
    else:
        detail = f"{n_minors} child/infant(s), each seated next to an adult" if n_minors else "no children or infants in party"
    checks.append(Check("P2 every child travels and sits with an adult (§3)", not bad, detail))

    if option.kind == "together":
        seg = option.segments[0]
        ok = len(option.segments) == 1 and fits_together(seg.flight, party.size)
        checks.append(Check("P3 together: whole party in one adjacent block on one flight", ok, f"{len(seg.together)} side by side on {seg.flight.flight_no}"))
    else:
        nos = [seg.flight.flight_no for seg in option.segments]
        checks.append(
            Check(
                "P3 split only when no valid flight seats the whole party together",
                not together_available,
                "no together option exists" if not together_available else "a together option exists",
            )
        )
        checks.append(
            Check(
                "P4 split: each group sits side by side on a different flight",
                len(set(nos)) == len(nos) >= 2,
                " + ".join(f"{len(seg.together)} on {seg.flight.flight_no}" for seg in option.segments),
            )
        )
        lead = party.passengers[0]
        checks.append(
            Check(
                "P5 the lead passenger is in the largest group, on the first flight",
                lead in option.segments[0].together
                and len(option.segments[0].together) == max(len(s.together) for s in option.segments),
                f"{lead.label} with {len(option.segments[0].together) - 1} other(s) on {nos[0]}",
            )
        )
        if min_flights is not None:
            checks.append(
                Check(
                    "P6 split uses as few flights as possible",
                    len(option.segments) == min_flights,
                    f"{len(option.segments)} flight(s), minimum possible {min_flights}",
                )
            )
    return checks


def all_passed(checks: list[Check] | tuple[Check, ...]) -> bool:
    return all(c.passed for c in checks)
