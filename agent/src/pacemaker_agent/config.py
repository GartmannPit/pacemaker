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


@dataclass(frozen=True)
class BaselineConfig:
    """Stack A (US-Baseline). Nur fuer markierte Referenzlaeufe mit synthetischen Clips."""

    deepgram_key: str
    openai_key: str
    openai_model: str
    elevenlabs_key: str
    elevenlabs_voice_id: str


def load_baseline_config() -> BaselineConfig:
    return BaselineConfig(
        deepgram_key=_require("DEEPGRAM_API_KEY"),
        openai_key=_require("OPENAI_API_KEY"),
        # Gleiches Modell wie im azure-eu-Referenzlauf, damit der Vergleich nur Provider misst.
        openai_model=os.environ.get("OPENAI_MODEL", "gpt-4.1-mini"),
        elevenlabs_key=_require("ELEVENLABS_API_KEY"),
        elevenlabs_voice_id=_require("ELEVENLABS_VOICE_ID"),
    )


@dataclass(frozen=True)
class LiveConfig:
    """Stack `live`: OpenAI GPT-Live (Gruenderentscheidung 2026-10-15).

    `region`: `eu` nutzt die EU-Residenz-Endpunkte (EWR + Schweiz, erst nach Freigabe des
    OpenAI-Projekts); sonst `api.openai.com` -- solche Laeufe sind Referenzlaeufe.
    """

    api_key: str
    region: str
    voice: str | None
    backend_model: str

    @property
    def base_url(self) -> str:
        host = "eu.api.openai.com" if self.region == "eu" else "api.openai.com"
        return f"wss://{host}/v1/live/sessions"


def load_live_config() -> LiveConfig:
    return LiveConfig(
        api_key=_require("OPENAI_API_KEY"),
        region=os.environ.get("OPENAI_LIVE_REGION", "global"),
        voice=os.environ.get("OPENAI_LIVE_VOICE") or None,
        # Hintergrundmodell fuer delegierte Arbeit (hier: Werkzeuge wie `auflegen`)
        backend_model=os.environ.get("OPENAI_LIVE_BACKEND_MODEL", "gpt-4.1-mini"),
    )


@dataclass(frozen=True)
class TuningConfig:
    """Stellschrauben der Pipeline, die per Umgebungsvariable fuer Experimente
    ueberschrieben werden koennen. Einzige Quelle der Defaults -- das Run-Manifest
    schreibt genau diese Werte mit."""

    stt_segmentation_ms: int  # Azure-STT-Segmentierungsstille (azure-eu)
    vad_stop_secs: float  # Stille, bis Silero das Sprechende meldet
    # Sprechbeginn: so lange Konfidenz UND Lautstaerke ueber Schwelle. Default 0.2 s
    # (Pipecat-Default). 0.1 s erkennt sehr kurze Antworten ("OK.", R19: ~1,4 statt ~3,2 s,
    # Summary §18) und verstummt beim Barge-in schneller (p50 306 statt 469 ms), wurde nach
    # der vorab festgelegten Regel aber NICHT uebernommen: Hoerersignal "Mhm" unterbrach mit
    # 0.1 s in 4/5, mit 0.2 s in 3/4 Faellen (Summary §19). Beide unterbrechen fast immer --
    # das loest keine VAD-Schwelle, sondern eine eigene Unterbrechungsregel.
    vad_start_secs: float
    vad_min_volume: float
    warm_up: bool  # Verbindungen vor dem ersten Turn aufbauen
    # Stille am Anfang/Ende jeder Azure-TTS-Anfrage in ms; None = Azure-Standard
    # (~0,1 s vorn, ~1-1,3 s hinten, gemessen 2026-10-07)
    tts_edge_silence_ms: int | None
    # Persona beginnt mit kurzem Einstieg ("Hm, nee."). Default aus seit 2026-10-07: Mit
    # asynchronem Filter und ohne TTS-Randstille bringt er beim ersten Audio nur noch
    # ~30-80 ms, der Inhalt kommt aber ~500-650 ms spaeter (Summary §15).
    short_opener: bool


def load_tuning_config() -> TuningConfig:
    edge_silence = os.environ.get("AZURE_TTS_EDGE_SILENCE_MS", "0")
    return TuningConfig(
        short_opener=os.environ.get("PACEMAKER_SHORT_OPENER", "0") == "1",
        stt_segmentation_ms=int(os.environ.get("AZURE_STT_SEGMENTATION_MS", "100")),
        vad_stop_secs=float(os.environ.get("PACEMAKER_VAD_STOP_SECS", "0.2")),
        vad_start_secs=float(os.environ.get("PACEMAKER_VAD_START_SECS", "0.2")),
        vad_min_volume=float(os.environ.get("PACEMAKER_VAD_MIN_VOLUME", "0.6")),
        warm_up=os.environ.get("PACEMAKER_WARM_UP", "1") == "1",
        tts_edge_silence_ms=None if edge_silence == "azure" else int(edge_silence),
    )
