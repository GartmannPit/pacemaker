#!/usr/bin/env bash
# Nur auf der EU-Mess-VM ausfuehren. Praeregistrierung: docs/phase-1-lasttest.md.
# Funktionstest und Reihe sind getrennte, ausdrueckliche Aufrufe; keine Wiederholungen.
set -euo pipefail
cd "$(dirname "$0")/.."
UV="${UV:-$HOME/.local/bin/uv}"
MODE="${1:-}"
case "$MODE" in
  funktionstest) STAGES=(F); COUNTS=(2); TURNS=3; SESSIONS=2 ;;
  reihe) STAGES=(E L5 E L10 E L20 E); COUNTS=(1 5 1 10 1 20 1); TURNS=10; SESSIONS=39 ;;
  *) echo 'Aufruf: bash infra/lasttest.sh funktionstest|reihe' >&2; exit 2 ;;
esac
[[ $# == 1 && $(uname -s) == Linux ]] || { echo 'Genau ein Modus; nur Linux EU-Mess-VM.' >&2; exit 2; }
for tool in setsid timeout vmstat; do command -v "$tool" >/dev/null; done
[[ -x "$UV" ]] || { echo 'UV ist nicht ausfuehrbar.' >&2; exit 2; }
# Pro Aufruf eigener Reihenordner, keine Vermischung mit Funktionstest oder Wiederholungen.
ROOT="$PWD/experiments/runs/lasttest/$(date -u +%Y%m%dT%H%M%S)-$$-$MODE"
mkdir -p "$ROOT"
# Planannahme aus §4; nur eine Kostenschaetzung, keine behauptete Messung.
if [[ "$MODE" == funktionstest ]]; then
  ESTIMATE='ca. 0,15 USD'; MAX_COST='ca. 0,51 USD'
else
  ESTIMATE='ca. 5,85 USD'; MAX_COST='ca. 9,95 USD'
fi
printf 'Baseline/Referenz, api.openai.com. Geplant: %s Sitzungen, je %s Clips.\n' "$SESSIONS" "$TURNS"
printf 'Kostenschaetzung (§4): %s. Harte Grenze: 300 s + 5 s Kill-Frist je Anrufer (max. ca. 0,255 USD/Sitzung, Backend zusaetzlich).\n' "$ESTIMATE"
printf 'Sitzungsbudget bei Zeitgrenze: %s fuer diesen Aufruf, Backend zusaetzlich.\n' "$MAX_COST"
printf 'Ergebnisse: %s\n' "$ROOT"
GROUPS_TO_STOP=()
VMSTAT_PID=''
cleanup() {
  local rc=$?
  set +u  # Bash 3 behandelt auch initialisierte leere Arrays unter nounset als ungesetzt.
  trap - EXIT INT TERM
  if [[ -n "$VMSTAT_PID" ]]; then kill "$VMSTAT_PID" 2>/dev/null || true; fi
  for pid in "${GROUPS_TO_STOP[@]}"; do kill -TERM -- "-$pid" 2>/dev/null || true; done
  if ((${#GROUPS_TO_STOP[@]})); then
    sleep 2
    for pid in "${GROUPS_TO_STOP[@]}"; do kill -KILL -- "-$pid" 2>/dev/null || true; done
  fi
  wait 2>/dev/null || true
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
rtt() {
  bash infra/rtt-check.sh 10 live | sed "s/}\$/,\"phase\":\"$1\",\"run\":\"$2\"}/" >> "$3/rtt.jsonl"
}
SKIP_HIGHER=''
for ((block=0; block<${#STAGES[@]}; block++)); do
  stage="${STAGES[block]}"; count="${COUNTS[block]}"
  # Scheitert eine Laststufe an Dienstfehlern, entfallen alle hoeheren Laststufen (§5).
  if [[ "$stage" == L* && -n "$SKIP_HIGHER" ]]; then
    printf '{"stage":"%s","reason":"mehr_als_2_Dienstfehler_in_%s"}\n' "$stage" "$SKIP_HIGHER" >> "$ROOT/skipped.jsonl"
    continue
  fi
  if ((block > 0)); then sleep 30; fi
  dir="$ROOT/$((block+1))-$stage"
  mkdir -p "$dir"
  printf '{"mode":"%s","stage":"%s","callers":%s,"turns":%s}\n' "$MODE" "$stage" "$count" "$TURNS" > "$dir/block.json"
  rtt vorher "$stage" "$dir"
  vmstat -w 1 > "$dir/vmstat.log" &
  VMSTAT_PID=$!
  GROUPS_TO_STOP=()
  for ((caller=1; caller<=count; caller++)); do
    # Schlaf je Prozess statt kumulativ: alle starten innerhalb derselben 0–3 s.
    offset=$((RANDOM % 4))
    setsid bash -c '
      sleep "$1"
      cd agent
      exec env PACEMAKER_RUNS_DIR="$2" PACEMAKER_LOAD_CONCURRENCY="$3" \
        PACEMAKER_LOAD_CALLER="$4" OPENAI_LIVE_REGION=referenz \
        OPENAI_LIVE_BACKEND_MODEL=gpt-4.1-mini PACEMAKER_LIVE_DIAG=1 \
        timeout --signal=TERM --kill-after=5s 300 "$5" run --offline --no-sync \
        python -m pacemaker_agent.tests.synthetic_caller --stack live --turns "$6" \
        --no-service-retries
    ' lasttest "$offset" "$dir" "$count" "$caller" "$UV" "$TURNS" > "$dir/caller-$caller.log" 2>&1 &
    GROUPS_TO_STOP+=("$!")
  done
  for ((i=0; i<${#GROUPS_TO_STOP[@]}; i++)); do
    rc=0
    wait "${GROUPS_TO_STOP[i]}" || rc=$?
    printf '{"caller":%s,"exit_code":%s}\n' "$((i+1))" "$rc" >> "$dir/callers.jsonl"
  done
  # Auch eventuell uebrig gebliebene Kinder bereits beendeter Wrapper beseitigen.
  for pid in "${GROUPS_TO_STOP[@]}"; do kill -KILL -- "-$pid" 2>/dev/null || true; done
  GROUPS_TO_STOP=()
  kill "$VMSTAT_PID" 2>/dev/null || true
  wait "$VMSTAT_PID" 2>/dev/null || true
  VMSTAT_PID=''
  rtt nachher "$stage" "$dir"
  health=$(cd agent && "$UV" run --offline --no-sync python -m pacemaker_agent.metrics.load_aggregate "$dir" --check-block)
  printf '%s\n' "$health" > "$dir/health.json"
  # Nur lokale Protokolle auswerten; keine Wiederholung, auch nicht bei Dienstfehlern.
  decision=$(printf '%s' "$health" | "$PWD/agent/.venv/bin/python" -c '
import json, sys
h = json.load(sys.stdin)
print("skip" if h["service_error_sessions"] > 2 else "ok" if h["complete"] else "stop")')
  if [[ "$MODE" == funktionstest && ( "$decision" != ok || "$health" != *'"service_error_sessions": 0'* ) ]]; then
    echo 'Funktionstest fehlerhaft; Ursache beheben und Funktionstest vor der Reihe wiederholen (§5).' >&2; exit 1
  fi
  if [[ "$stage" == L* && "$decision" == skip ]]; then SKIP_HIGHER="$stage"
  elif [[ "$decision" == stop || "$decision" == skip ]]; then
    echo 'Block unvollstaendig/fehlerhaft; Reihe beendet.' >&2; exit 1
  fi
done
if [[ "$MODE" == reihe ]]; then
  (cd agent && "$UV" run --offline --no-sync python -m pacemaker_agent.metrics.load_aggregate "$ROOT") > "$ROOT/aggregate.json"
else
  echo 'Funktionstest beendet. Verbrauch jetzt in der OpenAI-Konsole (Usage) ablesen; keine Live-TPM aus Sekunden ableiten.'
fi
