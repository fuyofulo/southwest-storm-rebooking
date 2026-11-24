#!/usr/bin/env bash
# One command to set up, test and demo the rebooking helper.
#
#   ./run.sh          set up (first time), run the tests, load Supabase if configured,
#                     run the family-of-four demo and the end-to-end run over the real data
#   ./run.sh serve    start the API on http://127.0.0.1:8000 (docs at /docs)
set -euo pipefail
cd "$(dirname "$0")"

step() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }

# --- setup (only does work the first time, or when requirements.txt changes)
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example. Add OPENROUTER_API_KEY (and Supabase settings) to use the AI model and the database."
fi
if [ ! -x .venv/bin/python ]; then
  step "Creating virtualenv"
  python3 -m venv .venv
fi
if [ ! -f .venv/.installed ] || [ requirements.txt -nt .venv/.installed ]; then
  step "Installing dependencies"
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q -r requirements.txt
  touch .venv/.installed
fi
PY=.venv/bin/python

if [ "${1:-}" = "serve" ]; then
  step "Starting the API: http://127.0.0.1:8000/docs  (Ctrl+C to stop)"
  exec .venv/bin/uvicorn app.main:app --port 8000
fi

step "1/4  Unit tests (offline)"
$PY -m pytest -q

step "2/4  Supabase"
if $PY -c "from app.config import get_settings; raise SystemExit(0 if get_settings().use_supabase else 1)"; then
  $PY -m scripts.seed
else
  echo "Skipped: SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set in .env, so the service reads the CSVs in data/."
fi

step "3/4  Family of four, only three seats together (real model if OPENROUTER_API_KEY is set)"
$PY -m scripts.demo_family

step "4/4  End-to-end over the real data, request date 2026-11-18"
$PY -m scripts.run_summary --show BKG-10018 BKG-10029

step "All done. To try the API:  ./run.sh serve   then open http://127.0.0.1:8000/docs"
