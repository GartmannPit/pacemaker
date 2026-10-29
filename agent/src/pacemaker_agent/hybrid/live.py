"""Provider-Modul für GPT-Live (contracts.Starter): Sitzung erzeugen, Sideband, Notschluss.

Kapselt das Provider-Protokoll (CLAUDE.md, Architektur). Region explizit, Erzeugung und
Sideband auf demselben Host, keine Weiterleitungen (Plan A8). Provider-Fehlertexte werden
nicht weitergegeben oder protokolliert, nur Status und Code.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

import aiohttp
from websockets.exceptions import InvalidStatus

from ..config import LIVE_REGIONS
from .contracts import (
    VOICES,
    CloseOutcome,
    CreateUnclear,
    OfferRejected,
    ProviderBlocked,
    ProviderConfig,
    ProviderUnavailable,
    StartFailed,
)
from .sideband import BLOCKING_CODES, HybridSideband, force_close

CREATE_TIMEOUT_S = 30.0
# Serverereignisse, die der Browser für Anzeige und Lebenszyklus braucht (Plan A6).
# ServerEventSelector-Objekte (API-Format seit spätestens 2026-10-28; Strings: 400 invalid_type).
# Bewusst ohne "error": Provider-Texte nicht ungefiltert an den Browser.
# Ohne session.started/session.closed: Diese tragen die Sitzungsressource (instructions mit
# verdeckten Persona-Details, delegation, Provider-ID; SDK SessionResource). Ende und Grund
# erfährt die Seite über den Herzschlag (Plan Schritt 2 §4.1).
BROWSER_SERVER_EVENTS = [
    {"type": "session.input_transcript.delta"},
    {"type": "session.output_transcript.delta"},
]


@dataclass(frozen=True)
class LiveSettings:
    region: str
    api_key: str
    backend_model: str
    prompt: str
    hangup_tool: dict
    greeting: str = ""  # Begrüßung über session.commentary.append (Schritt 2b)

    def __post_init__(self) -> None:
        if self.region not in LIVE_REGIONS:
            raise ValueError(f"OPENAI_LIVE_REGION={self.region!r} unzulässig")

    @property
    def host(self) -> str:
        return "eu.api.openai.com" if self.region == "eu" else "api.openai.com"

    @property
    def http_base(self) -> str:
        return f"https://{self.host}"

    @property
    def sideband_base(self) -> str:
        return f"wss://{self.host}/v1/live/sessions"


def responses_tool(tool: dict) -> dict:
    """Werkzeug im Responses-Format (flach)."""
    return {
        "type": "function",
        "name": tool["name"],
        "description": tool["description"],
        "parameters": {
            "type": "object",
            "properties": tool["properties"],
            "required": tool["required"],
        },
    }


def session_payload(settings: LiveSettings, voice: str | None) -> dict[str, Any]:
    """Startkonfiguration; Datenkanal des Browsers immer gesperrt (Plan A6)."""
    if voice is not None and voice not in VOICES:
        raise ValueError("Unbekannte Stimme")
    session: dict[str, Any] = {
        "model": "gpt-live-1",
        # Ausdrücklich keine Speicherung für Forking/Aufnahme-Download (Standard heute false;
        # Vorgaben der API können sich ohne Ankündigung ändern).
        "store": False,
        "instructions": settings.prompt,
        "delegation": {
            "type": "responses",
            "responses": {
                "model": settings.backend_model,
                "tools": [responses_tool(settings.hangup_tool)],
                "max_output_tokens": 300,
            },
        },
        "client": {
            "data_channel": {
                "allowed_client_events": [],
                "allowed_server_events": BROWSER_SERVER_EVENTS,
            }
        },
    }
    if voice:
        session["audio"] = {"output": {"voice": voice}}
    return session


def _error_code(body: bytes) -> str | None:
    try:
        error = json.loads(body).get("error") or {}
    except (ValueError, AttributeError):
        return None
    code = error.get("code") if isinstance(error, dict) else None
    return code if isinstance(code, str) else None


def _provider_error[E: (StartFailed, ProviderBlocked)](exc: E, status: int, code: str | None) -> E:
    """Status und Code für das Betriebslog anhängen (Diagnose ohne Antworttext)."""
    exc.provider_status = status
    exc.provider_code = code
    return exc


class LiveStarter:
    """contracts.Starter für GPT-Live über HTTP (Erzeugung) und Sideband (Steuerung)."""

    def __init__(self, settings: LiveSettings, http: aiohttp.ClientSession) -> None:
        self._s = settings
        self._http = http

    async def create(self, sdp: str, voice: str | None) -> tuple[str, str]:
        body = {
            "session": session_payload(self._s, voice),
            "transport": {"type": "webrtc", "sdp": sdp},
        }
        try:
            async with asyncio.timeout(CREATE_TIMEOUT_S):
                async with self._http.post(
                    f"{self._s.http_base}/v1/live/sessions",
                    json=body,
                    headers={"Authorization": f"Bearer {self._s.api_key}"},
                    allow_redirects=False,
                ) as response:
                    raw = await response.read()
                    status = response.status
        except aiohttp.ClientConnectorError as exc:
            # Nur ein nachweislich gescheiterter Verbindungsaufbau ist eindeutig.
            raise ProviderUnavailable("verbindung") from exc
        except (TimeoutError, OSError, aiohttp.ClientError) as exc:
            # Anfrage möglicherweise angekommen: nicht wiederholen, Reserve bleibt (Plan §3).
            raise CreateUnclear() from exc
        if status in (200, 201):
            try:
                created = json.loads(raw)
                return created["session"]["id"], created["transport"]["sdp"]
            except (ValueError, KeyError, TypeError) as exc:
                raise CreateUnclear() from exc
        code = _error_code(raw)
        if code in BLOCKING_CODES:
            raise _provider_error(ProviderBlocked(code), status, code)
        if code == "invalid_offer":
            raise _provider_error(OfferRejected(code), status, code)
        if status >= 500 or status == 429:
            raise _provider_error(ProviderUnavailable(f"http_{status}"), status, code)
        # Übrige 4xx (z. B. unknown_parameter, 401/403): unsere Konfiguration
        raise _provider_error(ProviderConfig(f"http_{status}:{code or '-'}"), status, code)

    async def attach(
        self, provider_id: str, *, deadline_s: float, idle_timeout_s: float
    ) -> HybridSideband:
        return await HybridSideband.attach(
            provider_id=provider_id,
            base_url=self._s.sideband_base,
            api_key=self._s.api_key,
            deadline_s=deadline_s,
            idle_timeout_s=idle_timeout_s,
            hangup_tool_name=self._s.hangup_tool["name"],
            greeting=self._s.greeting,
        )

    async def force_close(self, provider_id: str) -> CloseOutcome:
        try:
            return await force_close(
                provider_id=provider_id, base_url=self._s.sideband_base, api_key=self._s.api_key
            )
        except InvalidStatus as exc:
            # 404/410: Sitzung existiert nicht mehr – gilt als beendet. Ob OpenAI so antwortet,
            # prüft die Live-Abnahme (Plan §5); andere Status bleiben unbestätigt.
            gone = exc.response.status_code in (404, 410)
            return CloseOutcome(confirmed=gone, reason="wiederanlauf")
        except Exception:  # Netzfehler o. ä.: unbestätigt, Reserve bleibt gebunden
            return CloseOutcome(confirmed=False, reason="wiederanlauf")
