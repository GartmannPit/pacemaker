"""Sideband einer GPT-Live-Sitzung (Produktfassung, abgeleitet aus tools/gptlive_browser).

Hängt sich an eine per WebRTC erzeugte Sitzung an, führt `auflegen` aus, beendet bei
Zeitlimit und Inaktivität und liefert Abschluss und Verbrauch (contracts.SidebandHandle).
Keine Dateiablage: Transkripttext bleibt im Speicher (Persistenz erst in Schritt 6),
gespiegeltes Audio wird nur flüchtig für das Abschiedsende ausgewertet.
"""

from __future__ import annotations

import asyncio
import base64
import json
import math
import re
from dataclasses import dataclass

from pipecat.audio.utils import is_silence
from pipecat.services.openai.live import events
from websockets.asyncio.client import ClientConnection
from websockets.asyncio.client import connect as _ws_connect

from .contracts import CloseOutcome, EndReason, UsageSummary

ATTACH_TIMEOUT_S = 12.0
SEND_TIMEOUT_S = 5.0
CLOSE_CONFIRM_S = 15.0
OUTPUT_QUIET_S = 1.5
FAREWELL_TIMEOUT_S = 20.0
_ID = re.compile(r"[A-Za-z0-9_-]+")


class _NoRedirectConnect(_ws_connect):
    """Keine Weiterleitungen: Ein Hostwechsel könnte die Region verlassen (Plan A8)."""

    def process_redirect(self, exc: Exception) -> Exception | str:
        return exc


def connect_attach(base_url: str, provider_id: str, api_key: str) -> _NoRedirectConnect:
    if not _ID.fullmatch(provider_id):
        raise ValueError("Unzulässige Provider-ID")
    if not base_url.startswith("wss://"):
        raise ValueError("Sideband nur über wss://")
    return _NoRedirectConnect(
        uri=f"{base_url.rstrip('/')}/{provider_id}/attach",
        additional_headers={"Authorization": f"Bearer {api_key}"},
        open_timeout=ATTACH_TIMEOUT_S,
        close_timeout=2.0,
    )


@dataclass(frozen=True)
class TranscriptPart:
    role: str  # "user" | "assistant"
    text: str
    start_ms: int | None
    end_ms: int | None


class HybridSideband:
    """Eine angehängte Sitzung. Erzeugen nur über `attach()`."""

    def __init__(self, websocket: ClientConnection, hangup_tool_name: str) -> None:
        loop = asyncio.get_running_loop()
        self._ws = websocket
        self._hangup = hangup_tool_name
        self._done: asyncio.Future[tuple[CloseOutcome, UsageSummary]] = loop.create_future()
        self._terminal = asyncio.Event()
        self._send_lock = asyncio.Lock()
        self._requested: EndReason | None = None
        self._close_task: asyncio.Task | None = None
        self._close_sent = False
        self._server_closed = False
        self._closing = False
        self._live_seconds: int | None = None
        self._backend: dict[str, int] = {}
        self._backend_complete = True
        self._seen_usage: set[str] = set()
        self._seen_calls: set[str] = set()
        self._pending: dict[str, tuple[bool, bool]] = {}  # delegation -> (hatte Aufrufe, auflegen)
        self._output_at = 0.0
        self._farewell_audio = False
        self._farewell_text = False
        self._last_user = loop.time()
        self.transcript: list[TranscriptPart] = []
        self._tasks: list[asyncio.Task] = []

    @classmethod
    async def attach(
        cls,
        *,
        provider_id: str,
        base_url: str,
        api_key: str,
        deadline_s: float,
        idle_timeout_s: float,
        hangup_tool_name: str,
    ) -> HybridSideband:
        """Anhängen, Empfang starten, per Ping/Pong bestätigen. Fehler gehen an den Aufrufer."""
        for value in (deadline_s, idle_timeout_s):
            if not math.isfinite(value) or value <= 0:
                raise ValueError("Zeitgrenzen müssen positiv und endlich sein")
        websocket = await connect_attach(base_url, provider_id, api_key)
        session = cls(websocket, hangup_tool_name)
        receiver = asyncio.create_task(session._receive())
        session._tasks = [
            receiver,
            asyncio.create_task(session._after(deadline_s, "zeitlimit")),
            asyncio.create_task(session._idle(idle_timeout_s)),
        ]
        try:
            async with asyncio.timeout(ATTACH_TIMEOUT_S):
                await (await websocket.ping())
            if session._terminal.is_set():
                raise ConnectionError("Sideband vor Bereitschaft beendet")
            return session
        except BaseException:
            receiver.cancel()
            await asyncio.shield(asyncio.gather(*session._tasks, return_exceptions=True))
            raise

    # --- contracts.SidebandHandle ---------------------------------------------------------------

    async def close(self, *, reason: EndReason) -> CloseOutcome:
        """Idempotent; der erste Grund zählt. Wartet auf Bestätigung oder Zeitüberschreitung."""
        if self._close_task is None and not self._terminal.is_set():
            self._requested = self._requested or reason
            self._closing = True
            self._close_task = asyncio.create_task(self._request_close())
        outcome, _ = await self.wait_closed()
        return outcome

    async def wait_closed(self) -> tuple[CloseOutcome, UsageSummary]:
        return await asyncio.shield(self._done)

    def usage(self) -> UsageSummary:
        return UsageSummary(
            live_seconds=self._live_seconds,
            backend_tokens=dict(self._backend),
            backend_complete=self._backend_complete,
            final=self._server_closed,
        )

    # --- intern ---------------------------------------------------------------------------------

    async def _send(self, event: events.ClientEvent, *, closing: bool = False) -> None:
        async with self._send_lock:
            if self._terminal.is_set() or (self._closing and not closing):
                return
            async with asyncio.timeout(SEND_TIMEOUT_S):
                await self._ws.send(json.dumps(event.to_payload(), ensure_ascii=False))

    async def _request_close(self) -> None:
        try:
            await self._send(events.SessionCloseEvent(), closing=True)
            self._close_sent = True
            async with asyncio.timeout(CLOSE_CONFIRM_S):
                await self._terminal.wait()
        except Exception:  # Zeitüberschreitung oder Sendefehler: unbestätigt beenden
            pass
        if not self._terminal.is_set():
            self._tasks[0].cancel()

    async def _after(self, seconds: float, reason: EndReason) -> None:
        await asyncio.sleep(seconds)
        await self.close(reason=reason)

    async def _idle(self, timeout_s: float) -> None:
        loop = asyncio.get_running_loop()
        while not self._terminal.is_set():
            remaining = self._last_user + timeout_s - loop.time()
            if remaining <= 0:
                await self.close(reason="inaktiv")
                return
            await asyncio.sleep(min(remaining, 1.0))

    async def _receive(self) -> None:
        try:
            async for message in self._ws:
                try:
                    event = events.parse_server_event(message)
                except (ValueError, UnicodeError):
                    continue
                await self._handle(event)
                if self._terminal.is_set():
                    break
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
        finally:
            await self._finish()

    async def _finish(self) -> None:
        self._terminal.set()
        self._closing = True
        current = asyncio.current_task()
        others = [t for t in self._tasks[1:] if t is not current]
        for task in others:
            task.cancel()
        await asyncio.gather(*others, return_exceptions=True)
        if not self._server_closed and not self._close_sent:
            # Notschluss über dieselbe Verbindung, falls sie noch offen ist (Plan A5).
            try:
                payload = json.dumps(events.SessionCloseEvent().to_payload())
                await asyncio.wait_for(self._ws.send(payload), timeout=2.0)
            except Exception:
                pass
        try:
            await asyncio.wait_for(self._ws.close(), timeout=3.0)
        except Exception:
            pass
        reason: EndReason = self._requested or (
            "verbindung_verloren" if self._server_closed else "sideband_abbruch"
        )
        if not self._done.done():
            self._done.set_result(
                (CloseOutcome(confirmed=self._server_closed, reason=reason), self.usage())
            )

    async def _handle(self, event: events.ServerEvent) -> None:
        loop = asyncio.get_running_loop()
        if isinstance(event, events.TranscriptDeltaEvent):
            if event.delta:
                self.transcript.append(
                    TranscriptPart(event.role, event.delta, event.start_ms, event.end_ms)
                )
                if event.role == "user":
                    self._last_user = loop.time()
                else:
                    self._output_at = loop.time()
                    self._farewell_text = True
        elif isinstance(event, events.OutputAudioDeltaEvent):
            if any(t.get_name() == "abschied" for t in self._tasks):
                if await asyncio.to_thread(_audible, event.delta):
                    self._output_at = loop.time()
                    self._farewell_audio = True
        elif isinstance(event, events.SessionUsageUpdatedEvent):
            self._update_live(event.usage)
        elif isinstance(event, events.SessionClosedEvent):
            if event.usage:
                self._update_live(event.usage)
            self._server_closed = True
            self._terminal.set()
        elif isinstance(event, events.ResponseEventEnvelope):
            await self._response_event(event)

    def _update_live(self, usage: events.Usage) -> None:
        if usage.seconds is not None and math.isfinite(usage.seconds) and usage.seconds >= 0:
            self._live_seconds = math.ceil(usage.seconds)  # kumulativ: ersetzen, nie summieren

    def _backend_usage(self, response: object) -> None:
        if not isinstance(response, dict):
            self._backend_complete = False
            return
        identity, usage = response.get("id"), response.get("usage")
        if not isinstance(identity, str) or not isinstance(usage, dict):
            self._backend_complete = False
            return
        if identity in self._seen_usage:
            return
        self._seen_usage.add(identity)
        for name in ("input_tokens", "output_tokens"):
            value = usage.get(name)
            if type(value) is int and value >= 0:
                self._backend[name] = self._backend.get(name, 0) + value
            else:
                self._backend_complete = False

    async def _response_event(self, event: events.ResponseEventEnvelope) -> None:
        key = event.delegation_id or "unkorreliert"
        if event.inner_type == "response.output_item.done" and not self._closing:
            try:
                item = events.ResponseOutputItem.model_validate(event.event.get("item") or {})
            except ValueError:
                return
            if item.type != "function_call" or item.status != "completed" or not item.call_id:
                return
            if item.call_id in self._seen_calls:
                return
            self._seen_calls.add(item.call_id)
            output, hangup = self._tool_output(item)
            had, hang = self._pending.get(key, (False, False))
            self._pending[key] = (True, hang or hangup)
            await self._send(
                events.ResponseItemCreateEvent(
                    item=events.FunctionCallOutputItem(call_id=item.call_id, output=output)
                )
            )
        elif event.inner_type in ("response.completed", "response.incomplete", "response.failed"):
            self._backend_usage(event.event.get("response"))
            had, hang = self._pending.pop(key, (False, False))
            if had and not self._closing:
                await self._send(events.ResponseCreateEvent())
                if hang and not any(t.get_name() == "abschied" for t in self._tasks):
                    self._farewell_audio = self._farewell_text = False
                    self._output_at = asyncio.get_running_loop().time()
                    self._tasks.append(asyncio.create_task(self._farewell(), name="abschied"))

    def _tool_output(self, item: events.ResponseOutputItem) -> tuple[str, bool]:
        if item.name != self._hangup:
            return json.dumps({"error": "Unbekanntes Werkzeug."}), False
        try:
            arguments = json.loads(item.arguments or "{}")
            farewell = arguments.get("abschiedssatz") if isinstance(arguments, dict) else None
            if not isinstance(farewell, str) or not farewell.strip():
                raise ValueError
        except ValueError:
            return json.dumps(
                {"error": "abschiedssatz muss eine nichtleere Zeichenfolge sein."}
            ), False
        return (
            json.dumps(
                {
                    "instruction": "Sprechen Sie jetzt den Abschiedssatz vollständig aus. "
                    "Danach wird das Gespräch serverseitig beendet.",
                    "abschiedssatz": farewell,
                },
                ensure_ascii=False,
            ),
            True,
        )

    async def _farewell(self) -> None:
        """Abschied ausgeben lassen: neue Ausgabe mit Text und Ton, dann Ruhe, dann Ende."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + FAREWELL_TIMEOUT_S
        while not self._terminal.is_set():
            now = loop.time()
            quiet = now - self._output_at >= OUTPUT_QUIET_S
            if (self._farewell_text and self._farewell_audio and quiet) or now >= deadline:
                await self.close(reason="auflegen")
                return
            await asyncio.sleep(0.1)


def _audible(delta: str) -> bool:
    # Nur Gesprächssteuerung (Ende des Abschieds), keine Bewertung der Stimme (CLAUDE.md).
    pcm = base64.b64decode(delta, validate=True)
    return bool(pcm) and len(pcm) % 2 == 0 and not is_silence(pcm)


async def force_close(*, provider_id: str, base_url: str, api_key: str) -> CloseOutcome:
    """Unabhängiger Steuerpfad: neu anhängen, session.close, auf session.closed warten."""
    async with connect_attach(base_url, provider_id, api_key) as websocket:
        await asyncio.wait_for(
            websocket.send(json.dumps(events.SessionCloseEvent().to_payload())), SEND_TIMEOUT_S
        )
        try:
            async with asyncio.timeout(CLOSE_CONFIRM_S):
                async for message in websocket:
                    try:
                        event = events.parse_server_event(message)
                    except (ValueError, UnicodeError):
                        continue
                    if isinstance(event, events.SessionClosedEvent):
                        return CloseOutcome(confirmed=True, reason="wiederanlauf")
        except TimeoutError:
            pass
    return CloseOutcome(confirmed=False, reason="wiederanlauf")
