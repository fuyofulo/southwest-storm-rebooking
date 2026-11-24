"""Load both CSVs into Supabase.

Usage (after running db/schema.sql in the Supabase SQL editor):
    python -m scripts.seed

Re-running is safe: rows are upserted on their primary keys.
"""
from __future__ import annotations

import logging
import sys
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal

from app.config import get_settings
from app.db import load_bookings_csv, load_flights_csv
from app.party import derive_party, party_to_rows


def _jsonable(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        if isinstance(v, datetime):
            v = v.isoformat()
        elif isinstance(v, Decimal):
            v = str(v)
        out[k] = v
    return out


def build_rows(data_dir):
    bookings = load_bookings_csv(data_dir)
    flights = load_flights_csv(data_dir)
    booking_rows = [_jsonable(asdict(b)) for b in bookings]
    flight_rows = [_jsonable(asdict(f)) for f in flights]
    passenger_rows = [row for b in bookings for row in party_to_rows(b.booking_id, derive_party(b))]
    return booking_rows, flight_rows, passenger_rows


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    settings = get_settings()
    if not settings.use_supabase:
        print("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env first.", file=sys.stderr)
        return 1

    from supabase import create_client

    client = create_client(settings.supabase_url, settings.supabase_service_role_key)
    booking_rows, flight_rows, passenger_rows = build_rows(settings.data_dir)

    client.table("bookings").upsert(booking_rows, on_conflict="booking_id").execute()
    client.table("flights").upsert(flight_rows, on_conflict="flight_no").execute()
    ids = [r["booking_id"] for r in booking_rows]
    client.table("passengers").delete().in_("booking_id", ids).execute()  # party make-up may have changed
    client.table("passengers").insert(passenger_rows).execute()

    print(f"Seeded {len(booking_rows)} bookings, {len(passenger_rows)} passengers, {len(flight_rows)} flights.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
