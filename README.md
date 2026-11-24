# Denver Storm Rebooking Helper

Prototype of a helper that suggests one valid rebooking per itinerary cancelled by the November 2026 Denver snowstorm. Contact center agents review and confirm each suggestion. The goal is under 7 minutes per itinerary, down from about 14, without breaking a single waiver rule.

- [`REBOOKING_SPEC.md`](REBOOKING_SPEC.md): the rules (routing checks, flight filter, party seating, fare treatment, agent confirmation), the source of truth for the code
- [`PROMPT_NOTES.md`](PROMPT_NOTES.md): the prompt used to write the spec, plus notes

## How a suggestion is made

| Step | Who | What |
|---|---|---|
| 1 | code | Routing checks R1–R4 ([`app/rules.py`](app/rules.py)). Revenue Management cases get a reason, no suggestion. |
| 2 | code | Valid options: the flight filter, then "together" options, or safe splits that keep every child beside an adult ([`app/options.py`](app/options.py)). |
| 3 | AI | The model (via OpenRouter) picks **one** option by ID and writes a one-line reason. It answers in JSON and never sees a way to add a flight ([`app/ai.py`](app/ai.py)). |
| 4 | code | The pick is re-checked against every rule. A malformed, unknown or failing pick falls back to the best option by code and is logged ([`app/service.py`](app/service.py)). |
| 5 | code | Fare result, `STORM WAIVER DEN NOV26` documentation line, split notes ([`app/fares.py`](app/fares.py)). |

## Repo layout

```
app/
  config.py    settings from .env
  models.py    Booking, Flight, Passenger, Party, Option, Check
  party.py     who is an adult / child / lap infant (from agent_note + travels_with_infant)
  rules.py     routing checks, flight filter, final re-check -> checklist
  options.py   together options and safe splits
  fares.py     fare result, documentation lines, split notes
  ai.py        OpenRouter call and strict parsing of the model's pick
  service.py   runs the five steps for each booking
  summary.py   counts and safety checks over a batch
  render.py    text view of one suggestion
  db.py        Supabase reads (or the CSVs when Supabase isn't configured)
  main.py      FastAPI endpoints
db/schema.sql  tables: bookings, passengers, flights
scripts/seed.py         load both CSVs into Supabase
scripts/run_summary.py  end-to-end run over the real data
data/          the two scenario CSVs
tests/         unit tests, family-of-four demo, end-to-end run
```

## Setup

Requires Python 3.11+ (developed on 3.15).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill it in
```

`.env` settings (never commit this file; `.env` is git-ignored):

| Setting | What |
|---|---|
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | Supabase project. Server-side only. If either is empty, the service reads the CSVs in `data/` instead. |
| `OPENROUTER_API_KEY` | OpenRouter key. If empty, the service uses the code choice and says so in each response. |
| `OPENROUTER_MODEL` | Any OpenRouter model ID. Default `anthropic/claude-sonnet-5.5`. |
| `REQUEST_DATE` | Date the rebooking request is made, for check R1 (`YYYY-MM-DD`). Default today. After 23 Nov 2026 every booking goes to Revenue Management. |

### Supabase

1. Create a project, open the SQL editor, and run [`db/schema.sql`](db/schema.sql).
2. Load the data:

   ```bash
   python -m scripts.seed
   ```

   Loads 140 bookings, 153 flights and 342 passenger rows. The truncated flight row WN1154 is skipped with a warning. Re-running is safe.

## Run

**API**

```bash
uvicorn app.main:app --reload
# interactive docs: http://127.0.0.1:8000/docs
curl "http://127.0.0.1:8000/suggestions?request_date=2026-11-18"
curl "http://127.0.0.1:8000/suggestions/BKG-10018?request_date=2026-11-18"
```

Both endpoints take `request_date` (overrides `REQUEST_DATE`) and `use_ai` (`false` skips the model). Each response includes:

- `suggestion.flights[]`: flight, times, status, weather risk, `seated_together` (the adjacent block) and `seated_apart`
- `path`: `waiver`, `non_covered` or `revenue_management`
- `status`: `suggested`, `no_suggestion` (flagged for the agent, with `message` saying why) or `revenue_management`
- `fare`: `result` ("no fare difference" / "collect $X") and `detail` with bulletin clauses
- `checklist[]`: every rule checked, with pass/fail and detail
- `ai`: model, one-line reason, and whether code fell back (and why)
- `family_must_agree`: true for every split
- `documentation_lines`, `split_notes`, `agent_context` (agent note, onward connection, bags, wheelchair, ...)

**Tests**

```bash
pytest                                   # everything (no network needed)
pytest -s tests/test_family_of_four.py   # demo: 2 adults + 2 children, only 3 seats together
pytest -s tests/test_end_to_end.py       # summary over the real data
```

**End-to-end summary over the real data**

```bash
python -m scripts.run_summary                    # request date 2026-11-18; uses the model if OPENROUTER_API_KEY is set
python -m scripts.run_summary --no-ai --show-splits
python -m scripts.run_summary --show BKG-10018 BKG-10029
```

## Results on the real data (request date 2026-11-18, code choice)

| | Bookings |
|---|---|
| Got a suggestion | 118 |
| · together (one flight, side by side) | 96 |
| · split, family must agree | 22 (17 on one flight with someone seated apart, 5 across two flights) |
| · non-covered path (fare difference quoted) | 6 |
| No suggestion, flagged for agent | 22 (21 make-up not stated, 1 where any split would leave a child without an adult) |
| Sent to Revenue Management | 0 (all 140 with a request date after 23 Nov) |
| Children left without an adult | 0 |

## Known limits

- Direct flights only. Connections would need a minimum connection time.
- Party make-up comes from free-text agent notes. See the open questions in the spec.
- Onward connections, weather risk and agent-note requests (e.g. "Land before 9pm local") are shown to the agent and the model, not enforced by code.
- Some cross-flight splits put the two halves of a family on different days (e.g. BKG-10018). They meet the spec, and the family must agree first.
- The live OpenRouter call is not covered by the test suite; tests use a stub model so they run offline.
