# Denver Storm Rebooking Helper

Prototype of a helper that suggests one valid rebooking per itinerary cancelled by the November 2026 Denver snowstorm. Contact center agents review and confirm each suggestion. The goal is under 7 minutes per itinerary, down from about 14, without breaking a single waiver rule.

- [`REBOOKING_SPEC.md`](REBOOKING_SPEC.md): the rules (routing checks, flight filter, party seating, fare treatment, agent confirmation), the source of truth for the code
- [`PROMPT_NOTES.md`](PROMPT_NOTES.md): the prompt used to write the spec, plus notes

## Quick start: one command

```bash
./run.sh
```

The first run creates `.venv`, installs the requirements and creates `.env` from `.env.example`. Every run then:

1. runs the unit tests (offline),
2. creates the Supabase tables and loads both CSVs, if Supabase is set in `.env` (otherwise the service reads the CSVs),
3. runs the family-of-four demo: 2 adults + 2 children, the only valid flight has 3 seats together. It prints the suggestion and, child by child, which adult they sit with,
4. runs every booking in the real data (request date 2026-11-18) and prints the summary.

To try the API afterwards: `./run.sh serve`, then open http://127.0.0.1:8000/docs.

Needs Python 3.11+ (developed on 3.15). Without any keys it still runs end to end: the model step falls back to the code choice and says so.

## Settings (`.env`)

`.env` is git-ignored; never commit it. [`.env.example`](.env.example) lists every setting.

| Setting | What |
|---|---|
| `OPENROUTER_API_KEY` | OpenRouter key. Without it, every suggestion uses the code choice. |
| `OPENROUTER_MODEL` | Any OpenRouter model ID. Empty = `nvidia/nemotron-3-ultra-550b-a55b:free` (free). |
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | Supabase project. Server-side only. Without them the service reads `data/*.csv`. |
| `SUPABASE_DB_URL` | Optional Postgres connection string. Lets `./run.sh` create the tables itself (needs `psql`). |
| `REQUEST_DATE` | Date the rebooking request is made, for check R1. Empty = today. `.env.example` sets 2026-11-18, because after 23 Nov 2026 every booking goes to Revenue Management. `?request_date=` on the API overrides it. |

### Free model limits

A free OpenRouter key gets a small daily allowance of free-model requests (about 50; OpenRouter's limit error says 10 credits unlock 1,000 a day). One full run needs about 118 (one per booking with a suggestion). So:

- Model replies are cached in `.cache/ai_replies.json`, keyed by model and the exact prompt (which includes the flights and open seats). Re-runs reuse them and spend nothing.
- When the daily limit is hit, the service logs it once and uses the code choice for the rest of the day. Every suggestion is still fully rule-checked. The run summary shows how many picks came from the model.
- Reasoning is switched off in the request. Free reasoning models otherwise spend the whole token budget thinking and return no answer.

### Connecting Supabase

1. Create a project at [supabase.com](https://supabase.com) (the free plan is enough).
2. Put three values in `.env`:
   - `SUPABASE_URL`: Project Settings → API → Project URL
   - `SUPABASE_SERVICE_ROLE_KEY`: Project Settings → API Keys → `service_role` (or a secret key, `sb_secret_...`)
   - `SUPABASE_DB_URL`: the **Connect** button → Session pooler connection string, with your database password filled in
3. Run `./run.sh`. Step 2 creates the tables from [`db/schema.sql`](db/schema.sql) and loads 140 bookings, 153 flights and 342 passenger rows, then reads the counts back.

Without `SUPABASE_DB_URL`, paste `db/schema.sql` into the Supabase SQL editor once instead. The service then reads from Supabase automatically.

## How a suggestion is made

| Step | Who | What |
|---|---|---|
| 1 | code | Routing checks R1–R4 ([`app/rules.py`](app/rules.py)). Revenue Management cases get a reason, no suggestion. |
| 2 | code | Valid options: the flight filter, then "together" options, or safe splits that keep every child beside an adult ([`app/options.py`](app/options.py)). |
| 3 | AI | The model (via OpenRouter) picks **one** option by ID and writes a one-line reason. It answers in JSON and never sees a way to add a flight ([`app/ai.py`](app/ai.py)). |
| 4 | code | The pick is re-checked against every rule. A malformed, unknown or failing pick falls back to the best option by code and is logged ([`app/service.py`](app/service.py)). |
| 5 | code | Fare result, `STORM WAIVER DEN NOV26` documentation line, split notes ([`app/fares.py`](app/fares.py)). |

## API

`GET /suggestions` (every booking) and `GET /suggestions/{booking_id}`. Both take `request_date` and `use_ai` (`false` skips the model). Each response includes:

- `suggestion.flights[]`: flight, times, status, weather risk, `seated_together` (the adjacent block) and `seated_apart`
- `path`: `waiver`, `non_covered` or `revenue_management`
- `status`: `suggested`, `no_suggestion` (flagged for the agent, with `message` saying why) or `revenue_management`
- `fare`: `result` ("no fare difference" / "collect $X") and `detail` with bulletin clauses
- `checklist[]`: every rule checked, with pass/fail and detail
- `ai`: model, one-line reason, and whether code fell back (and why)
- `family_must_agree`: true for every split
- `documentation_lines`, `split_notes`, `agent_context` (agent note, onward connection, bags, wheelchair, ...)

## Repo layout

```
run.sh         the one command
app/
  config.py    settings from .env
  models.py    Booking, Flight, Passenger, Party, Option, Check
  party.py     who is an adult / child / lap infant (from agent_note + travels_with_infant)
  rules.py     routing checks, flight filter, final re-check -> checklist
  options.py   together options and safe splits
  fares.py     fare result, documentation lines, split notes
  ai.py        OpenRouter call, reply cache, strict parsing of the model's pick
  service.py   runs the five steps for each booking
  summary.py   counts and safety checks over a batch
  render.py    text view of one suggestion
  db.py        Supabase reads (or the CSVs when Supabase isn't configured)
  main.py      FastAPI endpoints
db/schema.sql  tables: bookings, passengers, flights
scripts/       seed.py (Supabase), demo_family.py, run_summary.py
data/          the two scenario CSVs
tests/         unit tests, family-of-four demo, end-to-end run
```

Individual steps, if you need them: `.venv/bin/python -m pytest`, `.venv/bin/python -m scripts.seed`, `.venv/bin/python -m scripts.demo_family`, `.venv/bin/python -m scripts.run_summary --show BKG-10018` (or `--no-ai`, `--show-splits`).

## Results on the real data (request date 2026-11-18)

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
- The free model's daily limit means a key without credits covers roughly 50 bookings a day with model picks; the rest use the code choice until the cache fills.
