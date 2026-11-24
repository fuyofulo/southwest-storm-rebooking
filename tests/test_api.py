"""HTTP layer: the waiting list, one booking, confirm, and the request_date parameter."""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.db import InMemoryRepo
from app.main import app, get_service
from app.service import RebookingService
from tests.fakes import make_booking, make_flight


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("REQUEST_DATE", "2026-11-18")
    bookings = [
        make_booking(booking_id="BKG-1", cancellation_time=datetime(2026, 11, 16, 2, 0)),
        make_booking(  # fails R3: no option found
            booking_id="BKG-2",
            cancellation_time=datetime(2026, 11, 16, 6, 0),
            earliest_acceptable_departure=datetime(2026, 11, 25, 8, 0),
        ),
    ]
    svc = RebookingService(InMemoryRepo(bookings, [make_flight(flight_no="WN5001")]), picker=None)
    app.dependency_overrides[get_service] = lambda: svc
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_list_returns_waiting_bookings_newest_cancellation_first(client):
    body = client.get("/suggestions").json()
    assert [(s["booking_id"], s["suggestion_status"]) for s in body] == [("BKG-2", "no_option_found"), ("BKG-1", "ready_to_confirm")]


def test_single_booking(client):
    body = client.get("/suggestions/BKG-1").json()
    assert body["suggestion_status"] == "ready_to_confirm" and body["request_date"] == "2026-11-18"
    assert body["suggestion"]["flights"][0]["seated_together"] == ["Adult 1 (T. Tester)"]


def test_no_option_found_booking_still_opens_and_says_why(client):
    body = client.get("/suggestions/BKG-2").json()
    assert body["suggestion_status"] == "no_option_found" and body["suggestion"] is None
    assert body["message"].startswith("No flight met the rules")


def test_confirm_records_and_removes_from_the_waiting_list(client):
    r = client.post("/bookings/BKG-1/confirm", json={"confirmed_by": "Rosalind Mkhize", "option_id": "OPT-1"})
    assert r.status_code == 201
    assert r.json()["confirmed_by"] == "Rosalind Mkhize" and r.json()["flight_nos"] == ["WN5001"]
    assert [s["booking_id"] for s in client.get("/suggestions").json()] == ["BKG-2"]
    assert client.get("/suggestions/BKG-1").json()["confirmation"]["option_id"] == "OPT-1"


def test_confirmations_lists_what_was_confirmed(client):
    assert client.get("/confirmations").json() == []
    client.post("/bookings/BKG-2/confirm", json={"confirmed_by": "Rosalind Mkhize"})
    body = client.get("/confirmations").json()
    assert [s["booking_id"] for s in body] == ["BKG-2"]
    assert body[0]["suggestion_status"] == "no_option_found" and body[0]["confirmation"]["confirmed_by"] == "Rosalind Mkhize"
    assert body[0]["confirmation"]["confirmed_at"]
    assert [s["booking_id"] for s in client.get("/suggestions").json()] == ["BKG-1"]


def test_confirm_stores_the_time_taken(client):
    r = client.post("/bookings/BKG-1/confirm", json={"confirmed_by": "R", "seconds_to_confirm": 42})
    assert r.status_code == 201 and r.json()["seconds_to_confirm"] == 42
    assert client.get("/confirmations").json()[0]["confirmation"]["seconds_to_confirm"] == 42
    assert client.post("/bookings/BKG-2/confirm", json={"confirmed_by": "R", "seconds_to_confirm": -1}).status_code == 422
    assert client.post("/bookings/BKG-2/confirm", json={"confirmed_by": "R"}).json()["seconds_to_confirm"] is None


def test_confirm_errors(client):
    assert client.post("/bookings/NOPE/confirm", json={"confirmed_by": "R"}).status_code == 404
    assert client.post("/bookings/BKG-1/confirm", json={"confirmed_by": "  "}).status_code == 422
    assert client.post("/bookings/BKG-1/confirm", json={}).status_code == 422
    assert client.post("/bookings/BKG-1/confirm", json={"confirmed_by": "R", "option_id": "OPT-4"}).status_code == 409
    assert client.post("/bookings/BKG-1/confirm", json={"confirmed_by": "R"}).status_code == 201
    assert client.post("/bookings/BKG-1/confirm", json={"confirmed_by": "R"}).status_code == 409


def test_request_date_query_parameter_overrides_the_setting(client):
    body = client.get("/suggestions/BKG-1", params={"request_date": "2026-11-24"}).json()
    assert body["suggestion_status"] == "no_option_found" and "R1" in body["message"]


def test_unknown_booking_is_404(client):
    assert client.get("/suggestions/NOPE").status_code == 404


def test_bad_request_date_is_422(client):
    assert client.get("/suggestions/BKG-1", params={"request_date": "tomorrow"}).status_code == 422
