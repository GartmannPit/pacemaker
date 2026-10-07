"""Turn-Protokoll: genau ein Endstatus und alle Zeitpunkte je angebotener Aeusserung.

Grund (2026-10-07): Der Metrik-Collector schreibt nur, wenn Bot-Audio beginnt. Ausfaelle
(stumme Persona, zerfallene Turns, Abbrueche) fielen still aus den Quantilen. Ausserdem
endet die E2E-Messung beim ersten Audio, oft beim kurzen Einstieg ("Hm, nee."), und sagt
nichts darueber, wann der eigentliche Inhalt kommt.

Der Synthetic Caller meldet je Clip `begin()` (Fenster beginnt) und `set_speech_end()`.
Alle Pipeline-Ereignisse bis zum naechsten `begin()` gehoeren zu dieser Aeusserung.

Zeitpunkte je Aeusserung (Unix-Zeit, im Protokoll als ms ab Sprechende):
- speech_end_clip: letzter hoerbarer Frame des Clips beim Einspeisen (Referenz unabhaengig
  von der VAD)
- speech_end_vad:  VAD-Erkennung minus stop_secs -- dieselbe Basis wie Pipecats
  UserBotLatencyObserver und damit wie `e2e_ms` im Collector
- turn_end:        Turn-Erkennung meldet Ende (UserStoppedSpeakingFrame)
- first_text:      erstes nicht-leeres LLM-Textdelta
- first_audio:     erstes Bot-Audio (BotStartedSpeakingFrame)
- main_sentence:   Hoerbeginn des ersten Worts nach dem ersten Satzende (Hilfsmetrik
  "Beginn des Hauptsatzes"; ob das inhaltlich relevant ist, bleibt manuelle Bewertung)

Ablage: experiments/runs/turns/<run_id>.jsonl
"""

from __future__ import annotations

import json
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path

from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    ErrorFrame,
    InterruptionFrame,
    LLMTextFrame,
    TTSTextFrame,
    UserStoppedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.observers.base_observer import BaseObserver, FramePushed
from pipecat.processors.frame_processor import FrameDirection
from pipecat.transports.base_output import BaseOutputTransport

from .collector import RUNS_DIR

TURNS_DIR = RUNS_DIR / "turns"

STATUSES = (
    "beantwortet",
    "abgebrochen",  # Bot-Antwort wurde unterbrochen
    "zerfallen",  # ein Clip ergab mehrere Turns
    "keine_turn_erkennung",  # kein Turn-Ende erkannt
    "audiofehler",  # Turn erkannt, kein Bot-Audio, Fehler gemeldet
    "keine_antwort",  # Turn erkannt, kein Bot-Audio, kein Fehler
)

_SENTENCE_END = (".", "?", "!")


@dataclass
class UtteranceEvents:
    utterance_id: int
    clip: str
    window_start: float
    speech_end_clip: float | None = None
    speech_end_vad: list[float] = field(default_factory=list)
    turn_ends: list[float] = field(default_factory=list)
    text_deltas: list[float] = field(default_factory=list)
    first_audio: float | None = None
    words: list[tuple[float, str]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    interrupted: bool = False


def classify(u: UtteranceEvents) -> str:
    """Genau ein Endstatus je angebotener Aeusserung."""
    if not u.turn_ends:
        return "keine_turn_erkennung"
    if len(u.turn_ends) > 1:
        return "zerfallen"
    if u.first_audio is None:
        return "audiofehler" if u.errors else "keine_antwort"
    if u.interrupted:
        return "abgebrochen"
    return "beantwortet"


def main_sentence_start(words: list[tuple[float, str]]) -> tuple[float | None, str]:
    """Hoerbeginn des ersten Worts nach dem ersten Satzende und der Text davor."""
    for i, (_, word) in enumerate(words[:-1]):
        if word.rstrip().endswith(_SENTENCE_END):
            first_sentence = " ".join(w for _, w in words[: i + 1])
            return words[i + 1][0], first_sentence
    return None, " ".join(w for _, w in words)


def _ms(later: float | None, earlier: float | None) -> float | None:
    if later is None or earlier is None:
        return None
    return round((later - earlier) * 1000, 1)


def summarize(u: UtteranceEvents) -> dict:
    turn_end = u.turn_ends[0] if u.turn_ends else None
    # VAD-Sprechende: das letzte vor dem (ersten) Turn-Ende
    vad_end = None
    if turn_end is not None:
        before = [t for t in u.speech_end_vad if t <= turn_end]
        vad_end = before[-1] if before else None
    first_text = next((t for t in u.text_deltas if turn_end is None or t >= turn_end), None)
    main_ts, first_sentence = main_sentence_start(u.words)
    return {
        "utterance_id": u.utterance_id,
        "clip": u.clip,
        "status": classify(u),
        "n_turn_ends": len(u.turn_ends),
        "errors": u.errors,
        # ms ab VAD-Sprechende (gleiche Basis wie e2e_ms des Collectors)
        "turn_end_ms": _ms(turn_end, vad_end),
        "first_text_ms": _ms(first_text, vad_end),
        "first_audio_ms": _ms(u.first_audio, vad_end),
        "main_sentence_ms": _ms(main_ts, vad_end),
        # Gegenprobe: ms ab Sprechende laut Clip (unabhaengig von der VAD)
        "first_audio_from_clip_ms": _ms(u.first_audio, u.speech_end_clip),
        "first_sentence": first_sentence,
    }


# Spanne der ersten 10 Textdeltas einer Antwort. Gepuffert (Azure-Inhaltsfilter im
# Default-Modus) kommt alles in einem Schub (Direktmessung: ~0,2 ms Abstand, < 5 ms
# Spanne); gestreamt verteilen sich die Deltas ueber Dutzende ms. Einzelne Abstaende
# taugen nicht als Kriterium: auch gestreamte Deltas kommen oft gebuendelt an
# (Smoke-Test 2026-10-07: Median-Abstand 0,7 ms bei aktivem asynchronem Filter).
_BUFFERED_SPAN_MS = 15.0


def text_delivery(utterances: list[UtteranceEvents]) -> dict:
    """Beobachteter LLM-Auslieferungsmodus: gepuffert oder streamend."""
    spans = [
        (u.text_deltas[min(9, len(u.text_deltas) - 1)] - u.text_deltas[0]) * 1000
        for u in utterances
        if len(u.text_deltas) >= 5
    ]
    if not spans:
        return {"text_delivery": "unbekannt", "median_delta_span_ms": None}
    median = statistics.median(spans)
    return {
        "text_delivery": "gepuffert" if median < _BUFFERED_SPAN_MS else "streamend",
        "median_delta_span_ms": round(median, 1),
    }


class TurnLedger(BaseObserver):
    """Sammelt Pipeline-Ereignisse und ordnet sie der aktuellen Aeusserung zu."""

    def __init__(self) -> None:
        super().__init__()
        self._utterances: list[UtteranceEvents] = []
        self._seen: set[int] = set()
        self._bot_speaking = False

    @property
    def utterances(self) -> list[UtteranceEvents]:
        return self._utterances

    def begin(self, utterance_id: int, clip: str) -> None:
        self._utterances.append(
            UtteranceEvents(utterance_id=utterance_id, clip=clip, window_start=time.time())
        )

    def set_speech_end(self, utterance_id: int, ts: float | None) -> None:
        for u in self._utterances:
            if u.utterance_id == utterance_id:
                u.speech_end_clip = ts

    def _first_sight(self, data: FramePushed) -> bool:
        if data.frame.id in self._seen:
            return False
        self._seen.add(data.frame.id)
        return True

    async def on_push_frame(self, data: FramePushed) -> None:
        if not self._utterances:
            return
        u = self._utterances[-1]
        frame = data.frame
        now = time.time()

        if isinstance(frame, TTSTextFrame):
            # Hoerbeginn: Text-Frames, die der Output-Transport im Abspieltakt freigibt
            if isinstance(data.source, BaseOutputTransport) and self._first_sight(data):
                u.words.append((now, frame.text))
            return
        # Pipecat broadcastet Turn-, Bot- und Unterbrechungs-Ereignisse in beide
        # Richtungen als zwei Frames mit eigener ID -- nur die Downstream-Kopie zaehlen
        # (sonst ergibt jeder Clip zwei Turn-Enden, Smoke-Test 2026-10-07). Fehler
        # laufen meist upstream und werden in beiden Richtungen erfasst.
        if not isinstance(frame, ErrorFrame) and data.direction != FrameDirection.DOWNSTREAM:
            return
        if not isinstance(
            frame,
            (
                VADUserStoppedSpeakingFrame,
                UserStoppedSpeakingFrame,
                LLMTextFrame,
                BotStartedSpeakingFrame,
                BotStoppedSpeakingFrame,
                ErrorFrame,
                InterruptionFrame,
            ),
        ) or not self._first_sight(data):
            return

        if isinstance(frame, VADUserStoppedSpeakingFrame):
            u.speech_end_vad.append(frame.timestamp - frame.stop_secs)
        elif isinstance(frame, UserStoppedSpeakingFrame):
            u.turn_ends.append(now)
        elif isinstance(frame, LLMTextFrame):
            if frame.text:
                u.text_deltas.append(now)
        elif isinstance(frame, BotStartedSpeakingFrame):
            self._bot_speaking = True
            if u.first_audio is None:
                u.first_audio = now
        elif isinstance(frame, BotStoppedSpeakingFrame):
            self._bot_speaking = False
        elif isinstance(frame, ErrorFrame):
            u.errors.append(str(frame.error)[:200])
        elif isinstance(frame, InterruptionFrame) and self._bot_speaking:
            u.interrupted = True

    def write(self, run_id: str) -> tuple[Path, dict]:
        """Schreibt das Protokoll und liefert die Bilanz fuer das Manifest."""
        TURNS_DIR.mkdir(parents=True, exist_ok=True)
        path = TURNS_DIR / f"{run_id}.jsonl"
        rows = [summarize(u) for u in self._utterances]
        with path.open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        counts = {s: sum(r["status"] == s for r in rows) for s in STATUSES}
        balance = {
            "offered": len(rows),
            "status_counts": counts,
            "error_rate": round(1 - counts["beantwortet"] / len(rows), 3) if rows else None,
            **text_delivery(self._utterances),
        }
        return path, balance
