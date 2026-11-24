"""FastAPI app.

    uvicorn app.main:app --reload
    GET  /suggestions                      bookings still waiting, newest cancellation first
    GET  /suggestions/BKG-10003            one booking (waiting or confirmed)
    POST /bookings/BKG-10003/confirm       record the agent's confirmation (does not book a flight)
"""
from __future__ import annotations

import logging
from datetime import date
from functools import lru_cache

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .ai import make_picker
from .config import get_settings, resolve_request_date
from .db import AlreadyConfirmed, get_repo
from .service import RebookingService, SuggestionChanged

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)  # don't log every Supabase / OpenRouter request
log = logging.getLogger("rebooking")

app = FastAPI(
    title="Denver Storm Rebooking Helper",
    description="Suggests one valid rebooking per cancelled booking. An agent reviews and confirms every suggestion; "
    "Confirm records the decision and never books a flight.",
    version="0.2.0",
)
app.add_middleware(  # the agent page (Vite dev server) normally goes through its proxy; this covers direct calls
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@lru_cache
def get_service() -> RebookingService:
    settings = get_settings()
    picker = make_picker(settings)
    if picker is None:
        log.warning("OPENROUTER_API_KEY not set: suggestions use the code choice and code reason")
    return RebookingService(get_repo(settings), picker)


REQUEST_DATE = Query(None, description="Date the rebooking request is made (check R1). Defaults to REQUEST_DATE, then today.")
USE_AI = Query(True, description="Set false to skip the model and use the code choice.")


class ConfirmRequest(BaseModel):
    confirmed_by: str = Field(..., min_length=1, description="The agent confirming, e.g. 'Rosalind Mkhize'")
    option_id: str | None = Field(None, description="The suggestion the agent saw (e.g. 'OPT-1'); refused if it has changed")


@app.get("/suggestions")
def list_suggestions(
    request_date: date | None = REQUEST_DATE,
    use_ai: bool = USE_AI,
    service: RebookingService = Depends(get_service),
) -> list[dict]:
    """Every booking still waiting for an agent, newest cancellation_time first, each with one suggestion."""
    return service.waiting(resolve_request_date(get_settings(), request_date), use_ai)


@app.get("/suggestions/{booking_id}")
def get_suggestion(
    booking_id: str,
    request_date: date | None = REQUEST_DATE,
    use_ai: bool = USE_AI,
    service: RebookingService = Depends(get_service),
) -> dict:
    result = service.suggest(booking_id, resolve_request_date(get_settings(), request_date), use_ai)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Booking {booking_id} not found")
    return result


@app.post("/bookings/{booking_id}/confirm", status_code=201)
def confirm_booking(
    booking_id: str,
    body: ConfirmRequest,
    request_date: date | None = REQUEST_DATE,
    service: RebookingService = Depends(get_service),
) -> dict:
    """Record the agent's confirmation (who, when, which suggestion). The booking leaves the waiting list.
    This does not book a flight: that is done in Southwest's own systems."""
    if not body.confirmed_by.strip():
        raise HTTPException(status_code=422, detail="confirmed_by is required")
    try:
        record = service.confirm(booking_id, body.confirmed_by, resolve_request_date(get_settings(), request_date), body.option_id)
    except AlreadyConfirmed:
        raise HTTPException(status_code=409, detail=f"Booking {booking_id} is already confirmed")
    except SuggestionChanged as exc:
        raise HTTPException(status_code=409, detail=f"The suggestion has changed, refresh and check again ({exc})")
    if record is None:
        raise HTTPException(status_code=404, detail=f"Booking {booking_id} not found")
    log.info("%s confirmed by %s (%s %s)", booking_id, record["confirmed_by"], record["suggestion_status"], record["flight_nos"])
    return record
