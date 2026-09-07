"""Pipecat-Pipeline-Aufbau. Stack-unabhaengig: bekommt fertige STT/LLM/TTS-Objekte."""

from __future__ import annotations

from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.observers.user_bot_latency_observer import LatencyBreakdown, UserBotLatencyObserver
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)

from .metrics.collector import MetricsCollector
from .personas.kaltakquise_head_of_ops import SYSTEM_PROMPT
from .stacks import build_stack


def _build_metrics_observer(stack_name: str) -> UserBotLatencyObserver:
    """Verdrahtet Pipecats UserBotLatencyObserver mit dem JSONL-Collector.

    `on_latency_measured` liefert die reine E2E-Latenz (das Kriterium aus
    CLAUDE.md), `on_latency_breakdown` kurz danach die Aufschluesselung pro
    Zyklus (Turn-Detection-Overhead, TTFB pro Service). Beide Events feuern
    synchron im selben `BotStartedSpeakingFrame`-Handling, deshalb reicht ein
    einfacher Zwischenspeicher zur Korrelation.
    """
    collector = MetricsCollector(stack_name)
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


def build_pipeline_task(
    stack_name: str, transport, *, extra_observers: list | None = None
) -> PipelineTask:
    services = build_stack(stack_name)

    context = LLMContext(messages=[{"role": "system", "content": SYSTEM_PROMPT}])
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
        user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
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
    pipeline = Pipeline(
        [
            transport.input(),
            services.stt,
            context_aggregator.user(),
            services.llm,
            services.tts,
            transport.output(),
            context_aggregator.assistant(),
        ]
    )

    observers = [_build_metrics_observer(stack_name)]
    observers.extend(extra_observers or [])

    return PipelineTask(
        pipeline,
        params=PipelineParams(
            allow_interruptions=True,  # Barge-in / Unterbrechbarkeit
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        observers=observers,
    )
