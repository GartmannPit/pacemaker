#!/usr/bin/env bash
# Netzwerk-RTT zu den Azure-Endpoints des azure-eu-Stacks messen.
# Zweck: abschaetzen, wie viel eine Migration auf die EU-Mess-VM an E2E-Latenz einspart.
# Gemessen wird der TCP-Handshake (~1 RTT) und der TLS-Handshake, ohne Authentifizierung.
#
# Aufruf (aus dem Repo-Root):  bash infra/rtt-check.sh [anzahl_samples]
# Ausgabe: eine JSON-Zeile pro Host mit Medianen in ms, z. B. umleiten nach
#   experiments/runs/<datum>-rtt-<geraet>.jsonl
set -euo pipefail

SAMPLES="${1:-20}"
ENV_FILE="$(dirname "$0")/../agent/.env"

region="germanywestcentral"
openai_host=""
if [[ -f "$ENV_FILE" ]]; then
  region="$(grep -E '^AZURE_SPEECH_REGION=' "$ENV_FILE" | cut -d= -f2- || true)"
  region="${region:-germanywestcentral}"
  openai_host="$(grep -E '^AZURE_OPENAI_ENDPOINT=' "$ENV_FILE" | cut -d= -f2- | sed -E 's#^https?://##; s#/.*$##' || true)"
fi
openai_host="${AZURE_OPENAI_HOST:-$openai_host}"

hosts=("$region.stt.speech.microsoft.com" "$region.tts.speech.microsoft.com")
if [[ -n "$openai_host" ]]; then
  hosts+=("$openai_host")
else
  echo "Hinweis: kein AZURE_OPENAI_ENDPOINT in agent/.env und kein AZURE_OPENAI_HOST gesetzt -- LLM-Endpoint wird uebersprungen." >&2
fi

median() { sort -n | awk '{a[NR]=$1} END {if (NR%2) print a[(NR+1)/2]; else print (a[NR/2]+a[NR/2+1])/2}'; }

for host in "${hosts[@]}"; do
  tcp=(); tls=()
  for _ in $(seq 1 "$SAMPLES"); do
    read -r dns conn app < <(curl -s -o /dev/null --max-time 10 \
      -w '%{time_namelookup} %{time_connect} %{time_appconnect}\n' "https://$host/" || echo "0 0 0")
    tcp+=("$(awk -v a="$conn" -v b="$dns" 'BEGIN {printf "%.1f", (a-b)*1000}')")
    tls+=("$(awk -v a="$app" -v b="$conn" 'BEGIN {printf "%.1f", (a-b)*1000}')")
  done
  tcp_p50="$(printf '%s\n' "${tcp[@]}" | median)"
  tls_p50="$(printf '%s\n' "${tls[@]}" | median)"
  printf '{"ts":"%s","device":"%s","host":"%s","samples":%s,"tcp_rtt_ms_p50":%s,"tls_handshake_ms_p50":%s}\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(hostname)" "$host" "$SAMPLES" "$tcp_p50" "$tls_p50"
done
