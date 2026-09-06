"""Provider-Stacks hinter einem gemeinsamen Adapter.

Der einzige Ort im Code, an dem konkrete Provider-SDKs vorkommen. Die Pipeline
(pipeline.py) kennt nur STT/LLM/TTS-Objekte, nicht deren Herkunft. Neuer Stack
=> hier eine `_build_*`-Funktion ergaenzen, sonst nirgends.

Siehe docs/phase-0-proof-of-concept.md §1.3 (Provider-Matrix).
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import load_azure_config

STACKS = ("azure-eu", "baseline", "sovereign", "s2s")


@dataclass
class StackServices:
    name: str
    stt: object
    llm: object
    tts: object


def build_stack(name: str) -> StackServices:
    if name == "azure-eu":
        return _build_azure_eu()
    if name in ("baseline", "sovereign", "s2s"):
        raise NotImplementedError(
            f"Stack '{name}' ist laut Phase-0-Plan §3 erst in Woche 3 dran. "
            f"Aktuell nur 'azure-eu'."
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
    return StackServices(name="azure-eu", stt=stt, llm=llm, tts=tts)
