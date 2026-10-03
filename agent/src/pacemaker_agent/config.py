"""Konfiguration aus Umgebungsvariablen. Siehe agent/.env.example."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"Umgebungsvariable {name} fehlt. agent/.env aus agent/.env.example anlegen."
        )
    return value


@dataclass(frozen=True)
class AzureConfig:
    speech_key: str
    speech_region: str
    tts_voice: str
    openai_endpoint: str
    openai_key: str
    openai_deployment: str


def load_azure_config() -> AzureConfig:
    return AzureConfig(
        speech_key=_require("AZURE_SPEECH_KEY"),
        speech_region=os.environ.get("AZURE_SPEECH_REGION", "germanywestcentral"),
        tts_voice=os.environ.get("AZURE_TTS_VOICE", "de-DE-ConradNeural"),
        openai_endpoint=_require("AZURE_OPENAI_ENDPOINT"),
        openai_key=_require("AZURE_OPENAI_API_KEY"),
        openai_deployment=os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1-mini"),
    )


@dataclass(frozen=True)
class AzureRealtimeConfig:
    endpoint: str
    api_key: str
    deployment: str
    voice: str
    reasoning_effort: str | None


def load_azure_realtime_config() -> AzureRealtimeConfig:
    # Eine im Portal kopierte URL traegt oft schon `?model=<deployment>`. Den Query-Teil
    # verwerfen: Pipecat haengt das Deployment selbst an, und so steht der Deployment-Name
    # nur an einer Stelle (AZURE_OPENAI_REALTIME_DEPLOYMENT) -- auch fuer die Messdaten.
    endpoint = _require("AZURE_OPENAI_REALTIME_ENDPOINT").split("?", 1)[0].rstrip("/")
    return AzureRealtimeConfig(
        endpoint=endpoint,
        # Liegt das Realtime-Deployment in derselben Ressource, gilt derselbe Schluessel.
        api_key=os.environ.get("AZURE_OPENAI_REALTIME_API_KEY") or _require("AZURE_OPENAI_API_KEY"),
        deployment=_require("AZURE_OPENAI_REALTIME_DEPLOYMENT"),
        voice=os.environ.get("AZURE_OPENAI_REALTIME_VOICE", "cedar"),
        # Leer = Server-Default. Werte: minimal, low, medium, high
        reasoning_effort=os.environ.get("AZURE_OPENAI_REALTIME_REASONING_EFFORT") or None,
    )
