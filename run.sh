#!/usr/bin/env bash
# One command to set up, test and demo the rebooking helper.
#
#   ./run.sh          set up (first time), run the tests, load Supabase if configured,
#                     run the family-of-four demo and the end-to-end run over the real data
#   ./run.sh app      start the service AND the agent page: open http://localhost:5173
#   ./run.sh serve    start only the service on http://127.0.0.1:8000 (docs at /docs)
#   ./run.sh page     start only the agent page (needs the service running)
#   ./run.sh reset    clear every agent confirmation, so all bookings are waiting again
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

web_deps() {
  if ! command -v npm >/dev/null; then
    echo "The agent page needs Node.js 20+ (npm). Install it from https://nodejs.org and run this again." >&2
    exit 1
  fi
  if [ ! -d web/node_modules ] || [ web/package.json -nt web/node_modules ]; then
    step "Installing the agent page's dependencies"
    (cd web && npm install --no-audit --no-fund)
    touch web/node_modules
  fi
}

case "${1:-}" in
  serve)
    step "Starting the rebooking service: http://127.0.0.1:8000/docs  (Ctrl+C to stop)"
    exec .venv/bin/uvicorn app.main:app --port 8000
    ;;
  page)
    web_deps
    step "Starting the agent page: http://localhost:5173  (the service must be running: ./run.sh serve)"
    cd web && exec npm run dev
    ;;
  app)
    web_deps
    step "Starting the rebooking service on :8000 and the agent page on :5173  (Ctrl+C stops both)"
    .venv/bin/uvicorn app.main:app --port 8000 &
    API_PID=$!
    trap 'kill $API_PID 2>/dev/null' EXIT INT TERM
    printf '\n    Open http://localhost:5173\n\n'
    (cd web && npm run dev)
    exit 0
    ;;
  reset)
    $PY -m scripts.seed --reset-confirmations
    exit 0
    ;;
esac

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
