"""Runs the five steps for each booking and builds the response the agent sees.

1. Routing checks (code). Revenue Management gets a reason, no suggestion.
2. Valid options: together first, then a split party (code).
3. The AI picks one option by ID and writes a one-line reason.
4. Code re-checks the pick against every rule; on any problem it falls back to the
   best option by code and logs why.
5. Fare result, documentation lines and split notes (code).

Every booking ends up with one suggestion_status:
  ready_to_confirm     the whole party side by side on one flight
  split_party_confirm  the party split into side-by-side groups on different flights; the family must agree
  no_option_found      no flight met the rules (or the booking goes to Revenue Management)

The agent's Confirm is recorded (who, when, which suggestion). It never books a flight.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from decimal import Decimal

from .ai import AIPicker
from .db import AlreadyConfirmed, Repo
from .fares import documentation_lines, fare_result, split_notes
from .models import ADULT, CHILD, LAP_INFANT, UNKNOWN, Booking, Check, Flight, Option, Party
from .options import build_options
from .rules import REVENUE_MANAGEMENT, all_passed, check_option, route

log = logging.getLogger("rebooking")

READY, SPLIT, NONE = "ready_to_confirm", "split_party_confirm", "no_option_found"
CONFIRMATION_FIELDS = ("booking_id", "confirmed_by", "confirmed_at", "suggestion_status", "option_id", "flight_nos")
SUGGESTION_STATUSES = (READY, SPLIT, NONE)


class SuggestionChanged(Exception):
    """The suggestion the agent saw is no longer the current one (for example, seats changed)."""


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
    parts = " + ".join(f"{len(s.together)} on {s.flight.flight_no}" for s in option.segments)
    return f"No flight seats everyone side by side; split with the lead's group kept largest ({parts}), every child with an adult."


class RebookingService:
    def __init__(self, repo: Repo, picker: AIPicker | None = None, max_workers: int = 4):
        self.repo = repo
        self.picker = picker
        self.max_workers = max_workers

    def suggest(self, booking_id: str, request_date: date, use_ai: bool = True) -> dict | None:
        b = self.repo.booking(booking_id)
        if b is None:
            return None
        out = self._suggest(b, request_date, use_ai, self.repo.flights())
        out["confirmation"] = self.repo.confirmation(booking_id)
        return out

    def suggest_all(self, request_date: date, use_ai: bool = True) -> list[dict]:
        """Every booking, by booking_id (confirmed or not)."""
        return self._run(sorted(self.repo.bookings(), key=lambda b: b.booking_id), request_date, use_ai)

    def waiting(self, request_date: date, use_ai: bool = True) -> list[dict]:
        """Bookings not yet confirmed by an agent, newest cancellation_time first."""
        done = self.repo.confirmed_ids()
        todo = [b for b in self.repo.bookings() if b.booking_id not in done]
        todo.sort(key=lambda b: (b.cancellation_time, b.booking_id), reverse=True)
        return self._run(todo, request_date, use_ai)

    def confirmed(self) -> list[dict]:
        """Bookings an agent has confirmed, most recent first.

        Each is the suggestion exactly as the agent saw it when confirming (the stored snapshot, so it doesn't
        change if seats move later), plus `confirmation`: who confirmed it, when, and which suggestion.
        """
        out = []
        for r in self.repo.confirmations():
            item = dict(r.get("suggestion") or {"booking_id": r["booking_id"]})
            item.setdefault("checklist", [])
            item["confirmation"] = {k: r.get(k) for k in CONFIRMATION_FIELDS}
            out.append(item)
        out.sort(key=lambda s: (s["confirmation"]["confirmed_at"] or "", s["booking_id"]), reverse=True)
        return out

    def confirm(self, booking_id: str, confirmed_by: str, request_date: date, option_id: str | None = None) -> dict | None:
        """Record the agent's decision against the booking. None if the booking doesn't exist.

        Raises AlreadyConfirmed, or SuggestionChanged when option_id no longer matches the current suggestion.
        """
        s = self.suggest(booking_id, request_date)
        if s is None:
            return None
        if s["confirmation"]:
            raise AlreadyConfirmed(booking_id)
        current = (s["suggestion"] or {}).get("option_id")
        if option_id is not None and option_id != current:
            raise SuggestionChanged(f"{booking_id}: the current suggestion is {current or 'none'}, not {option_id}")
        snapshot = {k: v for k, v in s.items() if k not in ("checklist", "confirmation")}
        record = {
            "booking_id": booking_id,
            "confirmed_by": confirmed_by.strip(),
            "confirmed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "suggestion_status": s["suggestion_status"],
            "option_id": current,
            "flight_nos": [f["flight_no"] for f in (s["suggestion"] or {}).get("flights", [])],
            "suggestion": snapshot,
        }
        return self.repo.add_confirmation(record)

    # ------------------------------------------------------------------

    def _run(self, bookings: list[Booking], request_date: date, use_ai: bool) -> list[dict]:
        flights = self.repo.flights()
        if use_ai and self.picker and self.max_workers > 1:
            with ThreadPoolExecutor(self.max_workers) as pool:
                return list(pool.map(lambda b: self._suggest(b, request_date, True, flights), bookings))
        return [self._suggest(b, request_date, use_ai, flights) for b in bookings]

    def _suggest(self, b: Booking, request_date: date, use_ai: bool, flights: list[Flight]) -> dict:
        out = {
            "booking_id": b.booking_id,
            "lead_passenger_name": b.lead_passenger_name,
            "party_size": b.party_size,
            "origin_airport": b.origin_airport,
            "destination_airport": b.destination_airport,
            "route": f"{b.origin_airport}-{b.destination_airport}",
            "earliest_acceptable_departure": _ts(b.earliest_acceptable_departure),
            "cancellation_time": _ts(b.cancellation_time),
            "waiver_eligible": b.waiver_eligible,
            "request_date": request_date.isoformat(),
            "path": None,
            "suggestion_status": NONE,
            "message": None,
            "family_must_agree": False,
            "agent_checks": [],
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
                "cancelled_flight_no": b.cancelled_flight_no,
                "fare_class": b.fare_class,
                "fare_paid_usd": _money(b.fare_paid_usd),
                "loyalty_tier": b.loyalty_tier,
                "has_checked_bags": b.has_checked_bags,
                "needs_wheelchair_assist": b.needs_wheelchair_assist,
                "travels_with_infant": b.travels_with_infant,
                "hotel_voucher_issued": b.hotel_voucher_issued,
            },
        }

        # Step 1: routing
        routing = route(b, request_date)
        out["path"] = routing.path
        out["checklist"] = _checks(routing.checks)
        if routing.path == REVENUE_MANAGEMENT:
            out["message"] = f"No flight met the rules: send to Revenue Management. {routing.reason}"
            return out

        # Step 2: valid options
        party = self.repo.party(b)
        out["party"] = self._party(party)
        option_set = build_options(b, party, flights)
        out["options_considered"] = len(option_set.options)
        if not option_set.options:
            out["message"] = option_set.reason
            return out

        # Steps 3 and 4: AI pick, re-checked by code
        flights_by_no = {f.flight_no: f for f in flights}

        def recheck(o: Option) -> list[Check]:
            return check_option(b, party, o, flights_by_no, option_set.together_available, option_set.min_flights)

        option, checks, ai_info = self._pick(b, party, routing.path, option_set.options, use_ai, recheck)
        if option is None:
            out.update(message="No flight met the rules: no option passed the final rule re-check.", ai=ai_info)
            return out

        # Step 5: fare and documentation from code
        fare = fare_result(b, routing.path, option)
        out.update(
            suggestion_status=SPLIT if option.kind == "split" else READY,
            family_must_agree=option.family_must_agree,
            agent_checks=list(option.agent_checks),
            suggestion=self._option(option, party),
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
            out["message"] = "Split party: the family must agree before you confirm. If they say no, escalate."
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
                why = pick.error if pick.skipped else f"AI pick unusable: {pick.error}"
            if not pick.skipped:  # skipped = daily limit, already logged once by the picker
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
    def _option(option: Option, party: Party) -> dict:
        lead = party.passengers[0]
        return {
            "option_id": option.option_id,
            "kind": option.kind,
            "family_must_agree": option.family_must_agree,
            "flights": [
                {
                    "flight_no": s.flight.flight_no,
                    "departure_datetime": _ts(s.flight.departure_datetime),
                    "arrival_datetime": _ts(s.flight.arrival_datetime),
                    "flight_status": s.flight.flight_status,
                    "weather_risk_flag": s.flight.weather_risk_flag,
                    "fare_class_open": s.flight.fare_class_open,
                    "base_fare_usd": _money(s.flight.base_fare_usd),
                    "open_seats_total": s.flight.open_seats_total,
                    "open_seats_adjacent_max": s.flight.open_seats_adjacent_max,
                    "passengers": len(s.together),
                    "seated_together": [p.label for p in s.together],
                    "includes_lead_passenger": lead in s.together,
                }
                for s in option.segments
            ],
        }
