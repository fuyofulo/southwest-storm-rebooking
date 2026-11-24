"""Where bookings, passengers and flights come from.

SupabaseRepo reads the tables created by db/schema.sql and filled by scripts/seed.py.
CsvRepo reads the same two CSVs directly; it backs the tests and lets the service
run before Supabase is set up.
"""
from __future__ import annotations

import csv
import logging
import threading
from pathlib import Path
from typing import Protocol

from .config import Settings
from .models import Booking, Flight, Party
from .party import derive_party, party_from_rows

log = logging.getLogger(__name__)

BOOKINGS_CSV = "cancelled_bookings_denver_storm.csv"
FLIGHTS_CSV = "flight_seat_availability.csv"


def read_csv_rows(path: Path) -> list[dict]:
    """Read a CSV, skipping (and logging) rows that are missing fields."""
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        rows = []
        for line_no, row in enumerate(reader, start=2):
            missing = [k for k, v in row.items() if v is None]
            if missing or None in row:
                first = next(iter(row.values()), "?")
                log.warning("Skipping malformed row %d in %s (%s): missing %s", line_no, path.name, first, missing)
                continue
            rows.append(row)
    return rows


def load_bookings_csv(data_dir: Path) -> list[Booking]:
    return [Booking.from_row(r) for r in read_csv_rows(data_dir / BOOKINGS_CSV)]


def load_flights_csv(data_dir: Path) -> list[Flight]:
    return [Flight.from_row(r) for r in read_csv_rows(data_dir / FLIGHTS_CSV)]


class AlreadyConfirmed(Exception):
    """An agent has already confirmed this booking."""


class Repo(Protocol):
    def bookings(self) -> list[Booking]: ...
    def booking(self, booking_id: str) -> Booking | None: ...
    def flights(self) -> list[Flight]: ...
    def party(self, booking: Booking) -> Party: ...
    def confirmed_ids(self) -> set[str]: ...
    def confirmation(self, booking_id: str) -> dict | None: ...
    def confirmations(self) -> list[dict]: ...
    def add_confirmation(self, record: dict) -> dict: ...  # raises AlreadyConfirmed
    def clear_confirmations(self) -> int: ...


class InMemoryRepo:
    """Holds bookings, flights and confirmations in memory. Used by tests and by CsvRepo."""

    def __init__(self, bookings: list[Booking], flights: list[Flight], parties: dict[str, Party] | None = None):
        self._bookings = {b.booking_id: b for b in bookings}
        self._flights = list(flights)
        self._parties = parties or {}
        self._confirmations: dict[str, dict] = {}
        self._lock = threading.Lock()

    def bookings(self) -> list[Booking]:
        return list(self._bookings.values())

    def booking(self, booking_id: str) -> Booking | None:
        return self._bookings.get(booking_id)

    def flights(self) -> list[Flight]:
        return list(self._flights)

    def party(self, booking: Booking) -> Party:
        return self._parties.get(booking.booking_id) or derive_party(booking)

    def confirmed_ids(self) -> set[str]:
        return set(self._confirmations)

    def confirmation(self, booking_id: str) -> dict | None:
        return self._confirmations.get(booking_id)

    def confirmations(self) -> list[dict]:
        return list(self._confirmations.values())

    def add_confirmation(self, record: dict) -> dict:
        with self._lock:
            if record["booking_id"] in self._confirmations:
                raise AlreadyConfirmed(record["booking_id"])
            self._confirmations[record["booking_id"]] = record
        return record

    def clear_confirmations(self) -> int:
        n = len(self._confirmations)
        self._confirmations.clear()
        return n


class CsvRepo(InMemoryRepo):
    """The CSVs, with confirmations kept in memory only (lost on restart). Supabase keeps them."""

    def __init__(self, data_dir: Path):
        super().__init__(load_bookings_csv(data_dir), load_flights_csv(data_dir))


class SupabaseRepo:
    def __init__(self, url: str | None = None, key: str | None = None, client=None):
        if client is None:
            from supabase import create_client

            client = create_client(url, key)
        self.client = client
        self._passengers: dict[str, list[dict]] = {}

    def _all(self, table: str, **eq) -> list[dict]:
        q = self.client.table(table).select("*")
        for col, val in eq.items():
            q = q.eq(col, val)
        return q.execute().data

    def bookings(self) -> list[Booking]:
        # Fetch every passenger row in one query too, so a full queue run is two round trips, not 140.
        self._passengers = {}
        for row in self._all("passengers"):
            self._passengers.setdefault(row["booking_id"], []).append(row)
        return [Booking.from_row(r) for r in sorted(self._all("bookings"), key=lambda r: r["booking_id"])]

    def booking(self, booking_id: str) -> Booking | None:
        rows = self._all("bookings", booking_id=booking_id)
        return Booking.from_row(rows[0]) if rows else None

    def flights(self) -> list[Flight]:
        return [Flight.from_row(r) for r in self._all("flights")]

    def party(self, booking: Booking) -> Party:
        rows = self._passengers.get(booking.booking_id) or self._all("passengers", booking_id=booking.booking_id)
        if len(rows) != booking.party_size:
            log.warning("%s: %d passenger rows for party_size %d; re-deriving", booking.booking_id, len(rows), booking.party_size)
            return derive_party(booking)
        return party_from_rows(rows)

    def confirmed_ids(self) -> set[str]:
        return {r["booking_id"] for r in self.client.table("confirmations").select("booking_id").execute().data}

    def confirmation(self, booking_id: str) -> dict | None:
        rows = self._all("confirmations", booking_id=booking_id)
        return rows[0] if rows else None

    def confirmations(self) -> list[dict]:
        return self._all("confirmations")

    def add_confirmation(self, record: dict) -> dict:
        try:
            return self.client.table("confirmations").insert(record).execute().data[0]
        except Exception as exc:  # postgrest APIError; 23505 = unique violation (already confirmed)
            if "23505" in str(exc) or "duplicate key" in str(exc):
                raise AlreadyConfirmed(record["booking_id"]) from exc
            raise

    def clear_confirmations(self) -> int:
        return len(self.client.table("confirmations").delete().neq("booking_id", "").execute().data)


def get_repo(settings: Settings) -> Repo:
    if settings.use_supabase:
        return SupabaseRepo(settings.supabase_url, settings.supabase_service_role_key)
    log.info("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set: reading the CSVs in %s", settings.data_dir)
    return CsvRepo(settings.data_dir)
