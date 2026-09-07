"""Einstiegspunkt. Waehlt Stack und Transport per CLI-Flag.

uv run pacemaker-agent --stack azure-eu --transport local
"""

from __future__ import annotations

import argparse
import asyncio

from loguru import logger

from .pipeline import build_pipeline_task
from .stacks import STACKS

TRANSPORTS = ("local", "webrtc", "livekit")


def _build_transport(kind: str):
    if kind == "local":
        from pipecat.transports.local.audio import (
            LocalAudioTransport,
            LocalAudioTransportParams,
        )

        # VAD wird in pipeline.py auf Aggregator-Ebene konfiguriert
        # (LLMUserAggregatorParams.vad_analyzer), nicht hier am Transport --
        # LocalAudioTransportParams hat in Pipecat >=1.8 kein vad_analyzer-Feld
        # mehr (wuerde von Pydantic still verworfen).
        return LocalAudioTransport(
            LocalAudioTransportParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
            )
        )

    raise NotImplementedError(
        f"Transport '{kind}' ist noch nicht verdrahtet. 'local' funktioniert jetzt; "
        f"'webrtc' / 'livekit' folgen direkt nach dem lokalen Milestone "
        f"(Phase-0-Plan §3, W1->W2)."
    )


async def _run(stack: str, transport_kind: str) -> None:
    from pipecat.pipeline.runner import PipelineRunner

    transport = _build_transport(transport_kind)
    task = build_pipeline_task(stack, transport)
    logger.info(f"Pacemaker-Agent startet | stack={stack} transport={transport_kind}")
    await PipelineRunner().run(task)


def main() -> None:
    parser = argparse.ArgumentParser(prog="pacemaker-agent")
    parser.add_argument("--stack", default="azure-eu", choices=STACKS)
    parser.add_argument("--transport", default="local", choices=TRANSPORTS)
    args = parser.parse_args()
    asyncio.run(_run(args.stack, args.transport))


if __name__ == "__main__":
    main()
