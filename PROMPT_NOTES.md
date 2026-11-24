# Prompt notes

How `REBOOKING_SPEC.md` and the service in `app/` were produced.

## Prompt that writes the spec

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


## Prompt that builds the service

Given to Claude Code in a fresh session at the repo root to turn `REBOOKING_SPEC.md` into the `app/` service.

```
Read REBOOKING_SPEC.md first. It's the source of truth for every rule. Then build a working rebooking suggestion service from it.

## Data
- data/cancelled_bookings_denver_storm.csv and data/flight_seat_availability.csv.
- Before writing code, inspect both files and tell me their columns. Check the spec's open questions against the real data: is there a field for child vs adult, a field for the open fare price, and any info on which seats sit together? If the data doesn't answer one, stop and ask me. Don't guess.

## Stack
- Supabase (Postgres): create tables for bookings, passengers (if the data has them) and flights/seats. Write a seed script that loads both CSVs. Keep the schema in a SQL file in the repo.
- FastAPI backend in Python.
- OpenRouter for the AI model, called through its OpenAI-compatible API. Make the model name a setting (default to a Claude model) so I can swap models.
- Secrets go in .env (SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, OPENROUTER_API_KEY, OPENROUTER_MODEL). Add .env to .gitignore and commit a .env.example with empty values. Never commit keys.

## How a suggestion is made (follow this split strictly)
1. Plain code runs the spec's routing checks (Section 1). Revenue Management cases get no suggestion, only a reason.
2. Plain code builds the list of valid options using the spec's flight filter (Section 2), including split-party options that keep every child with an adult (Section 3).
3. The AI model only picks ONE option from that list and writes a one-line reason for the agent. It must answer in JSON with the option's ID. It can never invent a flight.
4. Plain code checks the picked option again against every rule before returning it. If the AI's pick fails or is malformed, fall back to the best option by plain code and log it.
5. Fare result and documentation line come from code, not the AI (spec Sections 4 and 5).

## API
- GET /suggestions: one suggestion (or a "no suggestion" reason) for every cancelled booking.
- GET /suggestions/{booking_id}: a single booking.
- Each response includes: the flight(s) and who sits on each, the path (waiver / non-covered / Revenue Management), the fare result, the rule checklist that passed, the AI's reason, and whether the family must agree to a split.

## Tests
- Unit tests for every routing check and filter rule, using small fake data.
- A specific test: a family of four (two adults, two children) where the only valid flight has three seats together. Show what the service suggests and prove no child is left without an adult.
- One end-to-end run over the real data that prints a summary: how many bookings got a suggestion, how many were split, how many went to Revenue Management.

## Working style
- Plan first: show me the file structure and table design before writing code.
- Keep it simple. This is a prototype.
- Commit in small steps with clear messages.
- Update README.md with how to set up and run it.
```

### Follow-up answers to Claude Code's questions

Claude Code inspected the data and stopped with five questions before writing code. This was my reply:

```
Go with your recommendations, with these specifics:

Q1: (a). Only split when the party's make-up is stated; unknown make-up gets together options only and is flagged to the agent if none fit.
For lap infants: don't assume they don't need a seat. Count every person in party_size as needing a seat. That way we can never put a party on a flight that's short a seat. Add it to the spec's open questions for the customer.

Q2: (a). Together = one flight with an adjacent block big enough for the whole party. In the family-of-4 case (3 adjacent, 4+ total), both children plus one adult take the block of 3 and the other adult sits elsewhere on the same flight. That counts as a split, so the family must agree. This is the case I need to demo, so make the test print the suggestion clearly.

Q3: (a). A REQUEST_DATE setting plus a ?request_date= query parameter. Use 2026-11-18 for the end-to-end run.

Q4: (a). Direct flights only, and "earliest" means earliest departure. Show onward_connection_flight_no, weather_risk_flag and agent notes to the agent and pass them to the AI as context, as you planned. Code doesn't enforce them.

Q5: Yes, commit both CSVs under the spec's names. They're scenario data.

Also:
- Skipping the truncated flight row with a warning is fine.
- Update REBOOKING_SPEC.md with these decisions (the child rule, the seat counting, adjacent seating, direct only, request date) so the spec matches the code.
- Work on a branch, but merge to main once all tests pass. I'll be submitting the repo link.
```

To rerun: start Claude Code at the repo root, paste the build prompt, then answer its data questions the same way (or reuse the reply above).

## Notes
- The bulletin is the only source of truth for fare and waiver rules. Every rule in the spec cites a clause.
- The family-seating rules (child with an adult, family agreement before a split) are my decisions. They aren't in the bulletin.
- Correction made during review: `waiver_eligible = false` bookings stay with the agent (§4.1). Only out-of-window and alternate-airport requests go to Revenue Management (§2.5, §4.3).
- Re-checking seats at confirm time was added so two agents can't book the same last seats.
