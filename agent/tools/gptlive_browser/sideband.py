"""Sideband für genau eine bestehende GPT-Live-Sitzung, ohne Audio-Persistenz."""

from __future__ import annotations

import asyncio
import base64
import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from pipecat.audio.utils import is_silence
from pipecat.services.openai.live import events
from websockets.asyncio.client import ClientConnection
from websockets.asyncio.client import connect as websocket_connect

ATTACH_TIMEOUT_S = 12.0
SEND_TIMEOUT_S = 5.0
OUTPUT_QUIET_S = 1.5
FAREWELL_TIMEOUT_S = 20.0


@dataclass
class SessionResult:
    """Abschluss einschließlich ausschließlich numerischer Verbrauchsangaben.

    ``backend_tokens`` summiert die Responses-Verbräuche; Live-Verbrauch steht
    separat in ``usage_seconds``. Fehlende Verbrauchsmeldungen bleiben erkennbar.
    ``diagnostics`` enthält nur lokale Codes, niemals fremde Fehlertexte/Payloads.
    """

    session_id: str
    reason: str
    complete: bool
    usage_seconds: float | None
    backend_tokens: dict[str, int]
    diagnostics: list[str]


@dataclass
class _Response:
    had_calls: bool = False
    hangup: bool = False


class SidebandSession:
    """Empfang, Werkzeuge, Deadline und Abschluss einer angehängten Sitzung."""

    def __init__(
        self,
        session_id: str,
        websocket: ClientConnection,
        path: Path,
        hangup_tool_name: str,
    ) -> None:
        self.session_id = session_id
        self._websocket = websocket
        self._path = path
        self._hangup_tool_name = hangup_tool_name
        self._ready = asyncio.Event()
        self._terminal = asyncio.Event()
        self._done: asyncio.Future[SessionResult] = asyncio.get_running_loop().create_future()
        self._records: asyncio.Queue[dict | None] = asyncio.Queue()
        self._send_lock = asyncio.Lock()
        self._closing = False
        self._finishing = False
        self._server_closed = False
        self._close_sent = False
        self._reason: str | None = None
        self._complete = False
        self._intact = True
        self._usage_seconds: float | None = None
        self._backend_tokens: dict[str, int] = {}
        self._diagnostics: list[str] = []
        self._sent_ids: set[str] = set()
        self._seen_calls: set[str] = set()
        self._seen_usage: set[str] = set()
        self._responses: dict[str, _Response] = {}
        self._output_at = 0.0
        self._farewell_transcript = False
        self._farewell_audio = False
        self._audio_processing = False
        self._farewell_task: asyncio.Task | None = None
        self._close_task: asyncio.Task | None = None
        self._deadline_task: asyncio.Task | None = None

    @classmethod
    async def attach(
        cls,
        *,
        session_id: str,
        base_url: str,
        api_key: str,
        output_dir: Path,
        max_duration_s: float,
        hangup_tool_name: str,
    ) -> SidebandSession:
        """Bestehende Sitzung anhängen; Upgrade, Empfang und Ping/Pong abwarten.

        Ein Sideband benötigt kein ``session.start`` und kein erneutes
        ``session.started``. Der Pong bestätigt die lebende Attach-Verbindung,
        während die Empfangsschleife bereits auf Ereignisse wartet.
        """
        if not re.fullmatch(r"[A-Za-z0-9_-]+", session_id):
            raise ValueError("Unzulässige session_id für URL und Dateinamen")
        url = urlsplit(base_url)
        if (
            url.scheme != "wss"
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise ValueError("base_url muss ein expliziter wss-Host-Präfix sein")
        if not math.isfinite(max_duration_s) or max_duration_s <= 0:
            raise ValueError("max_duration_s muss positiv und endlich sein")
        if not api_key or not hangup_tool_name:
            raise ValueError("API-Key und Werkzeugname müssen gesetzt sein")
        path = output_dir / f"{session_id}.jsonl"
        # Vor dem Attach Schreibbarkeit prüfen, bestehende Protokolle nicht überschreiben.
        await asyncio.to_thread(_prepare_file, path)
        websocket = await websocket_connect(
            uri=f"{base_url.rstrip('/')}/{session_id}/attach",
            additional_headers={"Authorization": f"Bearer {api_key}"},
            open_timeout=ATTACH_TIMEOUT_S,
            close_timeout=2.0,
        )
        session = cls(session_id, websocket, path, hangup_tool_name)
        session._writer_task = asyncio.create_task(session._write_records())
        session._receive_task = asyncio.create_task(session._receive())
        session._deadline_task = asyncio.create_task(session._deadline(max_duration_s))
        try:
            async with asyncio.timeout(ATTACH_TIMEOUT_S):
                await session._ready.wait()
                pong = await websocket.ping()
                await pong
                if session._terminal.is_set():
                    raise RuntimeError("Sideband vor Empfangsbereitschaft beendet")
            session._record({"type": "status", "status": "angehaengt"})
            return session
        except BaseException:
            session._fail("attach_fehlgeschlagen")
            await session._ready.wait()
            session._stop_receiver()
            await asyncio.shield(session.wait_closed())
            raise

    async def close(self, *, reason: str, timeout_s: float = 12.0) -> SessionResult:
        """Einmal schließen; alle Aufrufer erhalten dasselbe persistierte Ergebnis.

        Der erste Aufruf bestimmt Grund und Timeout. Abbruch eines wartenden
        Aufrufers bricht weder Abschluss noch Empfang ab.
        """
        if not math.isfinite(timeout_s) or timeout_s < 0:
            raise ValueError("timeout_s muss nichtnegativ und endlich sein")
        if self._close_task is None and not self._terminal.is_set():
            self._closing = True
            self._reason = reason
            self._close_task = asyncio.create_task(self._request_close(timeout_s))
        if self._close_task is not None:
            await asyncio.shield(self._close_task)
        return await self.wait_closed()

    async def wait_closed(self) -> SessionResult:
        """Bis zum Abschluss von Verbindung, Hintergrundtasks und JSONL warten."""
        return await asyncio.shield(self._done)

    def _diagnose(self, code: str, *, incomplete: bool = False) -> None:
        if code not in self._diagnostics:
            self._diagnostics.append(code)
        if incomplete:
            self._intact = False

    def _fail(self, code: str) -> None:
        self._diagnose(code, incomplete=True)
        self._complete = False
        self._reason = "unvollstaendig"
        self._terminal.set()

    def _stop_receiver(self) -> None:
        # Ein zweites cancel() darf den bereits laufenden finally-Block nicht abbrechen.
        if not self._finishing:
            self._receive_task.cancel()

    def _record(self, row: dict) -> None:
        self._records.put_nowait({**row, "timestamp": datetime.now(UTC).isoformat()})

    async def _write_records(self) -> None:
        try:
            while (row := await self._records.get()) is not None:
                await asyncio.to_thread(_append_record, self._path, row)
        except Exception:
            # Auch OSError-/Parsertexte können vertrauliche Inhalte enthalten.
            self._fail("persistenz_fehler")
            self._stop_receiver()

    async def _send(self, event: events.ClientEvent) -> None:
        async with self._send_lock:
            if self._terminal.is_set():
                return
            if self._closing and not isinstance(event, events.SessionCloseEvent):
                return
            self._sent_ids.add(event.event_id)
            async with asyncio.timeout(SEND_TIMEOUT_S):
                await self._websocket.send(json.dumps(event.to_payload(), ensure_ascii=False))

    async def _deadline(self, duration: float) -> None:
        await asyncio.sleep(duration)
        # Die harte Deadline hat Vorrang vor einem noch laufenden Abschied.
        await self.close(reason="zeitlimit")

    async def _request_close(self, timeout_s: float) -> None:
        try:
            async with asyncio.timeout(timeout_s):
                await self._send(events.SessionCloseEvent())
                self._close_sent = True
                await self._terminal.wait()
        except TimeoutError:
            self._fail("session_closed_timeout")
            self._stop_receiver()
        except Exception:
            self._fail("senden_fehlgeschlagen")
            self._stop_receiver()

    async def _receive(self) -> None:
        try:
            self._ready.set()
            if self._terminal.is_set():
                return
            async for message in self._websocket:
                try:
                    event = events.parse_server_event(message)
                except (ValueError, UnicodeError):
                    self._diagnose("ereignis_parsefehler", incomplete=True)
                    continue
                await self._handle(event)
                if self._terminal.is_set():
                    break
        except asyncio.CancelledError:
            pass
        except Exception:
            self._diagnose("empfang_fehlgeschlagen", incomplete=True)
        finally:
            self._finishing = True
            if not self._terminal.is_set():
                self._fail("sideband_abbruch")
            self._closing = True
            tasks = [t for t in (self._deadline_task, self._farewell_task) if t is not None]
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if not self._server_closed and not self._close_sent:
                # Notschluss: Die OpenAI-Sitzung darf nicht unbeobachtet weiterlaufen (K5).
                try:
                    payload = events.SessionCloseEvent().to_payload()
                    await asyncio.wait_for(self._websocket.send(json.dumps(payload)), timeout=2.0)
                    self._diagnose("notschluss_gesendet")
                except Exception:
                    self._diagnose("notschluss_fehlgeschlagen", incomplete=True)
            try:
                await asyncio.wait_for(self._websocket.close(), timeout=3.0)
            except Exception:
                self._diagnose("transport_close_fehler", incomplete=True)
            self._record(
                {
                    "type": "status",
                    "status": "beendet",
                    "session_id": self.session_id,
                    "reason": self._reason,
                    "complete": self._complete and self._intact,
                    "usage_seconds": self._usage_seconds,
                    "backend_tokens": dict(self._backend_tokens),
                    "diagnostics": list(self._diagnostics),
                }
            )
            self._records.put_nowait(None)
            await self._writer_task
            self._done.set_result(
                SessionResult(
                    session_id=self.session_id,
                    reason=self._reason or "unvollstaendig",
                    complete=self._complete and self._intact,
                    usage_seconds=self._usage_seconds,
                    backend_tokens=dict(self._backend_tokens),
                    diagnostics=list(self._diagnostics),
                )
            )

    async def _handle(self, event: events.ServerEvent) -> None:
        if event.client_event_id and event.client_event_id not in self._sent_ids:
            self._diagnose("unbekannte_bestaetigungs_id")
        if isinstance(event, (events.ContextAppendedEvent, events.SessionUpdatedEvent)) or (
            isinstance(event, events.ErrorEvent)
        ):
            # Für K3: welche Steuerereignisse der Sideband sieht und ob sie von uns stammen.
            # Nur Typ, Code und Feldname; keine Meldungstexte oder Inhalte.
            error = event.error if isinstance(event, events.ErrorEvent) else None
            correlated = event.client_event_id or (
                getattr(error, "client_event_id", None) if error else None
            )
            self._record(
                {
                    "type": "steuerereignis",
                    "event": event.type,
                    "eigen": (correlated in self._sent_ids) if correlated else None,
                    "code": error.code if error else None,
                    "error_type": error.type if error else None,
                    "param": error.param if error else None,
                }
            )
        if isinstance(event, events.TranscriptDeltaEvent):
            self._record(
                {
                    "type": "transcript",
                    "role": event.role,
                    "text": event.delta,
                    "start_ms": event.start_ms,
                    "end_ms": event.end_ms,
                }
            )
            if event.role == "assistant" and event.delta:
                self._output_at = asyncio.get_running_loop().time()
                self._farewell_transcript = True
        elif isinstance(event, events.OutputAudioDeltaEvent):
            if self._farewell_task is not None:
                received_at = asyncio.get_running_loop().time()
                self._audio_processing = True
                try:
                    audible = await asyncio.to_thread(_audible_pcm, event.delta)
                except ValueError:
                    self._diagnose("audio_parsefehler", incomplete=True)
                    self._output_at = received_at
                else:
                    if audible:
                        self._output_at = received_at
                        self._farewell_audio = True
                finally:
                    self._audio_processing = False
        elif isinstance(event, events.SessionUsageUpdatedEvent):
            self._update_usage(event.usage)
        elif isinstance(event, events.SessionClosedEvent):
            if event.usage:
                self._update_usage(event.usage)
            if self._farewell_task is not None and not self._closing:
                self._diagnose("abschied_vorzeitig_beendet", incomplete=True)
            self._reason = self._reason or event.reason or "beendet"
            self._server_closed = True
            self._complete = True
            self._terminal.set()
        elif isinstance(event, events.ResponseEventEnvelope):
            await self._response_event(event)
        elif isinstance(event, events.ErrorEvent):
            # Nicht beenden: Fehler können abgewiesene Fremdbefehle sein (V2). Ein
            # tatsächliches Sitzungsende kommt als session.closed oder Verbindungsabbruch.
            self._diagnose("server_fehler")
        elif isinstance(event, events.UnknownServerEvent):
            self._diagnose("unbekanntes_ereignis")
        elif isinstance(event, events.SessionDelegationCreatedEvent):
            if event.delegation.target != "responses":
                self._fail("unerwartete_client_delegation")

    def _update_usage(self, usage: events.Usage) -> None:
        if usage.seconds is not None and math.isfinite(usage.seconds) and usage.seconds >= 0:
            # Kumulativ, keine Summe periodischer Meldungen.
            self._usage_seconds = usage.seconds
            self._record({"type": "usage", "usage_seconds": usage.seconds})

    async def _response_event(self, event: events.ResponseEventEnvelope) -> None:
        key = event.delegation_id or "uncorrelated"
        if event.inner_type == "response.output_item.done" and not self._closing:
            try:
                item = events.ResponseOutputItem.model_validate(event.event.get("item") or {})
            except ValueError:
                self._diagnose("werkzeug_parsefehler", incomplete=True)
                return
            if item.type != "function_call" or item.status != "completed":
                return
            if not item.call_id or not item.name:
                self._diagnose("werkzeug_ohne_id_oder_name", incomplete=True)
                return
            if item.call_id in self._seen_calls:
                self._diagnose("doppelte_call_id")
                return
            self._seen_calls.add(item.call_id)
            pending = self._responses.setdefault(key, _Response())
            pending.had_calls = True
            output, hangup = self._tool_output(item)
            pending.hangup |= hangup
            await self._send(
                events.ResponseItemCreateEvent(
                    item=events.FunctionCallOutputItem(call_id=item.call_id, output=output)
                )
            )
        elif event.inner_type in ("response.completed", "response.incomplete", "response.failed"):
            if event.inner_type == "response.completed":
                self._backend_usage(event)
            else:
                self._diagnose("backend_response_fehlgeschlagen", incomplete=True)
            pending = self._responses.pop(key, None)
            if pending and pending.had_calls and not self._closing:
                await self._send(events.ResponseCreateEvent())
                if pending.hangup and self._farewell_task is None:
                    self._farewell_transcript = self._farewell_audio = False
                    self._output_at = asyncio.get_running_loop().time()
                    self._farewell_task = asyncio.create_task(self._await_farewell())

    def _tool_output(self, item: events.ResponseOutputItem) -> tuple[str, bool]:
        if item.name != self._hangup_tool_name:
            self._diagnose("unbekanntes_werkzeug")
            return json.dumps({"error": "Unbekanntes Werkzeug."}), False
        try:
            arguments = json.loads(item.arguments or "{}")
            farewell = arguments.get("abschiedssatz") if isinstance(arguments, dict) else None
            if not isinstance(farewell, str) or not farewell.strip():
                raise ValueError
        except ValueError:
            self._diagnose("ungueltige_auflegen_argumente", incomplete=True)
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

    async def _await_farewell(self) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + FAREWELL_TIMEOUT_S
        while not self._terminal.is_set() and not self._closing:
            now = loop.time()
            if (
                self._farewell_transcript
                and self._farewell_audio
                and not self._audio_processing
                and now - self._output_at >= OUTPUT_QUIET_S
            ):
                await self.close(reason="auflegen")
                return
            if now >= deadline:
                self._diagnose("abschied_timeout", incomplete=True)
                await self.close(reason="auflegen")
                return
            await asyncio.sleep(min(0.1, OUTPUT_QUIET_S, deadline - now))

    def _backend_usage(self, event: events.ResponseEventEnvelope) -> None:
        response = event.event.get("response")
        if not isinstance(response, dict):
            return
        usage = response.get("usage")
        if not isinstance(usage, dict):
            return
        identity = response.get("id")
        if not isinstance(identity, str) or not identity:
            self._diagnose("backend_verbrauch_ohne_response_id", incomplete=True)
            return
        if identity in self._seen_usage:
            return
        self._seen_usage.add(identity)
        for name in ("input_tokens", "output_tokens", "total_tokens"):
            value = usage.get(name)
            if type(value) is int and value >= 0:
                self._backend_tokens[name] = self._backend_tokens.get(name, 0) + value
        self._record({"type": "usage", "backend_tokens": dict(self._backend_tokens)})


def _prepare_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8"):
        pass


def _audible_pcm(delta: str) -> bool:
    # GPT-Live/Pipecat: PCM16 mono; Stillepakete laufen auch nach Sprechende weiter.
    # Nur Gesprächssteuerung, keine Bewertung der Stimme; Bytes bleiben flüchtig.
    pcm = base64.b64decode(delta, validate=True)
    if len(pcm) % 2:
        raise ValueError("Ungültige PCM16-Länge")
    return bool(pcm) and not is_silence(pcm)


def _append_record(path: Path, row: dict) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")


async def force_close(*, session_id: str, base_url: str, api_key: str) -> None:
    """Unabhängiger Steuerpfad: neu anhängen, nur session.close senden, nichts protokollieren."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", session_id):
        raise ValueError("Unzulässige session_id")
    async with websocket_connect(
        uri=f"{base_url.rstrip('/')}/{session_id}/attach",
        additional_headers={"Authorization": f"Bearer {api_key}"},
        open_timeout=ATTACH_TIMEOUT_S,
        close_timeout=2.0,
    ) as websocket:
        await asyncio.wait_for(
            websocket.send(json.dumps(events.SessionCloseEvent().to_payload())), timeout=5.0
        )
