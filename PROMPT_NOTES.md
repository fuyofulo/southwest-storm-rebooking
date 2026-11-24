# Prompt notes

How `REBOOKING_SPEC.md` was produced.

## Prompt given to Claude

```
Write a short REBOOKING_SPEC.md (about two pages of Markdown) for a rebooking helper that suggests one valid new itinerary per cancelled Denver storm booking. A contact center agent reviews and confirms every suggestion.

Work from these sources (attached):
1. Storm Travel Waiver Fare Rules Bulletin (Denver, November 2026). Treat its clauses as the deterministic rules and cite clause numbers.
2. My agent minutes readout. The three slowest steps are find open flights, reseat party and check waiver rules. Explain the spec in terms of those.

Structure it as an algorithm:
1. First, a list of routing checks to run BEFORE any search, saying which bookings the helper must not suggest a rebooking for and where they go (out of window or alternate airport → Revenue Management). waiver_eligible = false bookings are NOT skipped: they stay with the agent under the section 4.1 fare-class rules.
2. Then the filter every candidate flight must pass.
3. Then how a suggestion is chosen.

My decisions:
- Keep the party together first. Only split when no valid flight fits everyone.
- A child is always paired with an adult. Never suggest anything where a child travels alone.
- A split is only a suggestion. The family must agree before the agent confirms it.
- Show the fare result with each suggestion: no difference for waiver bookings, the amount to collect for non-covered bookings.
- Never relax a rule to find a flight. If nothing is valid, say so.

List anything the sources don't answer as open questions instead of guessing.
```

## Notes
- The bulletin is the only source of truth for fare and waiver rules. Every rule in the spec cites a clause.
- The family-seating rules (child with an adult, family agreement before a split) are my decisions. They aren't in the bulletin.
- Correction made during review: `waiver_eligible = false` bookings stay with the agent (§4.1). Only out-of-window and alternate-airport requests go to Revenue Management (§2.5, §4.3).
- Re-checking seats at confirm time was added so two agents can't book the same last seats.
