"""Pipecat-Pipeline-Aufbau. Stack-unabhaengig: bekommt fertige STT/LLM/TTS-Objekte.

Bei Speech-to-Speech-Stacks fehlen STT und TTS; das LLM verarbeitet Audio direkt. Der Stack
`live` (GPT-Live) steuert zusaetzlich Turn-Erkennung und Unterbrechungen selbst: keine lokale
VAD, kein Smart Turn, Turn-Grenzen kommen aus den Transkripten des Dienstes.
"""

from __future__ import annotations

import asyncio

from loguru import logger
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    EndWorkerFrame,
    FunctionCallResultProperties,
    LLMRunFrame,
    TTSSpeakFrame,
    UserStartedSpeakingFrame,
)
from pipecat.observers.base_observer import BaseObserver, FramePushed
from pipecat.observers.user_bot_latency_observer import LatencyBreakdown, UserBotLatencyObserver
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.pipeline.worker import ProcessorUnusablePolicy
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    AssistantTurnStoppedMessage,
    LLMAssistantAggregator,
    LLMContextAggregatorPair,
    LLMUserAggregator,
    LLMUserAggregatorParams,
    UserTurnMessageAddedMessage,
)
from pipecat.utils.types import NOT_GIVEN

from .audio_resampler import InputAudioResampler
from .config import load_tuning_config
from .metrics.barge_in import BargeInObserver
from .metrics.collector import MetricsCollector
from .metrics.run_manifest import write_manifest
from .metrics.transcript import TranscriptRecorder, TranscriptTimingObserver
from .personas.kaltakquise_head_of_ops import HANGUP_TOOL, HANGUP_TOOL_NAME, system_prompt
from .stacks import SELF_TURNING_STACKS, build_stack

# Werkzeuge fuer Kaskaden-Stacks und GPT-Live (dort ueber das Hintergrundmodell); der
# Azure-Realtime-Stack bekommt den Prompt ueber system_instruction und ist fuer Werkzeuge
# nicht geprueft.
_STACKS_WITH_TOOLS = {"live", "azure-eu", "baseline"}

# GPT-Live: spricht die Persona nach `auflegen` nicht innerhalb dieser Zeit, endet das
# Gespraech trotzdem (sonst haengt die Sitzung, falls das Modell den Abschied auslaesst).
_FAREWELL_TIMEOUT_SECS = 8.0


def _openai_tool(tool: dict) -> dict:
    """Werkzeug im OpenAI-Format (fuer das Aufwaermen ausserhalb von Pipecats Kontext)."""
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool["description"],
            "parameters": {
                "type": "object",
                "properties": tool["properties"],
                "required": tool["required"],
            },
        },
    }


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


class _HangupController(BaseObserver):
    """Persona legt auf (Werkzeug `auflegen`): Abschied sprechen, danach Gespraech beenden.

    Kaskade: der Abschiedssatz geht als TTSSpeakFrame an die TTS. GPT-Live hat keine TTS:
    Das Ergebnis des Werkzeugs geht an das Hintergrundmodell, das Live-Modell spricht den
    Abschied selbst (`speak_farewell=False`); Ende nach dessen Sprechende oder nach
    `_FAREWELL_TIMEOUT_SECS`.

    Das Ende folgt erst, wenn der Abschied ohne Unterbrechung ausgegeben wurde (Sprechbeginn
    und -ende am Ausgabe-Transport). Spricht der Anrufer vorher oder dazwischen, laeuft das
    Gespraech weiter -- sonst legte die Persona stumm oder mitten im Satz auf (synthetische
    Tests 2026-10-08: eine Unterbrechung verwarf bzw. kappte den Abschied, das Ende kam
    trotzdem durch).
    """

    def __init__(self, transcript: TranscriptRecorder, *, speak_farewell: bool = True) -> None:
        super().__init__()
        self._transcript = transcript
        self._speak_farewell = speak_farewell
        self._timeout: asyncio.Task | None = None
        self._task: PipelineTask | None = None
        self._pending = False
        self._spoken = False
        self._seen: set[int] = set()

    def attach(self, task: PipelineTask) -> None:
        self._task = task

    async def hangup(self, params) -> None:
        farewell = str(params.arguments.get("abschiedssatz", "")).strip() or "Auf Wiederhoeren."
        logger.info(f"Persona legt auf: {farewell!r}")
        self._transcript.record(role="event", text="auflegen")
        self._pending, self._spoken = True, False
        if self._speak_farewell:
            await params.result_callback(
                {"status": "aufgelegt"}, properties=FunctionCallResultProperties(run_llm=False)
            )
            await params.llm.push_frame(TTSSpeakFrame(farewell))
            return
        await params.result_callback(
            {
                "status": "aufgelegt",
                "anweisung": f"Verabschiede dich jetzt mit genau diesem Satz: {farewell}",
            }
        )
        self._timeout = asyncio.create_task(self._end_after_timeout())

    async def _end_after_timeout(self) -> None:
        await asyncio.sleep(_FAREWELL_TIMEOUT_SECS)
        if self._pending:
            logger.warning("Abschied nicht gesprochen -- Gespraech endet nach Zeitgrenze")
            self._pending = False
            self._transcript.record(role="event", text="aufgelegt")
            if self._task is not None:
                await self._task.queue_frame(EndWorkerFrame(reason="persona_aufgelegt"))

    async def on_push_frame(self, data: FramePushed) -> None:
        if not self._pending or data.frame.id in self._seen:
            return
        self._seen.add(data.frame.id)
        frame = data.frame
        if isinstance(frame, BotStartedSpeakingFrame):
            self._spoken = True
        elif isinstance(frame, BotStoppedSpeakingFrame) and self._spoken:
            self._pending = False
            if self._timeout is not None:
                self._timeout.cancel()
            self._transcript.record(role="event", text="aufgelegt")
            if self._task is not None:
                await self._task.queue_frame(EndWorkerFrame(reason="persona_aufgelegt"))
        elif isinstance(frame, UserStartedSpeakingFrame) and self._speak_farewell:
            # Nur Kaskade: GPT-Live haelt Hoerersignale und Ueberlappung selbst aus, der
            # Abschied laeuft dort weiter.
            self._pending = False
            logger.info("Abschied unterbrochen -- Gespraech laeuft weiter")
            self._transcript.record(role="event", text="auflegen_unterbrochen")


def build_pipeline_task(
    stack_name: str,
    transport,
    *,
    run_id: str,
    extra_observers: list | None = None,
    manifest_extra: dict | None = None,
) -> PipelineTask:
    """Baut die Pipeline und schreibt das Run-Manifest (metrics/run_manifest.py).

    `run_id` verbindet Metrikdatei, Transkript, Turn-Protokoll und Manifest eines Laufs.
    """
    tuning = load_tuning_config()
    prompt = system_prompt(short_opener=tuning.short_opener)
    use_tools = stack_name in _STACKS_WITH_TOOLS
    self_turning = stack_name in SELF_TURNING_STACKS
    openai_tools = [_openai_tool(HANGUP_TOOL)] if use_tools else None
    services = build_stack(stack_name, system_prompt=prompt, tools=openai_tools, run_id=run_id)

    context = LLMContext(
        messages=[{"role": "system", "content": prompt}],
        tools=[FunctionSchema(**HANGUP_TOOL)] if use_tools else NOT_GIVEN,
    )
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
        # GPT-Live: keine lokale VAD; der Dienst empfiehlt per Metadaten-Frame externe
        # Turn-Strategien ohne Unterbrechungen, die der Aggregator selbst uebernimmt.
        user_params=LLMUserAggregatorParams()
        if self_turning
        else LLMUserAggregatorParams(
            # stop_secs: Stille, bis Silero das Sprechende meldet (Pipecat-Default 0.2 s).
            # Steckt vollstaendig in der Turn-Erkennung. Per PACEMAKER_VAD_STOP_SECS
            # ueberschreibbar fuer Experimente (config.TuningConfig).
            # start_secs/min_volume: PACEMAKER_VAD_START_SECS / PACEMAKER_VAD_MIN_VOLUME.
            vad_analyzer=SileroVADAnalyzer(
                params=VADParams(
                    stop_secs=tuning.vad_stop_secs,
                    start_secs=tuning.vad_start_secs,
                    min_volume=tuning.vad_min_volume,
                )
            )
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

    if services.manifest_extra:
        manifest_extra = {**(manifest_extra or {}), **services.manifest_extra}
    write_manifest(
        run_id,
        stack=stack_name,
        llm_model=services.llm_model,
        tuning=tuning,
        system_prompt=prompt,
        extra=manifest_extra,
    )
    collector = MetricsCollector(stack_name, llm_model=services.llm_model, run_id=run_id)
    transcript = TranscriptRecorder(
        collector.path.parent / "transcripts" / collector.path.name,
        stack=stack_name,
        llm_model=services.llm_model,
    )
    _wire_transcript(context_aggregator, transcript)
    observers = [
        _build_metrics_observer(collector),
        TranscriptTimingObserver(transcript),
        BargeInObserver(run_id),
    ]
    hangup = _HangupController(transcript, speak_farewell=not self_turning) if use_tools else None
    if hangup is not None:
        services.llm.register_function(HANGUP_TOOL_NAME, hangup.hangup)
        observers.append(hangup)
    observers.extend(extra_observers or [])

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            allow_interruptions=True,  # Barge-in / Unterbrechbarkeit
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        observers=observers,
        processor_unusable_policy=(
            ProcessorUnusablePolicy.CANCEL if self_turning else ProcessorUnusablePolicy.CONTINUE
        ),
    )
    if hangup is not None:
        hangup.attach(task)

    if self_turning:
        # GPT-Live startet die Sitzung mit dem ersten LLMContextFrame. Die Persona spricht
        # nicht zuerst: der Anrufer (SDR) eroeffnet das Gespraech.
        @task.event_handler("on_pipeline_started")
        async def _start_live_session(_task: PipelineTask, _frame) -> None:
            await _task.queue_frame(LLMRunFrame())

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
