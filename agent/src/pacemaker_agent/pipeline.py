"""Pipecat-Pipeline-Aufbau. Stack-unabhaengig: bekommt fertige STT/LLM/TTS-Objekte.

Bei Speech-to-Speech-Stacks fehlen STT und TTS; das LLM verarbeitet Audio direkt.
"""

from __future__ import annotations

import asyncio

from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.observers.user_bot_latency_observer import LatencyBreakdown, UserBotLatencyObserver
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    AssistantTurnStoppedMessage,
    LLMAssistantAggregator,
    LLMContextAggregatorPair,
    LLMUserAggregator,
    LLMUserAggregatorParams,
    UserTurnMessageAddedMessage,
)

from .audio_resampler import InputAudioResampler
from .config import load_tuning_config
from .metrics.collector import MetricsCollector
from .metrics.run_manifest import write_manifest
from .metrics.transcript import TranscriptRecorder
from .personas.kaltakquise_head_of_ops import system_prompt
from .stacks import build_stack


def _build_metrics_observer(collector: MetricsCollector) -> UserBotLatencyObserver:
    """Verdrahtet Pipecats UserBotLatencyObserver mit dem JSONL-Collector.

    `on_latency_measured` liefert die reine E2E-Latenz (das Kriterium aus
    CLAUDE.md), `on_latency_breakdown` kurz danach die Aufschluesselung pro
    Zyklus (Turn-Detection-Overhead, TTFB pro Service). Beide Events feuern
    synchron im selben `BotStartedSpeakingFrame`-Handling, deshalb reicht ein
    einfacher Zwischenspeicher zur Korrelation.
    """
    observer = UserBotLatencyObserver()
    pending_e2e_ms: dict[str, float] = {}

    @observer.event_handler("on_latency_measured")
    async def _on_latency_measured(
        _observer: UserBotLatencyObserver, latency_seconds: float
    ) -> None:
        pending_e2e_ms["value"] = latency_seconds * 1000

    @observer.event_handler("on_latency_breakdown")
    async def _on_latency_breakdown(
        _observer: UserBotLatencyObserver, breakdown: LatencyBreakdown
    ) -> None:
        e2e_ms = pending_e2e_ms.pop("value", None)
        if e2e_ms is None:
            return  # Breakdown ohne zugehoerige Latenzmessung (z.B. erste Bot-Aeusserung)

        # Achtung: "TTS" ist als Teilstring auch in "...STTService..." enthalten
        # (S-T-T-S) -- deshalb ueber die volleren Suffixe matchen, sonst landet
        # die STT-TTFB fälschlich im TTS-Feld.
        llm_ttfb_ms: float | None = None
        tts_ttfb_ms: float | None = None
        for entry in breakdown.ttfb:
            if "LLMService" in entry.processor and llm_ttfb_ms is None:
                llm_ttfb_ms = entry.duration_secs * 1000
            elif "TTSService" in entry.processor and tts_ttfb_ms is None:
                tts_ttfb_ms = entry.duration_secs * 1000

        turn_detection_ms = (
            breakdown.user_turn_secs * 1000 if breakdown.user_turn_secs is not None else None
        )

        collector.record_turn(
            e2e_ms=e2e_ms,
            turn_detection_ms=turn_detection_ms,
            llm_ttfb_ms=llm_ttfb_ms,
            tts_ttfb_ms=tts_ttfb_ms,
        )

    logger.info(f"Metriken werden geschrieben nach: {collector.path}")
    return observer


def _wire_transcript(
    context_aggregator: LLMContextAggregatorPair, transcript: TranscriptRecorder
) -> None:
    """Schreibt jede fertige Nutzer- und Bot-Aeusserung ins Lauf-Transkript."""

    @context_aggregator.user().event_handler("on_user_turn_message_added")
    async def _on_user_message(
        _aggregator: LLMUserAggregator, message: UserTurnMessageAddedMessage
    ) -> None:
        transcript.record(role="user", text=message.content)

    @context_aggregator.assistant().event_handler("on_assistant_turn_stopped")
    async def _on_assistant_message(
        _aggregator: LLMAssistantAggregator, message: AssistantTurnStoppedMessage
    ) -> None:
        transcript.record(role="assistant", text=message.content, interrupted=message.interrupted)

    logger.info(f"Transkript wird geschrieben nach: {transcript.path}")


def build_pipeline_task(
    stack_name: str, transport, *, run_id: str, extra_observers: list | None = None
) -> PipelineTask:
    """Baut die Pipeline und schreibt das Run-Manifest (metrics/run_manifest.py).

    `run_id` verbindet Metrikdatei, Transkript, Turn-Protokoll und Manifest eines Laufs.
    """
    tuning = load_tuning_config()
    prompt = system_prompt(short_opener=tuning.short_opener)
    services = build_stack(stack_name, system_prompt=prompt)

    context = LLMContext(messages=[{"role": "system", "content": prompt}])
    # vad_analyzer hier (Aggregator-Ebene), nicht am Transport: Pipecat >=1.8 haengt
    # VAD-basierte Turn-Start-Erkennung an LLMUserAggregatorParams, nicht mehr an
    # TransportParams. Ohne das laeuft Turn-Erkennung nur ueber Transkription +
    # das semantische Smart-Turn-Modell, ohne den in CLAUDE.md vorgesehenen
    # Silero-VAD-Anteil.
    #
    # Getestet und verworfen: user_turn_strategies mit
    # TurnAnalyzerUserTurnStopStrategy(..., wait_for_transcript=False), um die
    # 1,8s-P99-Finalisierungslatenz von Azure STT (stt_latency.AZURE_TTFS_P99)
    # vom kritischen Pfad zu nehmen. Im 30-Turn-Vergleich machte das die
    # Turn-Detection-Latenz mehr als doppelt so langsam (p50 1036ms -> 2648ms)
    # statt schneller -- Mechanismus ungeklaert, siehe experiments/summaries/.
    # Getestet und verworfen: user_turn_strategies mit
    # LocalSmartTurnAnalyzerV3(cpu_count=4) statt Pipecat-Default (cpu_count=1),
    # in der Annahme, die lokale ONNX-Inferenz sei CPU-bound (Testrechner hat
    # 8 Kerne). 30-Turn-Vergleich zeigte keinen Effekt auf die
    # Turn-Detection-Latenz (p50 476ms -> 487ms, innerhalb der Messstreuung) --
    # kein Grund, von Pipecats Default abzuweichen. Details: experiments/summaries/.
    # Getestet und verworfen (synthetisch): SmartTurnParams.stop_secs 3s -> 1.5s.
    # Anlass war ein echter Gespraechs-Ausreisser (turn_detection_ms 3199.8ms,
    # 4x INCOMPLETE in Folge nahe der 3s-Grenze, siehe experiments/summaries/
    # 2026-09-07-latenz-ansaetze-*.md Nachtrag 3). 30-Turn-Synthetic-Test zeigte
    # aber keinen Effekt (Turn-Detection p50 476ms -> 491ms, p90 unveraendert
    # 545ms) -- saubere TTS-Clips loesen praktisch nie INCOMPLETE aus, der
    # synthetische Test kann diesen Hebel also weder als Nutzen noch als Risiko
    # (zu frueher Cutoff bei echten Sprechpausen) validieren. Ohne Beleg fuer
    # einen Nutzen zurueckgerollt; echte Validierung braucht ein echtes
    # Gespraech, nicht Synthetic-Caller-Daten.
    context_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            # stop_secs: Stille, bis Silero das Sprechende meldet (Pipecat-Default 0.2 s).
            # Steckt vollstaendig in der Turn-Erkennung. Per PACEMAKER_VAD_STOP_SECS
            # ueberschreibbar fuer Experimente (config.TuningConfig).
            vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=tuning.vad_stop_secs))
        ),
    )

    # Getestet und verworfen: ContextWindowLimiter (Sliding Window auf die letzten
    # 15 Turns statt vollem Verlauf, Modul mittlerweile entfernt). Idee war, das
    # mit jedem Turn wachsende Prompt-Volumen zu kappen -- Azure hat dafuer keine
    # Server-Einstellung ("ChatHistory" in Azure AI Foundry betrifft nur den
    # dortigen Test-Chat, nicht unser Deployment). Ergebnis: Zwar weniger
    # Prompt-Tokens (30-Turn-Test: 1759 -> 993 beim letzten Turn), aber **schlechter**
    # statt besser, weil das Kappen den Prompt-Prefix bei jedem Turn veraendert und
    # damit Azures automatisches Prompt-Caching zerstoert (Log zeigte vorher
    # "cache read input tokens: 1664", danach keine Cache-Treffer mehr). E2E p50
    # 1570ms -> 1770ms, LLM-TTFB p50 444ms -> 546ms. Gecachte Tokens sind
    # offenbar deutlich billiger/schneller verarbeitet als weniger, aber frische
    # Tokens. Details: experiments/summaries/2026-09-07-latenz-ansaetze-*.md.
    processors = [
        transport.input(),
        services.stt,
        context_aggregator.user(),
        # Nach dem User-Aggregator, damit VAD/Smart Turn weiter die Pipeline-Rate sehen.
        (
            InputAudioResampler(services.llm_input_sample_rate)
            if services.llm_input_sample_rate
            else None
        ),
        services.llm,
        services.tts,
        transport.output(),
        context_aggregator.assistant(),
    ]
    pipeline = Pipeline([p for p in processors if p is not None])

    write_manifest(
        run_id,
        stack=stack_name,
        llm_model=services.llm_model,
        tuning=tuning,
        system_prompt=prompt,
    )
    collector = MetricsCollector(stack_name, llm_model=services.llm_model, run_id=run_id)
    transcript = TranscriptRecorder(
        collector.path.parent / "transcripts" / collector.path.name,
        stack=stack_name,
        llm_model=services.llm_model,
    )
    _wire_transcript(context_aggregator, transcript)

    observers = [_build_metrics_observer(collector)]
    observers.extend(extra_observers or [])

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            allow_interruptions=True,  # Barge-in / Unterbrechbarkeit
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        observers=observers,
    )

    if services.warm_up is not None:
        warm_up = services.warm_up

        background: set[asyncio.Task] = set()

        @task.event_handler("on_pipeline_started")
        async def _on_pipeline_started(_task: PipelineTask, _frame) -> None:
            # Im Hintergrund: der Start soll nicht auf Azure warten. Referenz halten,
            # sonst kann der Task vor dem Ende eingesammelt werden.
            warm_task = asyncio.create_task(warm_up())
            background.add(warm_task)
            warm_task.add_done_callback(background.discard)

    return task
