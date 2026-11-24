"""Plain-text view of one suggestion, as the agent would read it."""
from __future__ import annotations


def format_suggestion(s: dict) -> str:
    lines = []
    party = s.get("party")
    make_up = ""
    if party and party["make_up_known"]:
        make_up = f" ({party['adults']} adults, {party['children']} children, {party['lap_infants']} lap infants)"
    elif party:
        make_up = " (make-up not stated)"
    lines.append(f"{s['booking_id']}  {s['route']}  party of {s['party_size']}{make_up}")
    lines.append(f"  path: {s['path']}    status: {s['status']}" + ("    FLAGGED FOR AGENT" if s["flagged_for_agent"] else ""))

    sug = s.get("suggestion")
    if sug:
        head = f"  suggestion {sug['option_id']}: {sug['kind']}"
        if s["family_must_agree"]:
            head += "  ** FAMILY MUST AGREE BEFORE CONFIRMING **"
        lines.append(head)
        for f in sug["flights"]:
            risk = ", weather risk" if f["weather_risk_flag"] else ""
            lines.append(
                f"    {f['flight_no']}  dep {f['departure'].replace('T', ' ')}  arr {f['arrival'].replace('T', ' ')}  "
                f"({f['flight_status']}{risk}; {f['open_seats_total']} open, largest block {f['open_seats_adjacent_max']})"
            )
            lines.append(f"      seated together: {', '.join(f['seated_together'])}")
            if f["seated_apart"]:
                lines.append(f"      seated apart:    {', '.join(f['seated_apart'])}")
    if s.get("fare"):
        lines.append(f"  fare: {s['fare']['result']}  ({s['fare']['detail']})")
    for d in s.get("documentation_lines", []):
        lines.append(f"  record: {d}")
    for n in s.get("split_notes", []):
        lines.append(f"  split note: {n}")
    if s.get("message"):
        lines.append(f"  note: {s['message']}")
    if s.get("ai"):
        if s["ai"]["used_fallback"]:
            tag = f" (code fallback: {s['ai']['fallback_reason']})"
        else:
            tag = f" ({s['ai']['model']})"
        lines.append(f"  reason{tag}: {s['ai']['reason']}")
    lines.append("  checklist:")
    for c in s.get("checklist", []):
        lines.append(f"    [{'PASS' if c['passed'] else 'FAIL'}] {c['rule']}: {c['detail']}")
    return "\n".join(lines)
