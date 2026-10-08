"""Barge-in-Protokoll: wie schnell verstummt die Persona, wenn der Nutzer hineinspricht?

Schreibt je Unterbrechung eine JSON-Zeile nach experiments/runs/bargein/<run_id>.jsonl --
auch im Live-Betrieb (lokales Headset), wo der echte Sprechbeginn unbekannt ist. Geschaetzter
Sprechbeginn = VAD-Erkennung minus `start_secs` (analog zur E2E-Metrik, die das Sprechende als
VAD-Erkennung minus `stop_secs` schaetzt). Die Abweichung dieser Schaetzung vom tatsaechlichen
Beginn wird an synthetischen Faellen mit bekanntem Beginn kalibriert (Testablauf T2).

Zeile: {"vad_ts", "est_onset_ts", "start_secs", "bot_was_speaking", "bot_stop_ts",
        "stop_ms_est"}; `bot_was_speaking=false` = kein Barge-in (Persona schwieg ohnehin).

    uv run python -m pacemaker_agent.metrics.barge_in [<run_id>|--latest]
"""

from __future__ import annotations

import json
import sys
import time

from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    VADUserStartedSpeakingFrame,
)
from pipecat.observers.base_observer import BaseObserver, FramePushed

from .aggregate import quantile
from .collector import RUNS_DIR

BARGE_IN_DIR = RUNS_DIR / "bargein"


class BargeInObserver(BaseObserver):
    def __init__(self, run_id: str) -> None:
        super().__init__()
        self._path = BARGE_IN_DIR / f"{run_id}.jsonl"
        self._seen: set[int] = set()
        self._bot_speaking = False
        self._pending: dict | None = None

    def _write(self, row: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")

    async def on_push_frame(self, data: FramePushed) -> None:
        frame = data.frame
        if frame.id in self._seen:
            return
        if isinstance(frame, BotStartedSpeakingFrame):
            self._seen.add(frame.id)
            self._bot_speaking = True
        elif isinstance(frame, VADUserStartedSpeakingFrame):
            self._seen.add(frame.id)
            row = {
                "vad_ts": frame.timestamp,
                "est_onset_ts": frame.timestamp - frame.start_secs,
                "start_secs": frame.start_secs,
                "bot_was_speaking": self._bot_speaking,
                "bot_stop_ts": None,
                "stop_ms_est": None,
            }
            if self._bot_speaking:
                self._pending = row
            else:
                self._write(row)
        elif isinstance(frame, BotStoppedSpeakingFrame):
            self._seen.add(frame.id)
            self._bot_speaking = False
            if self._pending is not None:
                row, self._pending = self._pending, None
                row["bot_stop_ts"] = time.time()  # Frame traegt keinen Zeitstempel
                row["stop_ms_est"] = round((row["bot_stop_ts"] - row["est_onset_ts"]) * 1000, 1)
                self._write(row)


def main() -> None:
    arg = sys.argv[1] if len(sys.argv) > 1 else "--latest"
    if arg == "--latest":
        files = sorted(BARGE_IN_DIR.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
        if not files:
            raise SystemExit(f"Keine Barge-in-Protokolle in {BARGE_IN_DIR}")
        path = files[-1]
    else:
        path = BARGE_IN_DIR / f"{arg}.jsonl"
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    cuts = [r for r in rows if r["bot_was_speaking"] and r["stop_ms_est"] is not None]
    stops = [r["stop_ms_est"] for r in cuts]
    ok = sum(s <= 300 for s in stops)
    p50, p90 = quantile(stops, 0.5), quantile(stops, 0.9)
    print(f"{path.name}: {len(cuts)} Unterbrechungen, <= 300 ms (geschaetzt): {ok}/{len(cuts)}")
    if stops:
        print(
            f"  Stopp p50 {p50:.0f} / p90 {p90:.0f} ms; einzeln: {sorted(round(s) for s in stops)}"
        )


if __name__ == "__main__":
    main()
