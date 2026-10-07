#!/usr/bin/env bash
# Messreihe auf der EU-Mess-VM: mehrere Varianten im Wechsel, Reihenfolge gegenbalanciert
# (Wiederholung 1: A, B, ...; Wiederholung 2: ..., B, A; usw.), damit weder Schwankungen bei
# Azure noch Reihenfolge-Effekte eine Variante bevorzugen. Vor und nach jedem Lauf RTT-Messung.
#
# Aufruf (aus dem Repo-Root, am besten im Hintergrund):
#   nohup bash infra/messreihe.sh 3 \
#     "stille-0=AZURE_OPENAI_DEPLOYMENT=gpt-4.1-nano AZURE_TTS_EDGE_SILENCE_MS=0" \
#     "stille-azure=AZURE_OPENAI_DEPLOYMENT=gpt-4.1-nano AZURE_TTS_EDGE_SILENCE_MS=azure" \
#     > experiments/runs/messreihe.log 2>&1 &
#
# Variante = "<name>=<ENV=WERT ENV=WERT ...>". Die Umgebungsvariablen gelten nur fuer diesen
# Lauf; das Run-Manifest haelt die tatsaechlich wirksame Konfiguration fest.
#
# Ergebnisse: experiments/runs/ (Metriken, manifests/, turns/, transcripts/),
# experiments/runs/rtt/<datum>-rtt.jsonl (RTT je Lauf, Felder "phase" und "run").
set -euo pipefail

REPS="${1:?Anzahl Wiederholungen fehlt}"
shift
[[ $# -ge 1 ]] || { echo "Mindestens eine Variante angeben" >&2; exit 1; }
VARIANTS=("$@")

cd "$(dirname "$0")/.."
UV="${UV:-$HOME/.local/bin/uv}"
RUNS="experiments/runs"
RTT_LOG="$RUNS/rtt/$(date -u +%Y-%m-%d)-rtt.jsonl"  # eigener Ordner: aggregate.py liest alle *.jsonl in runs/
mkdir -p "$RUNS/rtt"

rtt() {
  bash infra/rtt-check.sh 10 2>/dev/null | sed "s/}\$/,\"phase\":\"$1\",\"run\":\"$2\"}/" >> "$RTT_LOG"
}

for rep in $(seq 1 "$REPS"); do
  order=("${VARIANTS[@]}")
  if (( rep % 2 == 0 )); then
    for (( i=${#VARIANTS[@]}-1, j=0; i>=0; i--, j++ )); do order[j]="${VARIANTS[i]}"; done
  fi
  for variant in "${order[@]}"; do
    name="${variant%%=*}"
    envspec="${variant#*=}"
    run="${name}-${rep}"
    echo "=== $(date -u +%H:%M:%S) Start $run ($envspec)"
    rtt vorher "$run"
    # shellcheck disable=SC2086  # envspec bewusst als mehrere ENV=WERT-Paare aufsplitten
    (cd agent && env $envspec "$UV" run python -m pacemaker_agent.tests.synthetic_caller \
      --stack azure-eu --turns 30) \
      > "$RUNS/$(date -u +%Y-%m-%d)-${run}.log" 2>&1 || echo "!!! $run fehlgeschlagen"
    rtt nachher "$run"
    grep -a "Turn-Bilanz\|Fertig. Lauf" "$RUNS/$(date -u +%Y-%m-%d)-${run}.log" | sed 's/.*- /    /' || true
  done
done
echo "=== $(date -u +%H:%M:%S) Messreihe fertig"
