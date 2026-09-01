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
    from pipecat.services.azure.llm import AzureLLMService
    from pipecat.services.azure.stt import AzureSTTService
    from pipecat.services.azure.tts import AzureTTSService

    cfg = load_azure_config()

    stt = AzureSTTService(
        api_key=cfg.speech_key,
        region=cfg.speech_region,
        language="de-DE",
    )
    llm = AzureLLMService(
        api_key=cfg.openai_key,
        endpoint=cfg.openai_endpoint,
        model=cfg.openai_deployment,
        api_version=cfg.openai_api_version,
    )
    tts = AzureTTSService(
        api_key=cfg.speech_key,
        region=cfg.speech_region,
        voice=cfg.tts_voice,
    )
    return StackServices(name="azure-eu", stt=stt, llm=llm, tts=tts)
