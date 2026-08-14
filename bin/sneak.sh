#!/usr/bin/env bash
# sneak.sh — one entry point for every scheduled stage.
#
#   bin/sneak.sh prep      pre-open: universe + previous-day levels
#   bin/sneak.sh stalk     08:45 CT: red opening candles breaking range low
#   bin/sneak.sh strike    09:00 CT: sneaky green candle + R:R + news pull
#   bin/sneak.sh publish   rebuild the dashboard and push to GitHub Pages
#
# Stages are idempotent: re-running one overwrites that session's artifact.
set -uo pipefail
cd "$(dirname "$0")/.."

STAGE="${1:-}"
shift || true
EXTRA=("$@")

log(){ echo "[sneak.sh] $*"; }

ensure_deps(){
  python3 -c "import requests, pandas_market_calendars" 2>/dev/null && return 0
  log "installing dependencies…"
  pip install -q --break-system-packages -r requirements.txt 2>&1 | tail -2
}

trading_day_guard(){
  python3 - <<'PY' || exit 9
import sys
sys.path.insert(0, "sneak")
try:
    from market_calendar import is_trading_day
except Exception as e:
    print(f"[guard] calendar unavailable ({e}); proceeding"); sys.exit(0)
if not is_trading_day():
    print("[guard] NYSE is closed today — nothing to scan."); sys.exit(9)
print("[guard] trading day confirmed")
PY
}

publish(){
  python3 -m sneak.dashboard "${EXTRA[@]}" || return 1
  git add -A docs data/cache data/universe.txt >/dev/null 2>&1
  if git diff --cached --quiet; then log "nothing to commit"; return 0; fi
  git -c user.name="sneak-bot" -c user.email="sneak@users.noreply.github.com" \
      -c commit.gpgsign=false commit -q -m "🥷 SNEAK $(date -u +%Y-%m-%d) — ${STAGE}"
  for i in 1 2 3; do
    git push -q origin HEAD:main && { log "pushed (attempt $i)"; return 0; }
    log "push failed, retrying…"; sleep $((i*4)); git pull --rebase -q origin main || true
  done
  log "PUSH FAILED after 3 attempts"; return 1
}

ensure_deps
case "$STAGE" in
  prep)    trading_day_guard && python3 -m sneak.prep "${EXTRA[@]}" ;;
  stalk)   trading_day_guard && python3 -m sneak.scan_open "${EXTRA[@]}" && publish ;;
  strike)  trading_day_guard && python3 -m sneak.confirm "${EXTRA[@]}" && python3 -m sneak.news "${EXTRA[@]}" ;;
  publish) publish ;;
  *) echo "usage: bin/sneak.sh {prep|stalk|strike|publish} [extra args]"; exit 2 ;;
esac
