"""Runs the five steps for each booking and builds the response the agent sees.

1. Routing checks (code). Revenue Management gets a reason, no suggestion.
2. Valid options: together first, then a safe split (code).
3. The AI picks one option by ID and writes a one-line reason.
4. Code re-checks the pick against every rule; on any problem it falls back to the
   best option by code and logs why.
5. Fare result, documentation lines and split notes (code).
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from decimal import Decimal

from .ai import AIPicker
from .db import Repo
from .fares import documentation_lines, fare_result, split_notes
from .models import ADULT, CHILD, LAP_INFANT, UNKNOWN, Booking, Check, Flight, Option, Party
from .options import build_options
from .rules import REVENUE_MANAGEMENT, all_passed, check_option, route

log = logging.getLogger("rebooking")

SUGGESTED, NO_SUGGESTION = "suggested", "no_suggestion"


def _ts(dt: datetime) -> str:
    return dt.isoformat(timespec="minutes")


def _money(x: Decimal | None) -> str | None:
    return None if x is None else f"{x:.2f}"


def _checks(checks) -> list[dict]:
    return [{"rule": c.rule, "passed": c.passed, "detail": c.detail} for c in checks]


def _code_reason(option: Option) -> str:
    first = option.segments[0].flight
    if option.kind == "together":
        return f"Earliest valid flight with the whole party side by side: {first.flight_no} at {_ts(first.departure_datetime)}."
    nos = ", ".join(s.flight.flight_no for s in option.segments)
    return f"No flight seats everyone side by side; earliest safe split on the fewest flights ({nos}), every child with an adult."


class RebookingService:
    def __init__(self, repo: Repo, picker: AIPicker | None = None, max_workers: int = 8):
        self.repo = repo
        self.picker = picker
        self.max_workers = max_workers

    def suggest(self, booking_id: str, request_date: date, use_ai: bool = True) -> dict | None:
        b = self.repo.booking(booking_id)
        if b is None:
            return None
        return self._suggest(b, request_date, use_ai, self.repo.flights())

    def suggest_all(self, request_date: date, use_ai: bool = True) -> list[dict]:
        flights = self.repo.flights()
        bookings = sorted(self.repo.bookings(), key=lambda b: b.booking_id)
        if use_ai and self.picker and self.max_workers > 1:
            with ThreadPoolExecutor(self.max_workers) as pool:
                return list(pool.map(lambda b: self._suggest(b, request_date, True, flights), bookings))
        return [self._suggest(b, request_date, use_ai, flights) for b in bookings]

    # ------------------------------------------------------------------

    def _suggest(self, b: Booking, request_date: date, use_ai: bool, flights: list[Flight]) -> dict:
        out = {
            "booking_id": b.booking_id,
            "lead_passenger_name": b.lead_passenger_name,
            "route": f"{b.origin_airport}-{b.destination_airport}",
            "party_size": b.party_size,
            "request_date": request_date.isoformat(),
            "path": None,
            "status": None,
            "message": None,
            "flagged_for_agent": False,
            "family_must_agree": False,
            "party": None,
            "suggestion": None,
            "fare": None,
            "documentation_lines": [],
            "split_notes": [],
            "checklist": [],
            "ai": None,
            "options_considered": 0,
            "agent_context": {
                "agent_note": b.agent_note,
                "onward_connection_flight_no": b.onward_connection_flight_no,
                "fare_class": b.fare_class,
                "fare_paid_usd": _money(b.fare_paid_usd),
                "waiver_eligible": b.waiver_eligible,
                "loyalty_tier": b.loyalty_tier,
                "has_checked_bags": b.has_checked_bags,
                "needs_wheelchair_assist": b.needs_wheelchair_assist,
                "travels_with_infant": b.travels_with_infant,
                "hotel_voucher_issued": b.hotel_voucher_issued,
                "earliest_acceptable_departure": _ts(b.earliest_acceptable_departure),
            },
        }

        # Step 1: routing
        routing = route(b, request_date)
        out["path"] = routing.path
        out["checklist"] = _checks(routing.checks)
        if routing.path == REVENUE_MANAGEMENT:
            out.update(status=REVENUE_MANAGEMENT, message=routing.reason)
            return out

        # Step 2: valid options
        party = self.repo.party(b)
        out["party"] = self._party(party)
        option_set = build_options(b, party, flights)
        out["options_considered"] = len(option_set.options)
        if not option_set.options:
            out.update(status=NO_SUGGESTION, message=option_set.reason, flagged_for_agent=True)
            return out

        # Steps 3 and 4: AI pick, re-checked by code
        flights_by_no = {f.flight_no: f for f in flights}

        def recheck(o: Option) -> list[Check]:
            return check_option(b, party, o, flights_by_no, option_set.together_available, option_set.min_flights)

        option, checks, ai_info = self._pick(b, party, routing.path, option_set.options, use_ai, recheck)
        if option is None:
            out.update(status=NO_SUGGESTION, message="No option passed the final rule re-check.", flagged_for_agent=True, ai=ai_info)
            return out

        # Step 5: fare and documentation from code
        fare = fare_result(b, routing.path, option)
        out.update(
            status=SUGGESTED,
            family_must_agree=option.family_must_agree,
            suggestion=self._option(option),
            fare={
                "result": fare.result,
                "collect_usd": _money(fare.collect_usd),
                "fare_paid_usd": _money(fare.fare_paid_usd),
                "new_open_fare_usd": _money(fare.new_open_fare_usd),
                "detail": fare.detail,
            },
            documentation_lines=documentation_lines(b, routing.path, option),
            split_notes=split_notes(b, option),
            checklist=out["checklist"] + _checks(checks),
            ai=ai_info,
        )
        if option.family_must_agree:
            out["message"] = "Split party: get the family's agreement before confirming. If they say no, look for a later together option or escalate."
        return out

    def _pick(self, b, party, path, options, use_ai, recheck):
        if use_ai and self.picker is not None:
            pick = self.picker.pick(b, party, path, options)
            if pick.error is None:
                option = next(o for o in options if o.option_id == pick.option_id)
                checks = recheck(option)
                if all_passed(checks):
                    return option, checks, {"model": self.picker.model, "reason": pick.reason, "used_fallback": False, "fallback_reason": None}
                failed = "; ".join(c.rule for c in checks if not c.passed)
                why = f"AI pick {pick.option_id} failed re-check: {failed}"
            else:
                why = f"AI pick unusable: {pick.error}"
            log.warning("%s: %s. Falling back to the best option by code.", b.booking_id, why)
            model = self.picker.model
        else:
            why = "AI not used (use_ai=false)" if not use_ai else "AI not configured (OPENROUTER_API_KEY not set)"
            model = None

        for option in options:  # options are already in best-first order
            checks = recheck(option)
            if all_passed(checks):
                return option, checks, {"model": model, "reason": _code_reason(option), "used_fallback": True, "fallback_reason": why}
            log.error("%s: %s failed re-check: %s", b.booking_id, option.option_id, [c.rule for c in checks if not c.passed])
        return None, [], {"model": model, "reason": None, "used_fallback": True, "fallback_reason": why}

    @staticmethod
    def _party(party: Party) -> dict:
        return {
            "make_up_known": party.make_up_known,
            "make_up_source": party.source,
            "adults": party.count(ADULT),
            "children": party.count(CHILD),
            "lap_infants": party.count(LAP_INFANT),
            "unknown": party.count(UNKNOWN),
            "passengers": [p.label for p in party.passengers],
        }

    @staticmethod
    def _option(option: Option) -> dict:
        return {
            "option_id": option.option_id,
            "kind": option.kind,
            "family_must_agree": option.family_must_agree,
            "flights": [
                {
                    "flight_no": s.flight.flight_no,
                    "departure": _ts(s.flight.departure_datetime),
                    "arrival": _ts(s.flight.arrival_datetime),
                    "flight_status": s.flight.flight_status,
                    "weather_risk_flag": s.flight.weather_risk_flag,
                    "fare_class_open": s.flight.fare_class_open,
                    "base_fare_usd": _money(s.flight.base_fare_usd),
                    "open_seats_total": s.flight.open_seats_total,
                    "open_seats_adjacent_max": s.flight.open_seats_adjacent_max,
                    "seated_together": [p.label for p in s.together],
                    "seated_apart": [p.label for p in s.apart],
                }
                for s in option.segments
            ],
        }
