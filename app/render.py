"""Plain-text view of one suggestion, as the agent would read it."""
from __future__ import annotations


def _when(ts: str) -> str:
    return ts.replace("T", " ")


def format_suggestion(s: dict) -> str:
    lines = []
    party = s.get("party")
    make_up = ""
    if party and party["make_up_known"]:
        make_up = f" ({party['adults']} adults, {party['children']} children, {party['lap_infants']} lap infants)"
    elif party:
        make_up = " (make-up not stated)"
    lines.append(f"{s['booking_id']}  {s['lead_passenger_name']}  {s['route']}  party of {s['party_size']}{make_up}")
    lines.append(
        f"  suggestion_status: {s['suggestion_status']}    path: {s['path']}    waiver_eligible: {s['waiver_eligible']}    "
        f"earliest acceptable: {_when(s['earliest_acceptable_departure'])}"
    )

    sug = s.get("suggestion")
    if sug:
        head = f"  suggestion {sug['option_id']}: {sug['kind']}"
        if s["family_must_agree"]:
            head += "  ** FAMILY MUST AGREE BEFORE CONFIRMING **"
        lines.append(head)
        for f in sug["flights"]:
            risk = ", weather risk" if f["weather_risk_flag"] else ""
            lines.append(
                f"    {f['flight_no']}  departs {_when(f['departure_datetime'])}  arrives {_when(f['arrival_datetime'])}  "
                f"({f['flight_status']}{risk}; {f['open_seats_total']} open, {f['open_seats_adjacent_max']} side by side)"
            )
            lines.append(f"      {f['passengers']} seated together: {', '.join(f['seated_together'])}")
    for c in s.get("agent_checks", []):
        lines.append(f"  AGENT CHECK: {c}")
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
