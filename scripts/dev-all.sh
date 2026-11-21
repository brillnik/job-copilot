#!/usr/bin/env bash
# Run the whole Job Copilot stack locally: database, migrations, local AI (Ollama),
# API, web, and the background scheduler. Ctrl-C stops everything this script started.
#
#   scripts/dev-all.sh                 # db + migrate + ollama + api + web + scheduler
#   scripts/dev-all.sh --apply         # also start Chrome (CDP) and the auto-apply worker
#   scripts/dev-all.sh --no-ai         # skip Ollama (e.g. AI_PROVIDER=claude)
#   scripts/dev-all.sh --no-scheduler  # skip discovery/autopilot/gmail cron loop
#   scripts/dev-all.sh --no-db         # DB already running; skip docker + migrations
#   scripts/dev-all.sh --dry-run       # print what would run, start nothing
#
# Env you can override: TAILOR_AGENT (default graph), APPLY_BROWSER_MODE (cdp),
# APPLY_CDP_URL, OLLAMA_URL, API_PORT (8000), WEB_PORT (3000).
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API="$ROOT/apps/api"
LOGDIR="$ROOT/.dev-logs"
API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-3000}"
OLLAMA_URL="${OLLAMA_URL:-http://localhost:11434}"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CHROME_PROFILE="${APPLY_CHROME_USER_DATA_DIR:-$HOME/.job-copilot-chrome}"

WITH_AI=1; WITH_SCHED=1; WITH_DB=1; WITH_APPLY=0; DRY=0
for arg in "$@"; do
  case "$arg" in
    --no-ai) WITH_AI=0 ;;
    --no-scheduler) WITH_SCHED=0 ;;
    --no-db) WITH_DB=0 ;;
    --apply) WITH_APPLY=1 ;;
    --dry-run) DRY=1 ;;
    -h|--help) sed -n '2,15p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg (see --help)"; exit 2 ;;
  esac
done

say() { printf '\033[1;36m[dev-all]\033[0m %s\n' "$*"; }
run() { if [ "$DRY" = 1 ]; then say "would run: $*"; else "$@"; fi; }
need() { command -v "$1" >/dev/null 2>&1 || { echo "missing required tool: $1"; exit 1; }; }

# Only read the one setting we need from the env files; never source them (secrets).
env_value() {
  local key="$1" f v=""
  [ -n "${!key:-}" ] && { echo "${!key}"; return; }
  for f in "$ROOT/.env" "$ROOT/.env.local" "$API/.env"; do
    [ -f "$f" ] && v="$(grep -E "^${key}=" "$f" | tail -1 | cut -d= -f2- | tr -d '"' | tr -d "'")" || true
    [ -n "$v" ] && { echo "$v"; return; }
  done
}

need bun; need uv
[ "$WITH_DB" = 1 ] && need docker
AI_PROVIDER="$(env_value AI_PROVIDER)"; AI_PROVIDER="${AI_PROVIDER:-qwen}"
QWEN_MODEL="$(env_value QWEN_MODEL)"; QWEN_MODEL="${QWEN_MODEL:-qwen3-vl:8b-instruct}"
export TAILOR_AGENT="${TAILOR_AGENT:-graph}"   # the tailoring agent, on by default here

mkdir -p "$LOGDIR"
PIDS=()
cleanup() {
  trap - INT TERM EXIT
  say "stopping…"
  for pid in ${PIDS[@]+"${PIDS[@]}"}; do kill "$pid" 2>/dev/null; done
  sleep 1
  for pid in ${PIDS[@]+"${PIDS[@]}"}; do kill -9 "$pid" 2>/dev/null; done
  pkill -P $$ 2>/dev/null
  exit 0
}
trap cleanup INT TERM EXIT

# prefix each line of a process's output and also keep it in a log file
start() {
  local name="$1"; shift
  if [ "$DRY" = 1 ]; then say "would start $name: $*"; return; fi
  ( "$@" 2>&1 | tee "$LOGDIR/$name.log" | sed -u "s/^/[$name] /" ) &
  PIDS+=($!)
  say "started $name (log: .dev-logs/$name.log)"
}

wait_http() { # url, seconds
  local i; for i in $(seq 1 "$2"); do curl -fs -o /dev/null "$1" && return 0; sleep 1; done; return 1
}

# --- 1. database + object store + migrations ---------------------------------
if [ "$WITH_DB" = 1 ]; then
  say "starting Postgres + MinIO"
  run bash -c "cd '$ROOT' && docker compose up -d --wait postgres minio minio-init"
  say "applying migrations"
  run bash -c "cd '$API' && uv run alembic upgrade head"
fi

# --- 2. local AI --------------------------------------------------------------
if [ "$WITH_AI" = 1 ] && [ "$AI_PROVIDER" = "qwen" ]; then
  if command -v ollama >/dev/null 2>&1; then
    if curl -fs -o /dev/null "$OLLAMA_URL/api/tags"; then
      say "Ollama already running"
    else
      start ollama ollama serve
      [ "$DRY" = 1 ] || wait_http "$OLLAMA_URL/api/tags" 30 || say "warning: Ollama did not come up"
    fi
    if [ "$DRY" = 1 ]; then say "would ensure model $QWEN_MODEL is pulled"
    elif ! ollama list 2>/dev/null | grep -q "^${QWEN_MODEL}"; then
      say "pulling $QWEN_MODEL (first run only; large download)"
      ollama pull "$QWEN_MODEL" || say "warning: model pull failed"
    fi
  else
    say "AI_PROVIDER=qwen but 'ollama' is not installed: resume/job extraction will fail."
    say "install Ollama, or set AI_PROVIDER=claude with ANTHROPIC_API_KEY, or pass --no-ai"
  fi
elif [ "$WITH_AI" = 1 ]; then
  say "AI_PROVIDER=$AI_PROVIDER: using the Anthropic API (needs ANTHROPIC_API_KEY); no local model started"
fi

# --- 3. API + web ---------------------------------------------------------------
start api bash -c "cd '$API' && exec uv run uvicorn app.main:app --reload --port $API_PORT"
start web bash -c "cd '$ROOT/apps/web' && PORT=$WEB_PORT exec bun run dev"

# --- 4. scheduler (discovery, autopilot, digests, gmail) ------------------------
scheduler() {
  cd "$API" || exit 1
  local last_day="" m h now_day
  while true; do
    m="$(date +%M)"; h="$(date +%H)"; now_day="$(date +%F)"; m=$((10#$m)); h=$((10#$h))
    [ $((m % 5)) -eq 0 ]  && uv run python -m app.apply.cli digests || true
    [ $((m % 15)) -eq 0 ] && { uv run python -m app.apply.cli tick || true; uv run python -m app.tasks.gmail || true; }
    if [ "$h" -eq 2 ] && [ "$m" -eq 30 ] && [ "$last_day" != "$now_day" ]; then
      last_day="$now_day"; uv run python -m app.discovery.cli run-daily || true
    fi
    sleep $((60 - 10#$(date +%S)))
  done
}
if [ "$WITH_SCHED" = 1 ]; then
  if [ "$DRY" = 1 ]; then say "would start scheduler: digests /5 min, autopilot tick + gmail /15 min, discovery 02:30"
  else ( scheduler 2>&1 | tee "$LOGDIR/scheduler.log" | sed -u "s/^/[scheduler] /" ) & PIDS+=($!); say "started scheduler"; fi
fi

# --- 5. optional: Chrome (CDP) + auto-apply worker ------------------------------
if [ "$WITH_APPLY" = 1 ]; then
  export APPLY_BROWSER_MODE="${APPLY_BROWSER_MODE:-cdp}"
  export APPLY_CDP_URL="${APPLY_CDP_URL:-http://127.0.0.1:9222}"
  if [ "$APPLY_BROWSER_MODE" = "cdp" ]; then
    if curl -fs -o /dev/null "$APPLY_CDP_URL/json/version"; then say "Chrome (CDP) already running"
    elif [ -x "$CHROME" ]; then
      start chrome "$CHROME" --remote-debugging-port=9222 --user-data-dir="$CHROME_PROFILE" --no-first-run
      [ "$DRY" = 1 ] || wait_http "$APPLY_CDP_URL/json/version" 20 || say "warning: Chrome CDP did not come up"
      say "log in to your job portals in that Chrome window (profile: $CHROME_PROFILE)"
    else say "Google Chrome not found at $CHROME"; fi
  fi
  start apply bash -c "cd '$API' && exec uv run python -m app.apply.worker serve"
fi

# --- ready -------------------------------------------------------------------------
if [ "$DRY" = 1 ]; then say "dry run done"; trap - EXIT; exit 0; fi
if wait_http "http://localhost:$API_PORT/health" 60; then say "API ready:  http://localhost:$API_PORT/docs"; else say "API did not answer /health yet; check .dev-logs/api.log"; fi
say "Web:        http://localhost:$WEB_PORT   (Ctrl-C to stop everything)"
wait
