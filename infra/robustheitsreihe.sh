#!/usr/bin/env bash
# Robustheitsprobe auf der EU-Mess-VM: echte Aufnahmen (agent/fixtures/robust, gitignored),
# jede in eigener Sitzung, fuer mehrere STT-Segmentierungswerte. Zwei Durchgaenge mit
# umgekehrter Reihenfolge der Werte (gegenbalanciert).
#
# Aufruf (aus dem Repo-Root, im Hintergrund):
#   setsid nohup bash infra/robustheitsreihe.sh > experiments/runs/robust/reihe.log 2>&1 < /dev/null &
#
# Ergebnisse: experiments/runs/robust/ (Metriken, manifests/, turns/, transcripts/) --
# getrennt von den Latenzlaeufen. Aufnahmeliste und Einwilligung:
# docs/phase-0-robustheitsprobe-aufnahmen.md
set -euo pipefail

cd "$(dirname "$0")/.."
UV="${UV:-$HOME/.local/bin/uv}"
CLIPS="${CLIPS:-R01,R02,R03,R04,R05,R06,R07,R08,R09,R10,R11,R12,R13,R14,R15,R16,R17,R18,R19,R20,R21,S01,S02,S03,S04,S05}"
DEPLOYMENT="${DEPLOYMENT:-gpt-4.1-nano}"
mkdir -p experiments/runs/robust

for pass in 1 2; do
  if (( pass == 1 )); then order=(100 200 300); else order=(300 200 100); fi
  for seg in "${order[@]}"; do
    echo "=== $(date -u +%H:%M:%S) Durchgang $pass, Segmentierung $seg ms"
    (cd agent && PACEMAKER_RUNS_DIR=experiments/runs/robust AZURE_STT_SEGMENTATION_MS="$seg" \
      AZURE_OPENAI_DEPLOYMENT="$DEPLOYMENT" "$UV" run python -m pacemaker_agent.tests.synthetic_caller \
      --fixtures fixtures/robust --clips "$CLIPS" --fresh) \
      > "experiments/runs/robust/durchgang${pass}-seg${seg}.log" 2>&1 || echo "!!! fehlgeschlagen"
    grep -ac "Turn-Bilanz" "experiments/runs/robust/durchgang${pass}-seg${seg}.log" | sed 's/^/    Sitzungen: /'
  done
done
echo "=== $(date -u +%H:%M:%S) Robustheitsreihe fertig"
