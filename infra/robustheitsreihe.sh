#!/usr/bin/env bash
# Robustheitsprobe auf der EU-Mess-VM: echte Aufnahmen (agent/fixtures/robust, gitignored),
# jede in eigener Sitzung, fuer mehrere Werte EINER Stellschraube. Zwei Durchgaenge mit
# umgekehrter Reihenfolge der Werte (gegenbalanciert).
#
# Aufruf (aus dem Repo-Root, im Hintergrund), z. B. VAD-Stopp-Kurve:
#   PARAM=PACEMAKER_VAD_STOP_SECS VALUES="0.2 0.4 0.6" OUT=experiments/runs/robust-vad \
#     setsid nohup bash infra/robustheitsreihe.sh > /tmp/reihe.log 2>&1 < /dev/null &
# Default (Segmentierungsreihe vom 2026-10-08):
#   PARAM=AZURE_STT_SEGMENTATION_MS VALUES="100 200 300" OUT=experiments/runs/robust
#
# Ergebnisse unter $OUT (Metriken, manifests/, turns/, transcripts/) -- getrennt von den
# Latenzlaeufen. Auswertung: uv run python -m pacemaker_agent.metrics.robustness $OUT
# Aufnahmeliste und Einwilligung: docs/phase-0-robustheitsprobe-aufnahmen.md
set -euo pipefail

cd "$(dirname "$0")/.."
UV="${UV:-$HOME/.local/bin/uv}"
CLIPS="${CLIPS:-R01,R02,R03,R04,R05,R06,R07,R08,R09,R10,R11,R12,R13,R14,R15,R16,R17,R18,R19,R20,R21,S01,S02,S03,S04,S05}"
DEPLOYMENT="${DEPLOYMENT:-gpt-4.1-nano}"
PARAM="${PARAM:-AZURE_STT_SEGMENTATION_MS}"
read -r -a VALS <<< "${VALUES:-100 200 300}"
OUT="${OUT:-experiments/runs/robust}"
mkdir -p "$OUT"

for pass in 1 2; do
  order=("${VALS[@]}")
  if (( pass == 2 )); then
    for (( i=${#VALS[@]}-1, j=0; i>=0; i--, j++ )); do order[j]="${VALS[i]}"; done
  fi
  for val in "${order[@]}"; do
    log="$OUT/durchgang${pass}-${PARAM}-${val}.log"
    echo "=== $(date -u +%H:%M:%S) Durchgang $pass, $PARAM=$val"
    (cd agent && env PACEMAKER_RUNS_DIR="$OUT" "$PARAM=$val" AZURE_OPENAI_DEPLOYMENT="$DEPLOYMENT" \
      "$UV" run python -m pacemaker_agent.tests.synthetic_caller \
      --fixtures fixtures/robust --clips "$CLIPS" --fresh) > "$log" 2>&1 || echo "!!! fehlgeschlagen"
    grep -ac "Turn-Bilanz" "$log" | sed 's/^/    Sitzungen: /'
  done
done
echo "=== $(date -u +%H:%M:%S) Robustheitsreihe fertig"
