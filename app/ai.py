"""Step 3: the model picks ONE option from the list code built, and gives a one-line reason.

It answers in JSON with an option_id. Anything else (bad JSON, an ID not in the
list, an empty reason, a failed call) is reported as an error, and the service
falls back to code. The model never sees a way to add or change flights.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable

from .config import OPENROUTER_BASE_URL, Settings
from .models import Booking, Option, Party

log = logging.getLogger("rebooking")

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
    skipped: bool = False  # the model wasn't called (daily limit already hit); nothing new to log


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
                **({"agent_checks": list(o.agent_checks)} if o.agent_checks else {}),
                "flights": [
                    {
                        "flight_no": s.flight.flight_no,
                        "departure": s.flight.departure_datetime.isoformat(timespec="minutes"),
                        "arrival": s.flight.arrival_datetime.isoformat(timespec="minutes"),
                        "status": s.flight.flight_status,
                        "weather_risk": s.flight.weather_risk_flag,
                        "seated_together": [p.label for p in s.together],
                        # Always empty now (nobody sits apart on the same flight). Kept so prompts for
                        # together options stay byte-identical and earlier cached model replies stay valid.
                        "seated_apart": [],
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
        self._daily_limit_hit_on: date | None = None
        self._lock = threading.Lock()

    @property
    def daily_limit_hit(self) -> bool:
        return self._daily_limit_hit_on == date.today()

    def pick(self, b: Booking, party: Party, path: str, options: tuple[Option, ...]) -> AIPick:
        prompt = build_prompt(b, party, path, options)
        if self.daily_limit_hit:
            # No new calls today, but a reply the model already gave for this exact prompt is still its answer.
            lookup = getattr(self.complete, "lookup", None)
            raw = lookup(SYSTEM_PROMPT, prompt) if lookup else None
            if raw is not None:
                return parse_pick(raw, [o.option_id for o in options])
            return AIPick(None, None, "OpenRouter daily free-model limit reached; not calling the model", skipped=True)
        try:
            raw = self.complete(SYSTEM_PROMPT, prompt)
        except Exception as exc:  # network, auth, rate limit, ...
            text = str(exc)
            if "per-day" in text or "per day" in text:
                with self._lock:  # parallel workers can hit the limit together; warn once
                    first = not self.daily_limit_hit
                    self._daily_limit_hit_on = date.today()
                if first:
                    log.warning(
                        "OpenRouter daily free-model limit reached: using the code choice for the rest of today. "
                        "Cached replies are still used. (OpenRouter: add 10 credits for 1,000 free requests/day.)"
                    )
                return AIPick(None, None, "OpenRouter daily free-model limit reached; not calling the model", skipped=True)
            return AIPick(None, None, f"model call failed: {type(exc).__name__}: {text[:200]}")
        return parse_pick(raw, [o.option_id for o in options])


def openrouter_complete(api_key: str, model: str, timeout: float = 60.0, client=None) -> Complete:
    """OpenRouter through its OpenAI-compatible API.

    Picking an option is a small task, so reasoning is switched off: free reasoning
    models otherwise spend the whole token budget thinking and return no answer.
    Models that can't switch it off are retried once with it on.
    """
    from openai import BadRequestError, OpenAI

    client = client or OpenAI(base_url=OPENROUTER_BASE_URL, api_key=api_key, timeout=timeout, max_retries=3)
    state = {"reasoning_off": True}

    def complete(system: str, user: str) -> str:
        kwargs = dict(
            model=model,
            temperature=0,
            max_tokens=1500,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        if state["reasoning_off"]:
            try:
                resp = client.chat.completions.create(**kwargs, extra_body={"reasoning": {"enabled": False}})
                return resp.choices[0].message.content or ""
            except BadRequestError as exc:
                if "reasoning" not in str(exc).lower():
                    raise
                state["reasoning_off"] = False
        resp = client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""

    return complete


class CachedComplete:
    """Keeps model replies on disk, keyed by model + prompt, so re-runs don't spend free-tier quota.

    The prompt holds the flights and open seats, so any change in inventory is a new key.
    Only replies that look like a pick are kept; a bad reply is asked again next time.
    """

    def __init__(self, complete: Complete, model: str, path: Path):
        self.complete, self.model, self.path = complete, model, path
        self.hits = self.live_calls = 0
        self._lock = threading.Lock()
        try:
            self._cache: dict[str, str] = json.loads(path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            self._cache = {}

    def _key(self, system: str, user: str) -> str:
        return hashlib.sha256(f"{self.model}\n{system}\n{user}".encode()).hexdigest()

    def lookup(self, system: str, user: str) -> str | None:
        """The stored reply for this exact prompt, without calling the model."""
        with self._lock:
            raw = self._cache.get(self._key(system, user))
            if raw is not None:
                self.hits += 1
            return raw

    def __call__(self, system: str, user: str) -> str:
        key = self._key(system, user)
        with self._lock:
            if key in self._cache:
                self.hits += 1
                return self._cache[key]
            self.live_calls += 1
        raw = self.complete(system, user)
        if '"option_id"' in raw:
            with self._lock:
                self._cache[key] = raw
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.path.write_text(json.dumps(self._cache, indent=1))
        return raw


def make_picker(settings: Settings) -> AIPicker | None:
    """The picker the app and scripts use: OpenRouter, with the reply cache. None without a key."""
    if not settings.openrouter_api_key:
        return None
    complete = openrouter_complete(settings.openrouter_api_key, settings.openrouter_model)
    cached = CachedComplete(complete, settings.openrouter_model, settings.cache_dir / "ai_replies.json")
    return AIPicker(cached, settings.openrouter_model)
