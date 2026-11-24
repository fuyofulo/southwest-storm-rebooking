"""Sections 4 and 5: fare result, documentation line and split notes. All plain code."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .models import Booking, Option
from .rules import WAIVER

DOC_LINE = "STORM WAIVER DEN NOV26"


@dataclass(frozen=True)
class FareResult:
    result: str  # "no fare difference" | "collect $X" | "no fare difference to collect"
    collect_usd: Decimal
    fare_paid_usd: Decimal
    new_open_fare_usd: Decimal | None  # non-covered only: base_fare_usd x seats
    detail: str


def _usd(x: Decimal) -> str:
    return f"${x:,.2f}"


def fare_result(b: Booking, path: str, option: Option) -> FareResult:
    if path == WAIVER:
        detail = (
            f"Waiver: fare_paid_usd {_usd(b.fare_paid_usd)} carries over unchanged (§3.2). Nothing collected, "
            f"nothing refunded (§3.1). No change or same-day fees (§3.4). Keeps {b.fare_class} benefits (§3.3)."
        )
        if option.kind == "split":
            detail += " Same treatment for every member of the split party, no penalty for the split (§3.5)."
        return FareResult("no fare difference", Decimal("0.00"), b.fare_paid_usd, None, detail)

    # Non-covered (§4.1): open fare is base_fare_usd per seat; every person has a seat.
    parts = [(seg.flight.flight_no, len(seg.people), seg.flight.base_fare_usd) for seg in option.segments]
    new_total = sum((n * fare for _, n, fare in parts), Decimal("0.00"))
    collect = max(new_total - b.fare_paid_usd, Decimal("0.00"))
    breakdown = " + ".join(f"{n} x {_usd(fare)} on {no}" for no, n, fare in parts)
    detail = (
        f"Non-covered, {b.fare_class} change rules apply (§4.1): open fare {breakdown} = {_usd(new_total)} "
        f"vs {_usd(b.fare_paid_usd)} paid. "
        + ("Quote and collect the difference. " if collect else "Open fare is not higher, nothing to collect. ")
        + f"Refund of unused value follows standard fare rules and is not calculated here. "
        f"Loyalty tier ({b.loyalty_tier}) does not change this (§4.2)."
    )
    result = f"collect {_usd(collect)}" if collect else "no fare difference to collect"
    return FareResult(result, collect, b.fare_paid_usd, new_total, detail)


def documentation_lines(b: Booking, path: str, option: Option) -> list[str]:
    """§3.6: the waiver line on every rebooked flight. §4.4: none on non-covered bookings."""
    if path != WAIVER:
        return []
    return [f"{seg.flight.flight_no}: {DOC_LINE} {b.booking_id}" for seg in option.segments]


def split_notes(b: Booking, option: Option) -> list[str]:
    """§5.4: each piece of a split names the rest of the party so the gate can find them."""
    if option.kind != "split":
        return []
    nos = [seg.flight.flight_no for seg in option.segments]
    notes = []
    for seg in option.segments:
        names = ", ".join(p.label for p in seg.people)
        others = [no for no in nos if no != seg.flight.flight_no]
        if others:
            notes.append(
                f"{seg.flight.flight_no}: party of {b.party_size} from {b.booking_id} split across {', '.join(nos)}. "
                f"On this flight: {names}. Link to the new booking number(s) on {', '.join(others)}."
            )
        else:
            together = ", ".join(p.label for p in seg.together)
            apart = ", ".join(p.label for p in seg.apart)
            notes.append(
                f"{seg.flight.flight_no}: party of {b.party_size} from {b.booking_id} on one flight, seated apart: "
                f"{together} side by side; {apart} elsewhere on the flight."
            )
    return notes
