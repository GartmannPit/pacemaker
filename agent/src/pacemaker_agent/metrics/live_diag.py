"""Diagnose: wann kommt GPT-Live-Audio vom Server an? (Schalter PACEMAKER_LIVE_DIAG=1)

Hintergrund (2026-10-15): Im ersten VM-Vorlauf kam der Text der Persona 250-800 ms vor ihrem
Audio am Ausgabe-Transport an. Je Server-Ereignis werden hier Unix-Zeitstempel festgehalten,
um Server-Zeit von Pipeline-Puffern zu trennen:

- audio: jedes Audio-Delta mit Laenge (ms) und ob es Stille ist (Pipecats is_silence)
- text:  jedes Transkript-Delta mit Rolle

Ausgabe: <RUNS_DIR>/live_diag/<run_id>.jsonl, eine Zeile je Ereignis.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import time

from loguru import logger
from pipecat.audio.utils import is_silence

from .collector import RUNS_DIR


def enabled() -> bool:
    return os.environ.get("PACEMAKER_LIVE_DIAG", "0") == "1"


def instrument(base: type, run_id: str) -> type:
    """Unterklasse eines Pipecat-OpenAILiveLLMService mit Zeitstempeln je Server-Ereignis."""
    path = RUNS_DIR / "live_diag" / f"{run_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"Live-Diagnose aktiv -> {path}")

    def write(row: dict) -> None:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    class DiagOpenAILiveLLMService(base):
        async def _handle_evt_audio_delta(self, evt):
            try:
                audio = base64.b64decode(evt.delta)
                await asyncio.to_thread(
                    write,
                    {
                        "t": time.time(),
                        "art": "audio",
                        "ms": round(len(audio) / 2 / 24, 1),  # PCM16 mono 24 kHz
                        "still": bool(is_silence(audio)),
                    },
                )
            except Exception as exc:  # noqa: BLE001 -- Diagnose darf nie stoeren
                logger.warning(f"Live-Diagnose: Audio-Eintrag verworfen ({exc!r:.120})")
            return await super()._handle_evt_audio_delta(evt)

        async def _handle_evt_transcript_delta(self, evt):
            if evt.delta:
                await asyncio.to_thread(
                    write, {"t": time.time(), "art": "text", "rolle": evt.role, "text": evt.delta}
                )
            return await super()._handle_evt_transcript_delta(evt)

    return DiagOpenAILiveLLMService
