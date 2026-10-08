"""Schreibt das Gesprächstranskript eines Laufs als JSON-Lines.

Zweck: Sprache und Rollentreue der Persona pro Stack/Modell nachprüfen können (Latenz
allein sagt nichts darüber, ob ein schnelleres Modell die Persona noch trägt), und das
Phase-0-Muss-Kriterium "Transkript + Timing je Sprecherwechsel, als Datei exportierbar"
(Export: metrics/transcript_export.py).
Gespeist aus den Turn-Events der Context-Aggregatoren, verdrahtet in pipeline.py; Beginn
der Redebeiträge aus TranscriptTimingObserver.

Liegt in einem Unterordner von experiments/runs/, damit metrics/aggregate.py (liest nur
*.jsonl direkt in runs/) die Dateien nicht als Latenzmessungen einliest. Dateiname =
Name der zugehörigen Metrikdatei.

Schema pro Zeile:
  {"ts": ISO8601 (Ende des Redebeitrags bzw. Zeitpunkt des Ereignisses),
   "started_at": ISO8601|null (Nutzer: Sprechbeginn laut VAD; Persona: erstes Audio),
   "stack": str, "llm_model": str, "role": "user"|"assistant"|"event",
   "text": str, "interrupted": bool|null}

`started_at` ist ab 2026-10-08 vorhanden. Bei s2s gibt es kein separates STT: Nutzer-Zeilen
fehlen dann, Bot-Zeilen stammen aus dem Audio-Transkript des Realtime-Modells.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from pipecat.frames.frames import BotStartedSpeakingFrame, UserStartedSpeakingFrame
from pipecat.observers.base_observer import BaseObserver, FramePushed


def _iso(ts: float | None) -> str | None:
    return datetime.fromtimestamp(ts, UTC).isoformat() if ts is not None else None


class TranscriptRecorder:
    def __init__(self, path: Path, *, stack: str, llm_model: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._path = path
        self._stack = stack
        self._llm_model = llm_model
        # Beginn des laufenden Redebeitrags je Rolle (erster Sprechbeginn seit dem letzten
        # Eintrag dieser Rolle)
        self._started: dict[str, float] = {}

    @property
    def path(self) -> Path:
        return self._path

    def note_started(self, role: str, ts: float) -> None:
        self._started.setdefault(role, ts)

    def record(self, *, role: str, text: str, interrupted: bool | None = None) -> None:
        row = {
            "ts": datetime.now(UTC).isoformat(),
            "started_at": _iso(self._started.pop(role, None)),
            "stack": self._stack,
            "llm_model": self._llm_model,
            "role": role,
            "text": text.strip(),
            "interrupted": interrupted,
        }
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


class TranscriptTimingObserver(BaseObserver):
    """Meldet dem Transkript den Beginn von Nutzer- und Persona-Redebeiträgen."""

    def __init__(self, transcript: TranscriptRecorder) -> None:
        super().__init__()
        self._transcript = transcript
        self._seen: set[int] = set()

    async def on_push_frame(self, data: FramePushed) -> None:
        frame = data.frame
        if not isinstance(frame, UserStartedSpeakingFrame | BotStartedSpeakingFrame):
            return
        if frame.id in self._seen:
            return
        self._seen.add(frame.id)
        now = datetime.now(UTC).timestamp()
        role = "user" if isinstance(frame, UserStartedSpeakingFrame) else "assistant"
        self._transcript.note_started(role, now)
