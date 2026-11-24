"""HTTP layer: both endpoints and the request_date parameter."""
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
        make_booking(booking_id="BKG-1"),
        make_booking(booking_id="BKG-2", earliest_acceptable_departure=datetime(2026, 11, 25, 8, 0)),  # fails R3
    ]
    svc = RebookingService(InMemoryRepo(bookings, [make_flight()]), picker=None)
    app.dependency_overrides[get_service] = lambda: svc
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_list_returns_every_booking(client):
    body = client.get("/suggestions").json()
    assert {s["booking_id"]: s["status"] for s in body} == {"BKG-1": "suggested", "BKG-2": "revenue_management"}


def test_single_booking(client):
    body = client.get("/suggestions/BKG-1").json()
    assert body["status"] == "suggested" and body["request_date"] == "2026-11-18"
    assert body["suggestion"]["flights"][0]["seated_together"] == ["Adult 1 (T. Tester)"]


def test_request_date_query_parameter_overrides_the_setting(client):
    body = client.get("/suggestions/BKG-1", params={"request_date": "2026-11-24"}).json()
    assert body["status"] == "revenue_management" and "R1" in body["message"]


def test_unknown_booking_is_404(client):
    assert client.get("/suggestions/NOPE").status_code == 404


def test_bad_request_date_is_422(client):
    assert client.get("/suggestions/BKG-1", params={"request_date": "tomorrow"}).status_code == 422
