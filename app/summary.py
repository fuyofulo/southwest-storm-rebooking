"""Counts over a batch of suggestions, plus the safety invariants checked on the output."""
from __future__ import annotations

from collections import Counter

MINOR_PREFIXES = ("Child", "Lap infant")


def safety_problems(s: dict) -> list[str]:
    """Problems found in a response: a child's group with no adult, a flight over its seats, a split on one flight."""
    problems = []
    sug = s.get("suggestion") or {}
    flights = sug.get("flights", [])
    for f in flights:
        group = f["seated_together"]
        if any(p.startswith(MINOR_PREFIXES) for p in group) and not any(p.startswith("Adult") for p in group):
            problems.append(f"{s['booking_id']} {f['flight_no']}: children with no adult")
        if len(group) > f["open_seats_total"] or len(group) > f["open_seats_adjacent_max"]:
            problems.append(f"{s['booking_id']} {f['flight_no']}: {len(group)} placed, more than the seats")
    nos = [f["flight_no"] for f in flights]
    if sug.get("kind") == "split" and (len(nos) < 2 or len(set(nos)) != len(nos)):
        problems.append(f"{s['booking_id']}: split not on different flights")
    return problems


def summarize(results: list[dict]) -> dict:
    status = Counter(s["suggestion_status"] for s in results)
    suggested = [s for s in results if s["suggestion"]]
    none = [s for s in results if not s["suggestion"]]
    why = Counter(
        "Revenue Management" if s["path"] == "revenue_management"
        else "no valid flight" if "None of the" in (s["message"] or "") or "No flights at all" in (s["message"] or "")
        else "not enough seats / no safe split"
        for s in none
    )
    return {
        "bookings": len(results),
        "ready_to_confirm": status["ready_to_confirm"],
        "split_party_confirm": status["split_party_confirm"],
        "split_make_up_to_confirm": sum(1 for s in suggested if s["agent_checks"]),
        "no_option_found": status["no_option_found"],
        "no_option_reasons": dict(why),
        "revenue_management": sum(s["path"] == "revenue_management" for s in results),
        "suggested_waiver_path": sum(s["path"] == "waiver" for s in suggested),
        "suggested_non_covered_path": sum(s["path"] == "non_covered" for s in suggested),
        "ai_pick_used": sum(1 for s in suggested if s["ai"] and not s["ai"]["used_fallback"]),
        "code_fallback": sum(1 for s in suggested if s["ai"] and s["ai"]["used_fallback"]),
        "all_suggestions_pass_every_check": all(all(c["passed"] for c in s["checklist"]) for s in suggested),
        "safety_problems": [p for s in suggested for p in safety_problems(s)],
    }


def format_summary(summary: dict) -> str:
    rows = [
        ("Bookings", summary["bookings"]),
        ("ready_to_confirm (whole party side by side)", summary["ready_to_confirm"]),
        ("split_party_confirm (family must agree)", summary["split_party_confirm"]),
        ("  of which make-up not stated (agent checks)", summary["split_make_up_to_confirm"]),
        ("no_option_found", summary["no_option_found"]),
        *[(f"  {k}", v) for k, v in summary["no_option_reasons"].items()],
        ("Suggestions on waiver / non-covered path", f"{summary['suggested_waiver_path']} / {summary['suggested_non_covered_path']}"),
        ("Model's pick used / code fallback", f"{summary['ai_pick_used']} / {summary['code_fallback']}"),
        ("Every suggestion passes every check", summary["all_suggestions_pass_every_check"]),
        ("Child without an adult, over-full or same-flight split", len(summary["safety_problems"])),
    ]
    width = max(len(k) for k, _ in rows) + 2
    return "\n".join(f"{k:<{width}}{v}" for k, v in rows)
