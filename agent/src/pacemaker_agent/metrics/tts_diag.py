"""Diagnose: wo entsteht die Azure-TTS-Zeit in der Pipeline? (Schalter PACEMAKER_TTS_DIAG=1)

Hintergrund (2026-10-14): Isoliert liefert Azure das erste Audio nach ~30-110 ms, in der
Pipeline misst Pipecat 250-390 ms TTS-TTFB. Je TTS-Anfrage werden hier monotone Zeitstempel und
die SDK-eigenen Latenzwerte festgehalten, um lokale Verzoegerung von Azure-Seite zu trennen:

- ttfb_start: Pipecat startet die TTFB-Uhr (tts_service, vor Kontext-/Textverwaltung)
- run_tts: Pipecat ruft run_tts auf
- sdk_call / sdk_return: speak_ssml_async wird aufgerufen / kehrt zurueck
- first_callback: erster synthesizing-Callback mit Audio (SDK-Thread)
- first_frame: erstes Audio-Frame aus run_tts (Event-Loop)
- loop_lag_max_ms: groesste Verspaetung eines 10-ms-Ticks der Event-Loop bis zum ersten Frame
- sdk_*: SpeechServiceResponse_Synthesis*LatencyMs aus dem Ergebnis (Diagnosewerte; ihre
  Differenzen sind nicht automatisch CPU- oder Codec-Zeit)

Ausgabe: <RUNS_DIR>/tts_diag/<zeit>-<pid>.jsonl, eine Zeile je Anfrage.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from datetime import UTC, datetime

from loguru import logger

from .collector import RUNS_DIR

SDK_LATENCIES = {
    "sdk_first_byte_ms": "SpeechServiceResponse_SynthesisFirstByteLatencyMs",
    "sdk_service_ms": "SpeechServiceResponse_SynthesisServiceLatencyMs",
    "sdk_network_ms": "SpeechServiceResponse_SynthesisNetworkLatencyMs",
    "sdk_connection_ms": "SpeechServiceResponse_SynthesisConnectionLatencyMs",
    "sdk_finish_ms": "SpeechServiceResponse_SynthesisFinishLatencyMs",
}


def enabled() -> bool:
    return os.environ.get("PACEMAKER_TTS_DIAG", "0") == "1"


def instrument(base: type) -> type:
    """Unterklasse eines Pipecat-AzureTTSService mit Messpunkten."""
    import azure.cognitiveservices.speech as speechsdk

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = RUNS_DIR / "tts_diag" / f"{stamp}-{os.getpid()}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = threading.Lock()
    logger.info(f"TTS-Diagnose aktiv -> {path}")

    class DiagAzureTTSService(base):
        _diag_rec: dict | None = None
        _diag_ttfb_start: float | None = None
        _diag_last_end: float | None = None
        _diag_patched = False

        async def start_ttfb_metrics(self):
            self._diag_ttfb_start = time.perf_counter()
            return await super().start_ttfb_metrics()

        def _diag_patch(self) -> None:
            synth = self._speech_synthesizer
            if self._diag_patched or synth is None:
                return
            original = synth.speak_ssml_async

            def wrapped(ssml):
                rec = self._diag_rec
                if rec is not None:
                    rec["sdk_call"] = time.perf_counter()
                result = original(ssml)
                if rec is not None:
                    rec["sdk_return"] = time.perf_counter()
                return result

            synth.speak_ssml_async = wrapped
            self._diag_patched = True

        async def run_tts(self, text, context_id):
            self._diag_patch()
            now = time.perf_counter()
            rec = {
                "text_len": len(text),
                "sample_rate": self.sample_rate,
                "ttfb_start": self._diag_ttfb_start,
                "run_tts": now,
                "idle_s": round(now - self._diag_last_end, 2) if self._diag_last_end else None,
            }
            self._diag_rec = rec
            lag = {"max": 0.0, "stop": False}

            async def watch_loop() -> None:
                while not lag["stop"]:
                    t = time.perf_counter()
                    await asyncio.sleep(0.01)
                    lag["max"] = max(lag["max"], time.perf_counter() - t - 0.01)

            watcher = asyncio.create_task(watch_loop())
            try:
                async for frame in super().run_tts(text, context_id):
                    if "first_frame" not in rec and frame is not None:
                        rec["first_frame"] = time.perf_counter()
                        rec["loop_lag_max_ms"] = round(lag["max"] * 1000, 1)
                        lag["stop"] = True
                    yield frame
            finally:
                lag["stop"] = True
                watcher.cancel()

        def _handle_synthesizing(self, evt):
            rec = self._diag_rec
            if rec is not None and "first_callback" not in rec and evt.result.audio_data:
                rec["first_callback"] = time.perf_counter()
            return super()._handle_synthesizing(evt)

        def _handle_completed(self, evt):
            # Pipecats Abschluss zuerst: Eine Ausnahme hier im SDK-Thread liesse die Synthese
            # sonst offiziell unbeendet (erster Versuch 2026-10-14: Pipeline hing beim Ende).
            result = super()._handle_completed(evt)
            rec, self._diag_rec = self._diag_rec, None
            self._diag_last_end = time.perf_counter()
            if rec is None:
                return result
            try:
                props = evt.result.properties
                for key, prop in SDK_LATENCIES.items():
                    value = props.get_property(getattr(speechsdk.PropertyId, prop), "")
                    rec[key] = int(value) if value.isdigit() else None
                base = rec.get("ttfb_start") or rec["run_tts"]
                row = {
                    k: (round((v - base) * 1000, 1) if isinstance(v, float) and k in _TIMES else v)
                    for k, v in rec.items()
                }
                with lock, path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(row) + "\n")
            except Exception as exc:  # noqa: BLE001 -- Diagnose darf die Synthese nie stoeren
                logger.warning(f"TTS-Diagnose: Eintrag verworfen ({exc!r:.120})")
            return result

    return DiagAzureTTSService


# Zeitstempel, die relativ zu ttfb_start (ms) geschrieben werden
_TIMES = {"ttfb_start", "run_tts", "sdk_call", "sdk_return", "first_callback", "first_frame"}
