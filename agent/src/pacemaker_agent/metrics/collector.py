"""Schreibt Latenzmetriken pro Turn als JSON-Lines nach experiments/runs/.

Pipecat liefert Metriken ueber MetricsFrame bzw. den Observer-Mechanismus. Welcher
Hook zur installierten Pipecat-Version passt, nach `uv sync` gegen die Quickstart
abgleichen (siehe README). Das JSONL-Schema unten ist die Schnittstelle zu
metrics/aggregate.py und bleibt stabil.

Schema pro Zeile:
  {"ts": ISO8601, "stack": str, "turn": int,
   "e2e_ms": float, "stt_final_ms": float|null,
   "llm_ttft_ms": float|null, "tts_ttfb_ms": float|null}
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

# .../agent/src/pacemaker_agent/metrics/collector.py -> parents[4] == Repo-Wurzel
_REPO_ROOT = Path(__file__).resolve().parents[4]
RUNS_DIR = _REPO_ROOT / "experiments" / "runs"


class MetricsCollector:
    def __init__(self, stack: str, runs_dir: Path | None = None) -> None:
        self.stack = stack
        self._turn = 0
        target = runs_dir or RUNS_DIR
        target.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self._path = target / f"{stamp}-{stack}.jsonl"

    @property
    def path(self) -> Path:
        return self._path

    def record_turn(
        self,
        *,
        e2e_ms: float,
        stt_final_ms: float | None = None,
        llm_ttft_ms: float | None = None,
        tts_ttfb_ms: float | None = None,
    ) -> None:
        self._turn += 1
        row = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "stack": self.stack,
            "turn": self._turn,
            "e2e_ms": round(e2e_ms, 1),
            "stt_final_ms": None if stt_final_ms is None else round(stt_final_ms, 1),
            "llm_ttft_ms": None if llm_ttft_ms is None else round(llm_ttft_ms, 1),
            "tts_ttfb_ms": None if tts_ttfb_ms is None else round(tts_ttfb_ms, 1),
        }
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
