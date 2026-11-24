"""End-to-end run over the real data: one suggestion per booking, then a summary.

    python -m scripts.run_summary                   # request date 2026-11-18, AI if OPENROUTER_API_KEY is set
    python -m scripts.run_summary --no-ai           # code choice only
    python -m scripts.run_summary --show BKG-10018  # also print full suggestions
    python -m scripts.run_summary --show-splits     # print every split

Reads Supabase when SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY are set, otherwise the CSVs.
"""
from __future__ import annotations

import argparse
import logging
from datetime import date

from app.ai import CachedComplete, make_picker
from app.config import get_settings
from app.db import get_repo
from app.render import format_suggestion
from app.service import RebookingService
from app.summary import format_summary, summarize


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--request-date", type=date.fromisoformat, default=date(2026, 11, 18))
    parser.add_argument("--no-ai", action="store_true")
    parser.add_argument("--show", nargs="*", default=[], metavar="BOOKING_ID")
    parser.add_argument("--show-splits", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    settings = get_settings()
    repo = get_repo(settings)
    picker = None if args.no_ai else make_picker(settings)

    results = RebookingService(repo, picker).suggest_all(args.request_date, use_ai=picker is not None)

    source = "Supabase" if settings.use_supabase else "CSV files"
    model = settings.openrouter_model if picker else "none (code choice)"
    print(f"Request date {args.request_date}  |  data: {source}  |  AI model: {model}\n")
    for s in results:
        if s["booking_id"] in args.show or (args.show_splits and s["family_must_agree"]):
            print(format_suggestion(s), end="\n\n")
    summary = summarize(results)
    print(format_summary(summary))
    for problem in summary["safety_problems"]:
        print("  PROBLEM:", problem)
    if picker is not None:
        if isinstance(picker.complete, CachedComplete):
            c = picker.complete
            print(f"\nModel replies: {c.live_calls} live calls to OpenRouter, {c.hits} reused from .cache/ai_replies.json")
        if picker.daily_limit_hit:
            print(
                "OpenRouter's free daily limit was reached, so the remaining bookings used the code choice "
                "(still fully rule-checked).\nRe-run tomorrow to fill them in (cached replies are kept), "
                "or add 10 OpenRouter credits for 1,000 free requests/day."
            )
    return 0 if summary["all_suggestions_pass_every_check"] and not summary["safety_problems"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
