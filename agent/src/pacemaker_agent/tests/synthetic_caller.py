"""Synthetic Caller: spielt vordefinierte deutsche Audio-Clips durch die Pipeline
und misst die E2E-Antwortzeit pro Turn -- reproduzierbare Latenzverteilung statt
Handstoppen, beliebig oft wiederholbar fuer belastbare p50/p90-Werte.

    uv run python -m pacemaker_agent.tests.generate_fixtures     # einmalig
    uv run python -m pacemaker_agent.tests.synthetic_caller --stack azure-eu --turns 30

Verdrahtung: build_pipeline_task() haengt den Metrik-Collector bereits
automatisch an (siehe pipeline.py) -- der Synthetic Caller liefert nur den
Datei-Transport und die Turn-Taktung (naechster Clip erst, wenn der Bot mit
seiner Antwort fertig ist, sonst wuerde eine ueberlappende Einspeisung wie
ein Barge-in wirken und die laufende Messung verwerfen).
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from loguru import logger
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.observers.base_observer import BaseObserver, FramePushed
from pipecat.pipeline.runner import PipelineRunner
from pipecat.processors.frame_processor import FrameDirection

from ..metrics.collector import RUNS_DIR
from ..pipeline import build_pipeline_task
from ..stacks import STACKS
from .synthetic_transport import SyntheticTransport

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "audio"


# Der Bot gilt erst als fertig, wenn er so lange am Stueck still ist. Antworten kommen in
# Schueben (TTS satzweise, Realtime-Audio in Paketen); die Luecken dazwischen loesen kurz
# BotStoppedSpeaking aus. Ohne Wartezeit startete der naechste Clip mitten in der Antwort
# und wirkte als Barge-in (2026-10-03 bei s2s beobachtet).
BOT_SETTLE_SECS = 1.0


class _TurnObserver(BaseObserver):
    """Taktgeber fuer den naechsten Clip und Zaehler der erkannten User-Turns."""

    def __init__(self) -> None:
        super().__init__()
        self._bot_idle = asyncio.Event()
        self._bot_idle.set()
        self._user_turn_frame_ids: set[int] = set()

    @property
    def user_turns(self) -> int:
        return len(self._user_turn_frame_ids)

    async def on_push_frame(self, data: FramePushed) -> None:
        if data.direction != FrameDirection.DOWNSTREAM:
            return
        if isinstance(data.frame, BotStartedSpeakingFrame):
            self._bot_idle.clear()
        elif isinstance(data.frame, BotStoppedSpeakingFrame):
            self._bot_idle.set()
        elif isinstance(data.frame, UserStoppedSpeakingFrame):
            # Derselbe Frame passiert mehrere Prozessoren -- ueber die ID nur einmal zaehlen.
            self._user_turn_frame_ids.add(data.frame.id)

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


async def _run(stack: str, turns: int) -> Path:
    clips = sorted(FIXTURES.glob("*.wav"))
    if not clips:
        raise SystemExit(
            f"Keine WAV-Clips in {FIXTURES}. Erst "
            f"`uv run python -m pacemaker_agent.tests.generate_fixtures` laufen lassen."
        )

    transport = SyntheticTransport()
    turn_observer = _TurnObserver()
    task = build_pipeline_task(stack, transport, extra_observers=[turn_observer])

    runner = PipelineRunner()
    run_task = asyncio.create_task(runner.run(task))
    await transport.input().ready.wait()  # Pipeline muss erst starten, bevor wir Audio pushen

    async def feed() -> None:
        for i in range(turns):
            clip = clips[i % len(clips)]
            await turn_observer.wait_bot_settled()
            logger.info(f"Turn {i + 1}/{turns}: {clip.name}")
            await transport.input().feed_clip(clip)
            await asyncio.sleep(0.3)  # kurze Luft, bis Turn-Detection reagiert
        await turn_observer.wait_bot_settled()  # letzte Antwort noch abwarten
        await task.stop_when_done()

    await asyncio.gather(feed(), run_task)

    latest = sorted(RUNS_DIR.glob(f"*-{stack}.jsonl"))[-1]
    _check_turn_accounting(turns, turn_observer.user_turns, latest)
    return latest


def _check_turn_accounting(clips_fed: int, user_turns: int, jsonl_path: Path) -> None:
    """Jeder Clip soll genau einen User-Turn mit genau einem Messwert ergeben.

    Abweichungen verzerren die Latenzverteilung: Zerfaellt ein Clip in mehrere Turns,
    fehlen gerade die Messwerte langsamer Antworten (der naechste Teil unterbricht sie).
    """
    with jsonl_path.open(encoding="utf-8") as fh:
        measurements = sum(1 for _ in fh)
    summary = f"Clips {clips_fed} | erkannte User-Turns {user_turns} | Messwerte {measurements}"
    if user_turns == clips_fed == measurements:
        logger.info(f"Turn-Bilanz sauber: {summary}")
    else:
        logger.warning(f"Turn-Bilanz abweichend -- Messung ggf. verzerrt: {summary}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="synthetic-caller")
    parser.add_argument("--stack", default="azure-eu", choices=STACKS)
    parser.add_argument("--turns", type=int, default=30)
    args = parser.parse_args()

    jsonl_path = asyncio.run(_run(args.stack, args.turns))
    logger.info(f"Fertig. Metriken: {jsonl_path}")
    logger.info("Auswertung: uv run python -m pacemaker_agent.metrics.aggregate experiments/runs")


if __name__ == "__main__":
    main()
