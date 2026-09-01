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
    openai_api_version: str


def load_azure_config() -> AzureConfig:
    return AzureConfig(
        speech_key=_require("AZURE_SPEECH_KEY"),
        speech_region=os.environ.get("AZURE_SPEECH_REGION", "germanywestcentral"),
        tts_voice=os.environ.get("AZURE_TTS_VOICE", "de-DE-ConradNeural"),
        openai_endpoint=_require("AZURE_OPENAI_ENDPOINT"),
        openai_key=_require("AZURE_OPENAI_API_KEY"),
        openai_deployment=os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1-mini"),
        openai_api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2025-01-01-preview"),
    )
