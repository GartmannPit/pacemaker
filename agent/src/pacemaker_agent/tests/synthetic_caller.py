"""Synthetic Caller: spielt vordefinierte deutsche Audio-Clips durch die Pipeline
und misst die E2E-Antwortzeit pro Turn -- reproduzierbare Latenzverteilung statt
Handstoppen, beliebig oft wiederholbar fuer belastbare p50/p90-Werte.

    uv run python -m pacemaker_agent.tests.generate_fixtures     # einmalig
    uv run python -m pacemaker_agent.tests.synthetic_caller --stack azure-eu --turns 30

Verdrahtung: build_pipeline_task() haengt Metrik-Collector und Transkript an und
schreibt das Run-Manifest (siehe pipeline.py). Der Synthetic Caller liefert den
Datei-Transport, die Turn-Taktung (naechster Clip erst, wenn der Bot mit seiner
Antwort fertig ist, sonst wuerde eine ueberlappende Einspeisung wie ein Barge-in
wirken) und das Turn-Protokoll mit genau einem Status je eingespieltem Clip
(metrics/turn_ledger.py).

Ergebnisse eines Laufs (gleiche run_id):
  experiments/runs/<run_id>.jsonl            Latenz je beantworteter Aeusserung
  experiments/runs/turns/<run_id>.jsonl      Status + Zeitpunkte je angebotener Aeusserung
  experiments/runs/manifests/<run_id>.json   Konfiguration + Bilanz
  experiments/runs/transcripts/<run_id>.jsonl
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from loguru import logger
from pipecat.frames.frames import BotStartedSpeakingFrame, BotStoppedSpeakingFrame
from pipecat.observers.base_observer import BaseObserver, FramePushed
from pipecat.pipeline.runner import PipelineRunner
from pipecat.processors.frame_processor import FrameDirection

from ..metrics.run_manifest import new_run_id, update_manifest
from ..metrics.turn_ledger import TurnLedger
from ..pipeline import build_pipeline_task
from ..stacks import STACKS
from .synthetic_transport import SyntheticTransport

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "audio"


# Der Bot gilt erst als fertig, wenn er so lange am Stueck still ist. Antworten kommen in
# Schueben (TTS satzweise, Realtime-Audio in Paketen); die Luecken dazwischen loesen kurz
# BotStoppedSpeaking aus. Ohne Wartezeit startete der naechste Clip mitten in der Antwort
# und wirkte als Barge-in (2026-10-03 bei s2s beobachtet).
BOT_SETTLE_SECS = 1.0


class _BotIdleObserver(BaseObserver):
    """Taktgeber fuer den naechsten Clip."""

    def __init__(self) -> None:
        super().__init__()
        self._bot_idle = asyncio.Event()
        self._bot_idle.set()

    async def on_push_frame(self, data: FramePushed) -> None:
        if data.direction != FrameDirection.DOWNSTREAM:
            return
        if isinstance(data.frame, BotStartedSpeakingFrame):
            self._bot_idle.clear()
        elif isinstance(data.frame, BotStoppedSpeakingFrame):
            self._bot_idle.set()

    async def wait_bot_settled(self) -> None:
        """Wartet, bis der Bot BOT_SETTLE_SECS am Stueck nicht gesprochen hat."""
        while True:
            await self._bot_idle.wait()
            try:
                await asyncio.wait_for(self._wait_bot_started(), timeout=BOT_SETTLE_SECS)
            except TimeoutError:
                return

    async def _wait_bot_started(self) -> None:
        while self._bot_idle.is_set():
            await asyncio.sleep(0.05)


async def _run(stack: str, turns: int) -> str:
    clips = sorted(FIXTURES.glob("*.wav"))
    if not clips:
        raise SystemExit(
            f"Keine WAV-Clips in {FIXTURES}. Erst "
            f"`uv run python -m pacemaker_agent.tests.generate_fixtures` laufen lassen."
        )

    run_id = new_run_id(stack)
    transport = SyntheticTransport()
    bot_idle = _BotIdleObserver()
    ledger = TurnLedger()
    task = build_pipeline_task(stack, transport, run_id=run_id, extra_observers=[bot_idle, ledger])

    runner = PipelineRunner()
    run_task = asyncio.create_task(runner.run(task))
    await transport.input().ready.wait()  # Pipeline muss erst starten, bevor wir Audio pushen

    async def feed() -> None:
        for i in range(turns):
            clip = clips[i % len(clips)]
            await bot_idle.wait_bot_settled()
            logger.info(f"Turn {i + 1}/{turns}: {clip.name}")
            ledger.begin(i + 1, clip.name)
            speech_end = await transport.input().feed_clip(clip)
            ledger.set_speech_end(i + 1, speech_end)
            await asyncio.sleep(0.3)  # kurze Luft, bis Turn-Detection reagiert
        await bot_idle.wait_bot_settled()  # letzte Antwort noch abwarten
        await task.stop_when_done()

    await asyncio.gather(feed(), run_task)

    ledger_path, balance = ledger.write(run_id)
    update_manifest(run_id, turns_requested=turns, result=balance)
    _report_balance(balance)
    logger.info(f"Turn-Protokoll: {ledger_path}")
    return run_id


def _report_balance(balance: dict) -> None:
    """Genau ein Status je eingespieltem Clip; alles ausser 'beantwortet' verzerrt die
    Latenzverteilung oder ist ein Ausfall und wird deshalb laut gemeldet."""
    counts = balance["status_counts"]
    summary = " | ".join(f"{k} {v}" for k, v in counts.items() if v) or "leer"
    line = (
        f"Turn-Bilanz: {balance['offered']} angeboten | {summary} | "
        f"LLM-Text {balance['text_delivery']}"
    )
    if counts.get("beantwortet") == balance["offered"]:
        logger.info(line)
    else:
        logger.warning(f"{line} -- Ausfaelle/Abweichungen, siehe Turn-Protokoll")


def main() -> None:
    parser = argparse.ArgumentParser(prog="synthetic-caller")
    parser.add_argument("--stack", default="azure-eu", choices=STACKS)
    parser.add_argument("--turns", type=int, default=30)
    args = parser.parse_args()

    run_id = asyncio.run(_run(args.stack, args.turns))
    logger.info(f"Fertig. Lauf: {run_id}")
    logger.info("Auswertung: uv run python -m pacemaker_agent.metrics.aggregate")


if __name__ == "__main__":
    main()
