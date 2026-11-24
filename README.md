# Denver Storm Rebooking Helper

Prototype of an agent page and rebooking service that suggests one valid rebooking per itinerary cancelled by the November 2026 Denver snowstorm. Contact center agents open each booking, check the suggestion and click Confirm. The goal is under 7 minutes per itinerary, down from about 14, without breaking a single waiver rule.

- **Minutes readout:** [one-page readout (Google Doc)](https://docs.google.com/document/d/1rbDkRzf2yGuapAuQeSoYcntC3FZvU6SkmkLMvhFvoAc/edit?usp=drivesdk)
- **Rules:** [`REBOOKING_SPEC.md`](REBOOKING_SPEC.md) is the spec the suggestions are built against (the acceptance criteria call it SPEC.md).
- [`PROMPT_NOTES.md`](PROMPT_NOTES.md): the prompt used to write the spec, plus notes.

The assistant only suggests. **Confirm records the agent's decision; it never books a flight.** The booking is made in Southwest's own systems.

## Run it locally

Needs Python 3.11+ and Node.js 20+.

```bash
./run.sh app
```

That starts the rebooking service on http://127.0.0.1:8000 and the agent page on **http://localhost:5173** (Ctrl+C stops both). The first run creates `.venv`, installs the Python and page dependencies, and creates `.env` from `.env.example`.

| Command | What it does |
|---|---|
| `./run.sh` | Tests, create the Supabase tables and load both CSVs, the family-of-four demo, and the summary over the real data |
| `./run.sh app` | Service and page together |
| `./run.sh serve` | Only the service (API docs at http://127.0.0.1:8000/docs) |
| `./run.sh page` | Only the page (the service must be running) |
| `./run.sh reset` | Clear every agent confirmation, so all bookings are waiting again |

## Environment values (`.env`)

Names only. `.env` is git-ignored; [`.env.example`](.env.example) lists them with empty values.

| Name | What |
|---|---|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service-role (secret) key. Server side only, never sent to the page |
| `SUPABASE_DB_URL` | Optional Postgres connection string, so `./run.sh` can create the tables itself (needs `psql`) |
| `OPENROUTER_API_KEY` | OpenRouter key for the model call |
| `OPENROUTER_MODEL` | OpenRouter model id. Empty = `nvidia/nemotron-3-ultra-550b-a55b:free` |
| `REQUEST_DATE` | Date the rebooking request is made (check R1). `.env.example` uses 2026-11-18 |

Without the Supabase values the service reads `data/*.csv` and keeps confirmations in memory only.

## The agent page

One quiet screen, no second page or tab, in light or dark (follows the system; the sun/moon button switches). A top bar with the agent's name, a sub-bar with a `suggestion_status` filter (All / Ready / Split / No option), "Booking 5 of 140" arrows and a search box, and a status bar with keyboard hints.

The list holds every booking still waiting, newest `cancellation_time` first. Each row shows `lead_passenger_name` with `booking_id` under it, `party_size`, `origin_airport` → `destination_airport`, `earliest_acceptable_departure`, the one suggestion, its `suggestion_status` and a Confirm button. Clicking a row opens it beside the list with:

- each suggested flight's `flight_no`, `departure_datetime`, `open_seats_total`, `open_seats_adjacent_max` and `flight_status`, and who sits on it, with the lead passenger named;
- `waiver_eligible`, the fare result and the original fare;
- the model's one-line reason, or a plain note that the code chose because the model did not answer;
- the agent note, onward connection and bags, plus the rule checklist (collapsed).

| `suggestion_status` | Meaning | Confirm |
|---|---|---|
| `ready_to_confirm` | Whole party side by side on one flight | One click |
| `split_party_confirm` | Party split into side-by-side groups on different flights. Party of 4, best block 3: three including the lead on that flight, the fourth on another valid flight | Needs the "family agreed" tick first. If the make-up isn't stated, the tick also confirms the separate passenger is an adult |
| `no_option_found` | No flight met the rules; the panel says why | Records that the agent handled it by hand or escalated it |

After Confirm the row leaves the list and the next booking opens. If the service is down, the page says so and offers Try again; it never spins forever.

| Key | Does |
|---|---|
| `j` / `k` (or ↓ / ↑) | Next / previous booking |
| `a` | Tick "the family agreed" on a split |
| `⌘↵` (Ctrl+Enter) | Confirm the open booking |
| `/` | Search by name, booking, route or flight (Esc clears) |
| `r` | Refresh the list |

**Screenshot: the family of four's suggestion, `split_party_confirm`, confirmed**

> _Placeholder: add the screenshot here (for example `docs/split_party_confirm.png`)._

## How a suggestion is made

| Step | Who | What |
|---|---|---|
| 1 | code | Routing checks R1–R4 ([`app/rules.py`](app/rules.py)). Revenue Management cases get `no_option_found` with the reason. |
| 2 | code | Valid options: the flight filter, then together options, or split-party options on different flights that keep every child with an adult ([`app/options.py`](app/options.py)). |
| 3 | AI | The model, called live through OpenRouter, picks **one** option by ID and writes a one-line reason. It answers in JSON and has no way to add a flight ([`app/ai.py`](app/ai.py)). |
| 4 | code | The pick is re-checked against every rule. A malformed, unknown or failing pick falls back to the best option by code, is logged, and the page says so ([`app/service.py`](app/service.py)). |
| 5 | code | Fare result, `STORM WAIVER DEN NOV26` documentation line, split notes ([`app/fares.py`](app/fares.py)). |

**Free model limits.** A free OpenRouter key allows about 50 free-model requests a day; the full list needs about 138. Each model reply is stored in `.cache/ai_replies.json`, keyed by the exact prompt, including the flights and open seats, and reused, so each booking is asked once. Once the daily limit is hit, uncached rows show the code's choice and say why. Adding 10 OpenRouter credits raises the limit to 1,000 a day.

## API

| Endpoint | What |
|---|---|
| `GET /suggestions` | Every booking still waiting, newest `cancellation_time` first, each with one suggestion |
| `GET /suggestions/{booking_id}` | One booking, waiting or confirmed (with its `confirmation`) |
| `POST /bookings/{booking_id}/confirm` | Body `{"confirmed_by": "Rosalind Mkhize", "option_id": "OPT-1"}`. Records who, when and which suggestion in the Supabase `confirmations` table; the booking leaves the waiting list. 409 if already confirmed or the suggestion changed. It does not book a flight |

`GET` endpoints take `request_date` and `use_ai`. Each suggestion includes `suggestion_status`, `suggestion.flights[]`, `path` (`waiver`, `non_covered`, `revenue_management`), `waiver_eligible`, `fare`, `checklist`, `ai` (model, reason, whether code fell back and why), `family_must_agree`, `agent_checks`, `documentation_lines`, `split_notes` and `agent_context`.

## Repo layout

```
run.sh         the one command
app/           the rebooking service (FastAPI)
  rules.py     routing checks, flight filter, final re-check -> checklist
  options.py   together options and split-party options
  ai.py        OpenRouter call, reply cache, strict parsing of the model's pick
  service.py   the five steps, waiting list, confirm
  fares.py     fare result, documentation lines, split notes
  party.py     who is an adult / child / lap infant (from agent_note + travels_with_infant)
  db.py        Supabase (or the CSVs), confirmations
  main.py      endpoints
web/           the agent page (React + Vite)
db/schema.sql  tables: bookings, passengers, flights, confirmations
scripts/       seed.py (Supabase), demo_family.py, run_summary.py
data/          the two scenario CSVs
tests/         unit tests, family-of-four case, confirm, no_option_found, end-to-end run
```

## Results on the real data (request date 2026-11-18)

| `suggestion_status` | Bookings |
|---|---|
| `ready_to_confirm` | 96 |
| `split_party_confirm` | 42 (21 where the agent also confirms the separate group is adults) |
| `no_option_found` | 2 (no way to seat the party in side-by-side groups on different flights) |

All 7 parties of 4 whose best flight has 3 seats side by side come out as `split_party_confirm`: three including the lead on that flight, the fourth on a different one. No child is left without an adult, no flight gets more people than its open seats, and every suggestion passes every check (`tests/test_end_to_end.py`). Six non-covered bookings get a suggestion with the fare difference quoted.

## Claude Code instruction for the page

The key instruction given to Claude Code for the page:

> "Build the agent page (React + Vite, in /web). One screen, no second page or tab … For split_party_confirm: show the three passengers seated together (with the lead passenger named) on one flight, and the fourth passenger's flight_no and departure_datetime. Show a clear note that the family must agree before confirming. A no_option_found booking still opens and states plainly that no flight met the rules. No empty panels and no spinners that never end. … Keep it fast to scan. Agents will be timed opening and confirming each booking."

## Changes to the AI's output

- Rejected Claude Code's first split rule. It seated the family of four's fourth member elsewhere on the same three-block flight, which fails the split-party criterion. It was rewritten so the fourth passenger goes on a different valid flight (`tests/test_family_of_four.py`).
- Fixed a Claude Code bug found while testing the page. Once OpenRouter's daily limit was hit, cached model replies were ignored and rows fell back to code text instead of the model's reason.

## Known limits

- Direct flights only. Connections would need a minimum connection time.
- Party make-up comes from free-text agent notes. When it isn't stated, a split relies on the agent confirming the separate group is adults (see the spec's open questions).
- Onward connections, weather risk and agent-note requests (e.g. "Land before 9pm local") are shown to the agent and the model, not enforced by code.
- On a free OpenRouter key, bookings beyond the daily allowance show the code's choice until a later run asks the model.
