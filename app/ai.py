"""Step 3: the model picks ONE option from the list code built, and gives a one-line reason.

It answers in JSON with an option_id. Anything else (bad JSON, an ID not in the
list, an empty reason, a failed call) is reported as an error, and the service
falls back to code. The model never sees a way to add or change flights.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Callable

from .config import OPENROUTER_BASE_URL
from .models import Booking, Option, Party

SYSTEM_PROMPT = """You help a Southwest Airlines contact-center agent rebook a customer whose flight was cancelled by the Denver snowstorm.
Code has already applied every waiver and seating rule and built the list of valid options. Your only job is to pick ONE option from that list and tell the agent why in one line.
Rules:
- Choose an option_id from the list. Never invent a flight or change who sits where.
- OPT-1 is the default (earliest departure). Pick another only if the booking context gives a concrete reason (agent note, onward connection, weather risk, wheelchair or bags), and say what it is.
- The reason is one line, at most 25 words, written for the agent.
Reply with JSON only, no other text: {"option_id": "OPT-n", "reason": "..."}"""

Complete = Callable[[str, str], str]  # (system, user) -> model text


@dataclass(frozen=True)
class AIPick:
    option_id: str | None
    reason: str | None
    error: str | None = None  # set when the pick can't be used
    raw: str | None = None


def build_prompt(b: Booking, party: Party, path: str, options: tuple[Option, ...]) -> str:
    context = {
        "booking": {
            "booking_id": b.booking_id,
            "route": f"{b.origin_airport}-{b.destination_airport}",
            "party_size": b.party_size,
            "passengers": [p.label for p in party.passengers],
            "fare_class": b.fare_class,
            "path": path,
            "earliest_acceptable_departure": b.earliest_acceptable_departure.isoformat(timespec="minutes"),
            "agent_note": b.agent_note,
            "onward_connection_flight_no": b.onward_connection_flight_no,
            "needs_wheelchair_assist": b.needs_wheelchair_assist,
            "has_checked_bags": b.has_checked_bags,
        },
        "options": [
            {
                "option_id": o.option_id,
                "kind": o.kind,
                "family_must_agree": o.family_must_agree,
                "flights": [
                    {
                        "flight_no": s.flight.flight_no,
                        "departure": s.flight.departure_datetime.isoformat(timespec="minutes"),
                        "arrival": s.flight.arrival_datetime.isoformat(timespec="minutes"),
                        "status": s.flight.flight_status,
                        "weather_risk": s.flight.weather_risk_flag,
                        "seated_together": [p.label for p in s.together],
                        "seated_apart": [p.label for p in s.apart],
                    }
                    for s in o.segments
                ],
            }
            for o in options
        ],
    }
    return json.dumps(context, indent=1)


def parse_pick(raw: str, valid_ids: list[str]) -> AIPick:
    match = re.search(r"\{.*\}", raw or "", re.S)
    if not match:
        return AIPick(None, None, "reply has no JSON object", raw)
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return AIPick(None, None, "reply is not valid JSON", raw)
    if not isinstance(data, dict):
        return AIPick(None, None, "reply JSON is not an object", raw)
    option_id, reason = data.get("option_id"), data.get("reason")
    if not isinstance(option_id, str) or option_id.strip() not in valid_ids:
        return AIPick(None, None, f"option_id {option_id!r} is not one of {valid_ids}", raw)
    if not isinstance(reason, str) or not reason.strip():
        return AIPick(None, None, "reply has no reason", raw)
    one_line = " ".join(reason.split())[:240]
    return AIPick(option_id.strip(), one_line, None, raw)


class AIPicker:
    def __init__(self, complete: Complete, model: str):
        self.complete = complete
        self.model = model

    def pick(self, b: Booking, party: Party, path: str, options: tuple[Option, ...]) -> AIPick:
        try:
            raw = self.complete(SYSTEM_PROMPT, build_prompt(b, party, path, options))
        except Exception as exc:  # network, auth, rate limit, ...
            return AIPick(None, None, f"model call failed: {type(exc).__name__}: {exc}")
        return parse_pick(raw, [o.option_id for o in options])


def openrouter_complete(api_key: str, model: str, timeout: float = 30.0) -> Complete:
    """OpenRouter through its OpenAI-compatible API."""
    from openai import OpenAI

    client = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=api_key, timeout=timeout, max_retries=1)

    def complete(system: str, user: str) -> str:
        resp = client.chat.completions.create(
            model=model,
            temperature=0,
            max_tokens=200,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        return resp.choices[0].message.content or ""

    return complete
