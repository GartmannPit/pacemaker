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
from pipecat.frames.frames import BotStartedSpeakingFrame, BotStoppedSpeakingFrame
from pipecat.observers.base_observer import BaseObserver, FramePushed
from pipecat.pipeline.runner import PipelineRunner
from pipecat.processors.frame_processor import FrameDirection

from ..metrics.collector import RUNS_DIR
from ..pipeline import build_pipeline_task
from ..stacks import STACKS
from .synthetic_transport import SyntheticTransport

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "audio"


class _BotIdleSignal(BaseObserver):
    """Meldet per asyncio.Event, wann der Bot NICHT spricht -- Taktgeber fuer den naechsten Clip."""

    def __init__(self) -> None:
        super().__init__()
        self.bot_idle = asyncio.Event()
        self.bot_idle.set()

    async def on_push_frame(self, data: FramePushed) -> None:
        if data.direction != FrameDirection.DOWNSTREAM:
            return
        if isinstance(data.frame, BotStartedSpeakingFrame):
            self.bot_idle.clear()
        elif isinstance(data.frame, BotStoppedSpeakingFrame):
            self.bot_idle.set()


async def _run(stack: str, turns: int) -> Path:
    clips = sorted(FIXTURES.glob("*.wav"))
    if not clips:
        raise SystemExit(
            f"Keine WAV-Clips in {FIXTURES}. Erst "
            f"`uv run python -m pacemaker_agent.tests.generate_fixtures` laufen lassen."
        )

    transport = SyntheticTransport()
    bot_idle = _BotIdleSignal()
    task = build_pipeline_task(stack, transport, extra_observers=[bot_idle])

    runner = PipelineRunner()
    run_task = asyncio.create_task(runner.run(task))
    await transport.input().ready.wait()  # Pipeline muss erst starten, bevor wir Audio pushen

    async def feed() -> None:
        for i in range(turns):
            clip = clips[i % len(clips)]
            await bot_idle.bot_idle.wait()
            logger.info(f"Turn {i + 1}/{turns}: {clip.name}")
            await transport.input().feed_clip(clip)
            await asyncio.sleep(0.3)  # kurze Luft, bis Turn-Detection reagiert
        await bot_idle.bot_idle.wait()  # letzte Antwort noch abwarten
        await task.stop_when_done()

    await asyncio.gather(feed(), run_task)

    latest = sorted(RUNS_DIR.glob(f"*-{stack}.jsonl"))[-1]
    return latest


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
