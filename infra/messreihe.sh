#!/usr/bin/env bash
# Messreihe auf der EU-Mess-VM: mehrere Deployments abwechselnd (A, B, A, B, ...), damit
# Schwankungen bei Azure beide Seiten gleich treffen. Vor und nach jedem Lauf RTT-Messung.
#
# Aufruf (aus dem Repo-Root, am besten im Hintergrund):
#   nohup bash infra/messreihe.sh 3 gpt-4.1-mini gpt-4.1-nano > experiments/runs/messreihe.log 2>&1 &
#
# Ergebnisse: experiments/runs/*.jsonl (Metriken, Feld llm_model unterscheidet die Deployments),
# experiments/runs/rtt/<datum>-rtt.jsonl (RTT je Lauf, mit Feld "phase": vorher/nachher).
set -euo pipefail

REPS="${1:-3}"
shift || true
MODELS=("${@:-gpt-4.1-mini gpt-4.1-nano}")
[[ ${#MODELS[@]} -eq 1 ]] && read -r -a MODELS <<< "${MODELS[0]}"

cd "$(dirname "$0")/.."
UV="${UV:-$HOME/.local/bin/uv}"
RUNS="experiments/runs"
RTT_LOG="$RUNS/rtt/$(date -u +%Y-%m-%d)-rtt.jsonl"  # eigener Ordner: aggregate.py liest alle *.jsonl in runs/
mkdir -p "$RUNS/rtt"

rtt() {
  bash infra/rtt-check.sh 10 2>/dev/null | sed "s/}\$/,\"phase\":\"$1\",\"run\":\"$2\"}/" >> "$RTT_LOG"
}

for rep in $(seq 1 "$REPS"); do
  for model in "${MODELS[@]}"; do
    run="${model}-${rep}"
    echo "=== $(date -u +%H:%M:%S) Start $run"
    rtt vorher "$run"
    (cd agent && AZURE_OPENAI_DEPLOYMENT="$model" "$UV" run python -m \
      pacemaker_agent.tests.synthetic_caller --stack azure-eu --turns 30) \
      > "$RUNS/$(date -u +%Y-%m-%d)-${run}.log" 2>&1 || echo "!!! $run fehlgeschlagen"
    rtt nachher "$run"
    grep -a "Turn-Bilanz" "$RUNS/$(date -u +%Y-%m-%d)-${run}.log" | sed 's/.*- /    /' || true
  done
done
echo "=== $(date -u +%H:%M:%S) Messreihe fertig"
