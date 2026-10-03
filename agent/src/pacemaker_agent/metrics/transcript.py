"""Schreibt das Gesprächstranskript eines Laufs als JSON-Lines.

Zweck: Sprache und Rollentreue der Persona pro Stack/Modell nachprüfen können (Latenz
allein sagt nichts darüber, ob ein schnelleres Modell die Persona noch trägt).
Gespeist aus den Turn-Events der Context-Aggregatoren, verdrahtet in pipeline.py.

Liegt in einem Unterordner von experiments/runs/, damit metrics/aggregate.py (liest nur
*.jsonl direkt in runs/) die Dateien nicht als Latenzmessungen einliest. Dateiname =
Name der zugehörigen Metrikdatei.

Schema pro Zeile:
  {"ts": ISO8601, "stack": str, "llm_model": str, "role": "user"|"assistant",
   "text": str, "interrupted": bool|null}

Bei s2s gibt es kein separates STT: Nutzer-Zeilen fehlen dann, Bot-Zeilen stammen aus
dem Audio-Transkript des Realtime-Modells.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path


class TranscriptRecorder:
    def __init__(self, path: Path, *, stack: str, llm_model: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._path = path
        self._stack = stack
        self._llm_model = llm_model

    @property
    def path(self) -> Path:
        return self._path

    def record(self, *, role: str, text: str, interrupted: bool | None = None) -> None:
        row = {
            "ts": datetime.now(UTC).isoformat(),
            "stack": self._stack,
            "llm_model": self._llm_model,
            "role": role,
            "text": text.strip(),
            "interrupted": interrupted,
        }
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
