"""Create the tables (optional) and load both CSVs into Supabase.

    python -m scripts.seed
    python -m scripts.seed --reset-confirmations   # clear agent confirmations: every booking waits again

- If SUPABASE_DB_URL is set, db/schema.sql is applied first with psql.
  Otherwise run db/schema.sql once in the Supabase SQL editor.
- Needs SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.
Re-running is safe: the schema uses IF NOT EXISTS, rows are upserted, and agents'
confirmations are left alone.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal

from app.config import ROOT, get_settings
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


def apply_schema(db_url: str) -> bool:
    psql = shutil.which("psql")
    if not psql:
        print("psql not found: run db/schema.sql in the Supabase SQL editor instead.", file=sys.stderr)
        return False
    result = subprocess.run(
        [psql, db_url, "-q", "-v", "ON_ERROR_STOP=1", "-f", str(ROOT / "db" / "schema.sql")],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print("Could not apply db/schema.sql:\n" + result.stderr.strip(), file=sys.stderr)
        return False
    print("Tables ready (db/schema.sql applied).")
    return True


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # don't log every Supabase request URL
    settings = get_settings()
    if not settings.use_supabase:
        print("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env first.", file=sys.stderr)
        return 1
    if "--reset-confirmations" in sys.argv[1:]:  # put every booking back on the waiting list (demo rehearsals)
        from app.db import SupabaseRepo

        n = SupabaseRepo(settings.supabase_url, settings.supabase_service_role_key).clear_confirmations()
        print(f"Removed {n} confirmation(s): every booking is waiting again.")
        return 0
    if settings.supabase_db_url and not apply_schema(settings.supabase_db_url):
        return 1

    from supabase import create_client

    client = create_client(settings.supabase_url, settings.supabase_service_role_key)
    booking_rows, flight_rows, passenger_rows = build_rows(settings.data_dir)
    try:
        client.table("bookings").upsert(booking_rows, on_conflict="booking_id").execute()
        client.table("flights").upsert(flight_rows, on_conflict="flight_no").execute()
        ids = [r["booking_id"] for r in booking_rows]
        client.table("passengers").delete().in_("booking_id", ids).execute()  # party make-up may have changed
        client.table("passengers").insert(passenger_rows).execute()
    except Exception as exc:
        if "PGRST205" in str(exc) or "Could not find the table" in str(exc):
            print(
                "The tables don't exist yet. Run db/schema.sql in the Supabase SQL editor, "
                "or set SUPABASE_DB_URL in .env so this script creates them.",
                file=sys.stderr,
            )
            return 1
        raise

    counts = {t: client.table(t).select("*", count="exact").limit(1).execute().count for t in ("bookings", "flights", "passengers")}
    print(f"Seeded Supabase: {counts['bookings']} bookings, {counts['flights']} flights, {counts['passengers']} passengers.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
