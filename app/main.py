"""FastAPI app.

    uvicorn app.main:app --reload
    GET /suggestions?request_date=2026-11-18
    GET /suggestions/BKG-10003?request_date=2026-11-18
"""
from __future__ import annotations

import logging
from datetime import date
from functools import lru_cache

from fastapi import Depends, FastAPI, HTTPException, Query

from .ai import make_picker
from .config import get_settings, resolve_request_date
from .db import get_repo
from .service import RebookingService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("rebooking")

app = FastAPI(
    title="Denver Storm Rebooking Helper",
    description="Suggests one valid rebooking per cancelled booking. An agent reviews and confirms every suggestion.",
    version="0.1.0",
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


@app.get("/suggestions")
def list_suggestions(
    request_date: date | None = REQUEST_DATE,
    use_ai: bool = USE_AI,
    service: RebookingService = Depends(get_service),
) -> list[dict]:
    return service.suggest_all(resolve_request_date(get_settings(), request_date), use_ai)


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
