"""Provider-Stacks hinter einem gemeinsamen Adapter.

Der einzige Ort im Code, an dem konkrete Provider-SDKs vorkommen. Die Pipeline
(pipeline.py) kennt nur STT/LLM/TTS-Objekte, nicht deren Herkunft. Neuer Stack
=> hier eine `_build_*`-Funktion ergaenzen, sonst nirgends.

Speech-to-Speech-Stacks (`s2s`) haben kein separates STT/TTS: `stt` und `tts` sind
dann None, das LLM nimmt Audio entgegen und liefert Audio.

Siehe docs/phase-0-proof-of-concept.md §1.3 (Provider-Matrix).
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import load_azure_config, load_azure_realtime_config, load_baseline_config

STACKS = ("azure-eu", "baseline", "sovereign", "s2s")


@dataclass
class StackServices:
    name: str
    stt: object | None
    llm: object
    tts: object | None
    llm_model: str
    # Abtastrate, die das LLM fuer Eingangsaudio erwartet, falls es Audio direkt
    # verarbeitet (s2s). None = Pipeline-Rate unveraendert durchreichen.
    llm_input_sample_rate: int | None = None


def build_stack(name: str, *, system_prompt: str) -> StackServices:
    """Baut die Services eines Stacks.

    `system_prompt` braucht nur s2s: Kaskadierte Stacks bekommen ihn ueber den
    LLMContext der Pipeline, der Realtime-Service bei lokaler Turn-Erkennung nicht.
    """
    if name == "azure-eu":
        return _build_azure_eu()
    if name == "s2s":
        return _build_s2s_azure(system_prompt)
    if name == "baseline":
        return _build_baseline()
    if name == "sovereign":
        raise NotImplementedError(
            f"Stack '{name}' ist noch nicht implementiert. Aktuell: 'azure-eu', 'baseline', 's2s'."
        )
    raise ValueError(f"Unbekannter Stack '{name}'. Erlaubt: {', '.join(STACKS)}")


def _build_azure_eu() -> StackServices:
    # Importpfade nach `uv sync` gegen die installierte Pipecat-Version pruefen
    # (siehe README-Hinweis). Bei aelteren Versionen: `from pipecat.services.azure import ...`
    import azure.cognitiveservices.speech as speechsdk
    from pipecat.services.azure.llm import AzureLLMService
    from pipecat.services.azure.stt import AzureSTTService
    from pipecat.services.azure.tts import AzureTTSService

    cfg = load_azure_config()

    stt = AzureSTTService(
        api_key=cfg.speech_key,
        region=cfg.speech_region,
        language="de-DE",
    )
    # Azure STT hat laut Pipecats eigenem Benchmark (stt_latency.AZURE_TTFS_P99)
    # eine P99-Finalisierungslatenz von 1,8s -- dominanter Anteil unserer
    # Turn-Detection-Latenz (siehe experiments/summaries/). Pipecat exponiert
    # dafuer keinen Konstruktor-Parameter, deshalb Zugriff auf das interne
    # SpeechConfig-Objekt: Azures serverseitige Segmentierungs-Stille-Schwelle
    # (Default laut Microsoft-Doku ~500ms) senken, bevor _connect() den
    # SpeechRecognizer daraus baut. Fragil ggue. Pipecat-Versionswechseln
    # (_speech_config ist ein privates Attribut) -- bei ImportError/AttributeError
    # nach `uv sync` hier zuerst pruefen.
    #
    # 200ms -> 30-Turn-Test: E2E p50 2176->1570ms, p90 2377->1817ms.
    # 100ms getestet und verworfen: nochmal schneller (p50 1396ms), aber
    # sichtbare Ueberfragmentierung -- "Guten Tag, hier ist Lena Fischer..."
    # wurde in zwei separate Turns zerschnitten statt als ein Satz erkannt zu
    # werden (bei 200ms blieb er zusammen). Schon mit sauberen TTS-Clips
    # sichtbar, bei echter menschlicher Sprache mit mehr Pausen vermutlich
    # staerker. Details: experiments/summaries/.
    stt._speech_config.set_property(speechsdk.PropertyId.Speech_SegmentationSilenceTimeoutMs, "200")
    llm = AzureLLMService(
        api_key=cfg.openai_key,
        endpoint=cfg.openai_endpoint,
        model=cfg.openai_deployment,
    )
    tts = AzureTTSService(
        api_key=cfg.speech_key,
        region=cfg.speech_region,
        voice=cfg.tts_voice,
    )
    return StackServices(
        name="azure-eu", stt=stt, llm=llm, tts=tts, llm_model=cfg.openai_deployment
    )


def _build_s2s_azure(system_prompt: str) -> StackServices:
    """Azure OpenAI Realtime (Speech-to-Speech), Stack D als Referenz.

    Turn-Erkennung bleibt lokal (Silero VAD + Smart Turn in pipeline.py), die
    serverseitige Turn-Detection ist abgeschaltet. Damit beginnt die E2E-Messung am
    selben Punkt wie beim kaskadierten Stack und ist direkt vergleichbar.
    """
    from pipecat.services.azure.realtime.llm import AzureRealtimeLLMService
    from pipecat.services.openai.realtime import events

    cfg = load_azure_realtime_config()

    session_properties = events.SessionProperties(
        output_modalities=["audio"],
        audio=events.AudioConfiguration(
            # turn_detection=False: Pipecat schickt bei lokalem Turn-Ende selbst
            # input_audio_buffer.commit + response.create. Mit Server-VAD meldete
            # zusaetzlich der Server Turn-Grenzen (doppelte User-Turn-Frames).
            input=events.AudioInput(turn_detection=False),
            output=events.AudioOutput(voice=cfg.voice),
        ),
        reasoning=(events.Reasoning(effort=cfg.reasoning_effort) if cfg.reasoning_effort else None),
    )
    llm = AzureRealtimeLLMService(
        api_key=cfg.api_key,
        base_url=cfg.endpoint,
        settings=AzureRealtimeLLMService.Settings(
            model=cfg.deployment,
            # Direkt in die Session-Konfiguration: Bei turn_detection=False erreicht kein
            # LLMContextFrame den Service, der System-Prompt aus dem Kontext kaeme nie an.
            system_instruction=system_prompt,
            session_properties=session_properties,
        ),
    )
    return StackServices(
        name="s2s",
        stt=None,
        llm=llm,
        tts=None,
        # Reasoning-Stufe mit in den Modellnamen, damit Laeufe in der Auswertung getrennt bleiben.
        llm_model=(
            f"{cfg.deployment} (reasoning={cfg.reasoning_effort})"
            if cfg.reasoning_effort
            else cfg.deployment
        ),
        llm_input_sample_rate=events.PCMAudioFormat().rate,
    )


def _build_baseline() -> StackServices:
    """Stack A: US-Baseline (Deepgram Nova-3 + OpenAI + ElevenLabs Flash v2.5).

    NUR Referenz fuer die technische Obergrenze, nie Produktpfad (CLAUDE.md: keine
    EU-Datenresidenz). Ausschliesslich mit synthetischen Clips betreiben. Setup:
    docs/phase-0-setup-stack-a.md.
    """
    from pipecat.services.deepgram.stt import DeepgramSTTService
    from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
    from pipecat.services.openai.llm import OpenAILLMService
    from pipecat.transcriptions.language import Language

    cfg = load_baseline_config()

    stt = DeepgramSTTService(
        api_key=cfg.deepgram_key,
        mip_opt_out=True,  # Testaudio nicht fuer Deepgrams Modelltraining freigeben
        settings=DeepgramSTTService.Settings(model="nova-3", language=Language.DE),
    )
    llm = OpenAILLMService(
        api_key=cfg.openai_key,
        settings=OpenAILLMService.Settings(model=cfg.openai_model),
    )
    tts = ElevenLabsTTSService(
        api_key=cfg.elevenlabs_key,
        settings=ElevenLabsTTSService.Settings(
            voice=cfg.elevenlabs_voice_id,
            model="eleven_flash_v2_5",
            language=Language.DE,
        ),
    )
    return StackServices(
        name="baseline", stt=stt, llm=llm, tts=tts, llm_model=f"openai/{cfg.openai_model}"
    )
