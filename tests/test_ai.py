"""Step 3 and 4: the AI only picks an ID; anything wrong falls back to code and is logged."""
import json
import logging
from dataclasses import replace
from datetime import date
from types import SimpleNamespace

import httpx
import pytest
from openai import BadRequestError

from app import service as service_module
from app.ai import AIPicker, CachedComplete, openrouter_complete, parse_pick
from app.db import InMemoryRepo
from app.options import OptionSet
from app.service import RebookingService
from tests.fakes import make_booking, make_flight, make_party

REQ = date(2026, 11, 18)
IDS = ["OPT-1", "OPT-2"]


def fixed_reply(text):
    return AIPicker(lambda system, user: text, model="fake/model")


def two_flight_service(reply_text, **booking_kw):
    b = make_booking(booking_id="BKG-1", **booking_kw)
    flights = [make_flight("2026-11-18T08:00"), make_flight("2026-11-18T12:00")]
    return RebookingService(InMemoryRepo([b], flights), fixed_reply(reply_text), max_workers=1), flights


# ---- parse_pick


def test_parse_valid_pick():
    p = parse_pick('{"option_id": "OPT-2", "reason": "Later flight avoids weather risk."}', IDS)
    assert p.error is None and p.option_id == "OPT-2"


def test_parse_pick_inside_extra_text():
    p = parse_pick('Sure!\n```json\n{"option_id": "OPT-1", "reason": "Earliest."}\n```', IDS)
    assert p.option_id == "OPT-1"


def test_parse_rejects_invented_option():
    p = parse_pick('{"option_id": "WN9999", "reason": "Made-up flight."}', IDS)
    assert p.error and "not one of" in p.error


def test_parse_rejects_malformed_json():
    assert parse_pick('{"option_id": OPT-1,}', IDS).error == "reply is not valid JSON"
    assert parse_pick("I pick option 1", IDS).error == "reply has no JSON object"


def test_parse_rejects_missing_reason():
    assert parse_pick('{"option_id": "OPT-1"}', IDS).error == "reply has no reason"


def test_reason_is_forced_to_one_line():
    p = parse_pick('{"option_id": "OPT-1", "reason": "Line one.\\nLine two."}', IDS)
    assert p.reason == "Line one. Line two."


# ---- service: steps 3 and 4


def test_valid_ai_pick_is_used_with_its_reason():
    svc, flights = two_flight_service('{"option_id": "OPT-2", "reason": "Customer asked for afternoon."}')
    s = svc.suggest("BKG-1", REQ)
    assert s["suggestion"]["flights"][0]["flight_no"] == flights[1].flight_no
    assert s["ai"] == {"model": "fake/model", "reason": "Customer asked for afternoon.", "used_fallback": False, "fallback_reason": None}


def test_prompt_only_offers_code_built_options():
    seen = {}

    def complete(system, user):
        seen["user"] = json.loads(user)
        return '{"option_id": "OPT-1", "reason": "Earliest."}'

    b = make_booking(booking_id="BKG-1", agent_note="Land before 9pm local.", onward_connection_flight_no="WN3101")
    cancelled = make_flight("2026-11-18T07:00", flight_status="cancelled")
    ok = make_flight("2026-11-18T09:00", weather_risk_flag=True)
    RebookingService(InMemoryRepo([b], [cancelled, ok]), AIPicker(complete, "fake")).suggest("BKG-1", REQ)
    offered = [f["flight_no"] for o in seen["user"]["options"] for f in o["flights"]]
    assert offered == [ok.flight_no]
    assert seen["user"]["booking"]["agent_note"] == "Land before 9pm local."
    assert seen["user"]["booking"]["onward_connection_flight_no"] == "WN3101"
    assert seen["user"]["options"][0]["flights"][0]["weather_risk"] is True


def test_invented_option_falls_back_to_code_and_logs(caplog):
    svc, flights = two_flight_service('{"option_id": "OPT-9", "reason": "Made up."}')
    with caplog.at_level(logging.WARNING, logger="rebooking"):
        s = svc.suggest("BKG-1", REQ)
    assert s["suggestion_status"] == "ready_to_confirm"
    assert s["suggestion"]["option_id"] == "OPT-1"
    assert s["ai"]["used_fallback"] and "OPT-9" in s["ai"]["fallback_reason"]
    assert "BKG-1" in caplog.text and "Falling back" in caplog.text


def test_malformed_reply_falls_back(caplog):
    svc, _ = two_flight_service("not json at all")
    with caplog.at_level(logging.WARNING, logger="rebooking"):
        s = svc.suggest("BKG-1", REQ)
    assert s["suggestion"]["option_id"] == "OPT-1" and s["ai"]["used_fallback"]
    assert "no JSON object" in caplog.text


def test_model_error_falls_back(caplog):
    def boom(system, user):
        raise TimeoutError("OpenRouter timed out")

    b = make_booking(booking_id="BKG-1")
    svc = RebookingService(InMemoryRepo([b], [make_flight()]), AIPicker(boom, "fake"))
    with caplog.at_level(logging.WARNING, logger="rebooking"):
        s = svc.suggest("BKG-1", REQ)
    assert s["suggestion_status"] == "ready_to_confirm" and s["ai"]["used_fallback"]
    assert "TimeoutError" in s["ai"]["fallback_reason"]


def test_pick_that_fails_recheck_falls_back_to_next_valid_option(monkeypatch, caplog):
    # Force the option list to contain a bad OPT-1 (a child alone on the second flight) and a good OPT-2.
    b = make_booking(booking_id="BKG-1", party_size=4)
    party = make_party(adults=2, children=2)
    f1 = make_flight("2026-11-18T08:00", open_seats_total=6, open_seats_adjacent_max=3)
    f2 = make_flight("2026-11-18T12:00", open_seats_total=6, open_seats_adjacent_max=3)
    good = service_module.build_options(b, party, [f1, f2])
    first, second = good.options[0].segments
    child = next(p for p in first.together if p.is_minor)
    bad = replace(good.options[0], segments=(
        replace(first, together=tuple(second.together[0] if p == child else p for p in first.together)),
        replace(second, together=(child,)),
    ))
    monkeypatch.setattr(service_module, "build_options", lambda *a, **k: OptionSet((bad, good.options[1]), False, 2))

    picker = AIPicker(lambda s, u: '{"option_id": "OPT-1", "reason": "Earliest."}', "fake")
    svc = RebookingService(InMemoryRepo([b], [f1, f2], {"BKG-1": party}), picker)
    with caplog.at_level(logging.WARNING, logger="rebooking"):
        s = svc.suggest("BKG-1", REQ)
    assert s["suggestion"]["option_id"] == "OPT-2"
    assert "failed re-check" in s["ai"]["fallback_reason"] and "P2" in s["ai"]["fallback_reason"]
    assert all(c["passed"] for c in s["checklist"])


def test_no_api_key_means_code_choice_without_error():
    b = make_booking(booking_id="BKG-1")
    s = RebookingService(InMemoryRepo([b], [make_flight()]), picker=None).suggest("BKG-1", REQ)
    assert s["suggestion_status"] == "ready_to_confirm" and s["ai"]["used_fallback"]
    assert "not configured" in s["ai"]["fallback_reason"]


# ---- OpenRouter call details (fake client, no network)

PICK = '{"option_id": "OPT-1", "reason": "Earliest."}'


class FakeCompletions:
    def __init__(self, error_text=None):
        self.calls, self.error_text = [], error_text

    def create(self, **kw):
        self.calls.append(kw)
        if self.error_text and "extra_body" in kw:
            response = httpx.Response(400, request=httpx.Request("POST", "https://openrouter.ai"))
            raise BadRequestError(self.error_text, response=response, body=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=PICK))])


def fake_client(error_text=None):
    return SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions(error_text)))


def test_reasoning_is_switched_off():
    client = fake_client()
    assert openrouter_complete("k", "m", client=client)("sys", "user") == PICK
    assert client.chat.completions.calls[0]["extra_body"] == {"reasoning": {"enabled": False}}


def test_model_that_requires_reasoning_is_retried_with_it_on():
    client = fake_client("Reasoning is mandatory for this endpoint and cannot be disabled.")
    complete = openrouter_complete("k", "m", client=client)
    assert complete("sys", "user") == PICK
    assert complete("sys", "user") == PICK
    calls = client.chat.completions.calls
    assert ["extra_body" in c for c in calls] == [True, False, False]  # remembers after the first refusal


def test_other_bad_requests_are_not_swallowed():
    with pytest.raises(BadRequestError):
        openrouter_complete("k", "m", client=fake_client("model not found"))("sys", "user")


def test_cache_serves_repeat_prompts_without_calling_the_model(tmp_path):
    calls = []

    def complete(system, user):
        calls.append(user)
        return PICK if user != "bad" else "no json"

    cached = CachedComplete(complete, "m", tmp_path / "cache.json")
    assert cached("s", "u1") == PICK and cached("s", "u1") == PICK
    assert calls == ["u1"]
    # a fresh instance reads the file
    assert CachedComplete(complete, "m", tmp_path / "cache.json")("s", "u1") == PICK
    assert calls == ["u1"]
    # bad replies are not kept
    cached("s", "bad")
    cached("s", "bad")
    assert calls.count("bad") == 2


def test_daily_free_limit_stops_further_calls_for_today(caplog):
    calls = []

    def capped(system, user):
        calls.append(1)
        raise RuntimeError("Rate limit exceeded: free-models-per-day")

    b = make_booking(booking_id="BKG-1")
    repo = InMemoryRepo([b, replace(b, booking_id="BKG-2"), replace(b, booking_id="BKG-3")], [make_flight()])
    picker = AIPicker(capped, "m")
    with caplog.at_level(logging.WARNING, logger="rebooking"):
        out = RebookingService(repo, picker, max_workers=1).suggest_all(REQ)
    assert len(calls) == 1 and picker.daily_limit_hit
    assert all(s["suggestion_status"] == "ready_to_confirm" and s["ai"]["used_fallback"] for s in out)
    assert all("daily free-model limit" in s["ai"]["fallback_reason"] for s in out)
    assert len(caplog.records) == 1  # one warning, not one per booking


def test_after_the_daily_limit_cached_model_replies_are_still_used(tmp_path):
    # BKG-2's prompt was answered by the model earlier (cached); BKG-1 trips the limit first.
    b1 = make_booking(booking_id="BKG-1")
    b2 = make_booking(booking_id="BKG-2", lead_passenger_name="C. Cached")
    flights = [make_flight()]
    answered = []

    def model(system, user):
        if not answered:
            answered.append(user)
            return '{"option_id": "OPT-1", "reason": "Answered by the model yesterday."}'
        raise RuntimeError("Rate limit exceeded: free-models-per-day")

    cache = CachedComplete(model, "m", tmp_path / "cache.json")
    RebookingService(InMemoryRepo([b2], flights), AIPicker(cache, "m")).suggest("BKG-2", REQ)  # fills the cache

    picker = AIPicker(cache, "m")
    svc = RebookingService(InMemoryRepo([b1, b2], flights), picker, max_workers=1)
    s1, s2 = svc.suggest_all(REQ)
    assert picker.daily_limit_hit and s1["ai"]["used_fallback"]
    assert not s2["ai"]["used_fallback"] and s2["ai"]["reason"] == "Answered by the model yesterday."
