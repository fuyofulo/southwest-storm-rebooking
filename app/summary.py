"""Counts over a batch of suggestions, plus the safety invariants checked on the output."""
from __future__ import annotations

from collections import Counter

MINOR_PREFIXES = ("Child", "Lap infant")


def child_left_without_adult(s: dict) -> list[str]:
    """Problems found in a response: a child seated apart, or a child's group with no adult."""
    problems = []
    for f in (s.get("suggestion") or {}).get("flights", []):
        apart_minors = [p for p in f["seated_apart"] if p.startswith(MINOR_PREFIXES)]
        if apart_minors:
            problems.append(f"{s['booking_id']} {f['flight_no']}: {apart_minors} seated apart")
        together = f["seated_together"]
        if any(p.startswith(MINOR_PREFIXES) for p in together) and not any(p.startswith("Adult") for p in together):
            problems.append(f"{s['booking_id']} {f['flight_no']}: children with no adult")
    return problems


def summarize(results: list[dict]) -> dict:
    status = Counter(s["status"] for s in results)
    suggested = [s for s in results if s["status"] == "suggested"]
    kinds = Counter()
    for s in suggested:
        flights = s["suggestion"]["flights"]
        if s["suggestion"]["kind"] == "together":
            kinds["together"] += 1
        elif len(flights) == 1:
            kinds["split_same_flight_seated_apart"] += 1
        else:
            kinds["split_across_flights"] += 1
    no_sugg = [s for s in results if s["status"] == "no_suggestion"]
    why = Counter(
        "make-up not stated" if "make-up" in s["message"]
        else "child would be without an adult" if "without an adult" in s["message"]
        else "no valid flight / seats"
        for s in no_sugg
    )
    return {
        "bookings": len(results),
        "suggested": len(suggested),
        "together": kinds["together"],
        "split": kinds["split_same_flight_seated_apart"] + kinds["split_across_flights"],
        "split_same_flight_seated_apart": kinds["split_same_flight_seated_apart"],
        "split_across_flights": kinds["split_across_flights"],
        "family_must_agree": sum(s["family_must_agree"] for s in suggested),
        "no_suggestion_flagged_for_agent": len(no_sugg),
        "no_suggestion_reasons": dict(why),
        "revenue_management": status["revenue_management"],
        "suggested_waiver_path": sum(s["path"] == "waiver" for s in suggested),
        "suggested_non_covered_path": sum(s["path"] == "non_covered" for s in suggested),
        "ai_pick_used": sum(1 for s in suggested if s["ai"] and not s["ai"]["used_fallback"]),
        "code_fallback": sum(1 for s in suggested if s["ai"] and s["ai"]["used_fallback"]),
        "all_suggestions_pass_every_check": all(all(c["passed"] for c in s["checklist"]) for s in suggested),
        "child_without_adult_problems": [p for s in suggested for p in child_left_without_adult(s)],
    }


def format_summary(summary: dict) -> str:
    rows = [
        ("Bookings", summary["bookings"]),
        ("Got a suggestion", summary["suggested"]),
        ("  together (one flight, side by side)", summary["together"]),
        ("  split (family must agree)", summary["split"]),
        ("    same flight, someone seated apart", summary["split_same_flight_seated_apart"]),
        ("    across two or more flights", summary["split_across_flights"]),
        ("  waiver path / non-covered path", f"{summary['suggested_waiver_path']} / {summary['suggested_non_covered_path']}"),
        ("  AI pick used / code fallback", f"{summary['ai_pick_used']} / {summary['code_fallback']}"),
        ("No suggestion, flagged for agent", summary["no_suggestion_flagged_for_agent"]),
        *[(f"  {k}", v) for k, v in summary["no_suggestion_reasons"].items()],
        ("Sent to Revenue Management", summary["revenue_management"]),
        ("Every suggestion passes every check", summary["all_suggestions_pass_every_check"]),
        ("Children left without an adult", len(summary["child_without_adult_problems"])),
    ]
    width = max(len(k) for k, _ in rows) + 2
    return "\n".join(f"{k:<{width}}{v}" for k, v in rows)
