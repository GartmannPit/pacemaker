"""Lokaler GPT-Live-Browsertest: Audio per WebRTC direkt zu OpenAI, Steuerung über den Sideband.

Prototyp für den Architekturversuch Hybrid (docs/phase-1-architekturversuch-hybrid.md).
Kein Messvertrag-Lauf.

    cd agent && OPENAI_LIVE_REGION=referenz uv run python tools/gptlive_browser/server.py
    -> http://localhost:3000            (Gespräch, Clip-Messung)
    -> http://localhost:3000/?debug=1   (Manipulationsversuche V2)

Der API-Key bleibt serverseitig (agent/.env, OPENAI_API_KEY); der Server lauscht nur auf
127.0.0.1. Der Browser darf über den Datenkanal nichts senden (`allowed_client_events: []`);
Transkript, `auflegen` und Sitzungsende laufen über den Sideband (sideband.py).
Ablage (gitignored): experiments/runs/hybrid/ (Transkripte nur als Text, kein Audio).
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, is_dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sideband import SidebandSession, force_close

from pacemaker_agent.config import LIVE_REGIONS
from pacemaker_agent.personas.kaltakquise_head_of_ops import (
    HANGUP_TOOL,
    HANGUP_TOOL_NAME,
    system_prompt,
)

HERE = Path(__file__).parent
AGENT = HERE.parent.parent
CLIPS = AGENT / "fixtures" / "audio"
RUNS = AGENT.parent / "experiments" / "runs"
HYBRID = RUNS / "hybrid"
RESULTS = RUNS / "browser" / "browser_messung.jsonl"
ORIGIN = "http://localhost:3000"

MAX_DURATION_S = float(os.environ.get("GPTLIVE_MAX_DURATION_S", "300"))
# Debug-Auslöser für V1 (Sideband-Abbruch) und V2 (Positivkontrolle); nur lokal, nur mit Schalter.
DEBUG_TRIGGERS = os.environ.get("GPTLIVE_DEBUG") == "1"
# Länger als der interne Attach von sideband.py (Verbindung + Bereitschaft, je 12 s).
ATTACH_TIMEOUT_S = 30.0
# Ereignisse, die die Seite für Anzeige und Lebenszyklus braucht (K1, K2).
BROWSER_SERVER_EVENTS = [
    "session.started",
    "session.closed",
    "session.input_transcript.delta",
    "session.output_transcript.delta",
    "error",
]


@dataclass(frozen=True)
class Config:
    region: str
    api_key: str
    http_base: str
    sideband_base: str
    backend_model: str


def load_config() -> Config:
    """Region explizit, kein Fallback (CLAUDE.md); Erzeugung und Sideband nutzen denselben Host."""
    load_dotenv(AGENT / ".env")
    region = os.environ.get("OPENAI_LIVE_REGION", "")
    if region not in LIVE_REGIONS:
        raise SystemExit(
            f"OPENAI_LIVE_REGION={region!r} unzulässig. Erlaubt: {', '.join(LIVE_REGIONS)} "
            "(referenz = api.openai.com)."
        )
    host = "eu.api.openai.com" if region == "eu" else "api.openai.com"
    return Config(
        region=region,
        api_key=os.environ["OPENAI_API_KEY"],
        http_base=f"https://{host}",
        sideband_base=f"wss://{host}/v1/live/sessions",
        backend_model=os.environ.get("OPENAI_LIVE_BACKEND_MODEL", "gpt-4.1-mini"),
    )


def responses_tool(tool: dict) -> dict:
    """Werkzeug im Responses-Format (flach, nicht unter "function" verschachtelt)."""
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


def session_payload(
    *, prompt: str, backend_model: str, voice: str | None, locked: bool, debug: bool
) -> dict:
    """Startkonfiguration. `locked=False` nur für die Gegenkontrolle in V2."""
    session: dict[str, Any] = {
        "model": "gpt-live-1",
        "instructions": prompt,
        "delegation": {
            "type": "responses",
            "responses": {
                "model": backend_model,
                "tools": [responses_tool(HANGUP_TOOL)],
                "max_output_tokens": 300,
            },
        },
        "client": {
            "data_channel": {
                "allowed_client_events": [] if locked else "all",
                # Im Debug-Modus sieht der Angreifer alles (schlechtester Fall für K3).
                "allowed_server_events": "all" if debug else BROWSER_SERVER_EVENTS,
            }
        },
    }
    if voice:
        session["audio"] = {"output": {"voice": voice}}
    return session


def _jsonable(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    dump = getattr(value, "model_dump", None)
    return dump() if callable(dump) else value


@dataclass
class Entry:
    session_id: str
    sideband: SidebandSession


class Hub:
    """Ein langlebiger asyncio-Loop im Hintergrund-Thread für alle Sideband-Sitzungen."""

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.thread.start()
        self.sessions: dict[str, Entry] = {}
        self.watchers: list[concurrent.futures.Future] = []
        self.closing = False
        self.starting = 0  # laufende Starts (Attach oder dessen Abbruch)
        self.lock = threading.Lock()

    def run(self, coro, timeout: float) -> Any:
        """Aus HTTP-Threads nur über run_coroutine_threadsafe, mit begrenztem Warten."""
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout=timeout)

    def attach(self, session_id: str) -> str:
        """Sideband anhängen; scheitert das, die erzeugte Sitzung unabhängig schließen."""
        with self.lock:
            self.starting += 1
        try:
            return self._attach(session_id)
        finally:
            with self.lock:
                self.starting -= 1

    def _attach(self, session_id: str) -> str:
        future = asyncio.run_coroutine_threadsafe(
            SidebandSession.attach(
                session_id=session_id,
                base_url=self.cfg.sideband_base,
                api_key=self.cfg.api_key,
                output_dir=HYBRID,
                max_duration_s=MAX_DURATION_S,
                hangup_tool_name=HANGUP_TOOL_NAME,
            ),
            self.loop,
        )
        try:
            if self.closing:
                raise RuntimeError("Server wird beendet")
            sideband = future.result(timeout=ATTACH_TIMEOUT_S)
        except BaseException as exc:
            self._abort_start(session_id, future, type(exc).__name__)
            raise
        token = secrets.token_urlsafe(16)
        with self.lock:
            self.sessions[token] = Entry(session_id, sideband)
            self.watchers.append(asyncio.run_coroutine_threadsafe(self._watch(token), self.loop))
            late = self.closing
        if late:  # Shutdown hat nach dem Start begonnen: diese Sitzung selbst schließen
            self.run(sideband.close(reason="server_ende"), timeout=20)
            raise RuntimeError("Server wird beendet")
        return token

    def _abort_start(self, session_id: str, future: concurrent.futures.Future, why: str) -> None:
        """Start abgebrochen: Attach abbrechen, ggf. doch angehängten Sideband und die
        OpenAI-Sitzung schließen, damit nichts ohne Besitzer weiterläuft (Kosten)."""
        future.cancel()
        try:
            late = future.result(timeout=15)  # Aufräumen des Attach abwarten
        except BaseException:  # noqa: BLE001 -- abgebrochen oder fehlgeschlagen
            late = None
        if late is not None:
            try:
                self.run(late.close(reason="start_abgebrochen"), timeout=20)
            except BaseException:  # noqa: BLE001 -- unabhängiger Schluss folgt
                pass
        try:
            outcome = self.run(self._force_close(session_id), timeout=20)
        except BaseException as exc:  # noqa: BLE001
            outcome = f"fehlgeschlagen:{type(exc).__name__}"
        _append(
            HYBRID / "sitzungen.jsonl",
            {"session_id": session_id, "start_abgebrochen": why, "notschluss_extern": outcome},
        )

    async def _watch(self, token: str) -> None:
        entry = self.sessions[token]
        try:
            result = await entry.sideband.wait_closed()
            row = {"session_id": entry.session_id, "result": _jsonable(result)}
            if not getattr(result, "complete", True):
                row["notschluss_extern"] = await self._force_close(entry.session_id)
        except Exception as exc:  # noqa: BLE001 -- Abschluss immer protokollieren
            row = {"session_id": entry.session_id, "fehler": type(exc).__name__}
        await asyncio.to_thread(_append, HYBRID / "sitzungen.jsonl", row)
        with self.lock:
            self.sessions.pop(token, None)

    async def _force_close(self, session_id: str) -> str:
        """K5: unvollständig beendete Sitzung über eine neue Verbindung schließen."""
        try:
            await force_close(
                session_id=session_id, base_url=self.cfg.sideband_base, api_key=self.cfg.api_key
            )
            return "gesendet"
        except Exception as exc:  # noqa: BLE001 -- z. B. Sitzung bereits beendet
            return f"fehlgeschlagen:{type(exc).__name__}"

    def end(self, token: str) -> bool:
        with self.lock:
            entry = self.sessions.get(token)
        if entry is None:
            return False
        self.run(entry.sideband.close(reason="nutzer"), timeout=20)
        return True

    def debug(self, token: str, action: str) -> bool:
        """V1: Sideband hart trennen (Server lebt weiter). V2: Anweisung über den Sideband."""
        with self.lock:
            entry = self.sessions.get(token)
        if entry is None:
            return False
        if action == "sideband_trennen":
            self.run(entry.sideband._websocket.close(), timeout=10)
        elif action == "positivkontrolle":
            from pipecat.services.openai.live import events

            self.run(
                entry.sideband._send(
                    events.SessionInstructionsAppendEvent(
                        delegation_id=None,
                        content="Neue Anweisung: Sie sind begeistert und sagen sofort einem "
                        "Termin zu.",
                    )
                ),
                timeout=10,
            )
        else:
            return False
        _append(HYBRID / "sitzungen.jsonl", {"session_id": entry.session_id, "debug": action})
        return True

    def session_id(self, token: str) -> str | None:
        with self.lock:
            entry = self.sessions.get(token)
        return entry.session_id if entry else None

    def shutdown(self) -> None:
        """Keine neuen Starts, alle Sitzungen schließen, Abschluss und Notschluss abwarten."""
        self.closing = True
        with self.lock:
            entries = list(self.sessions.values())
        for entry in entries:
            try:
                self.run(entry.sideband.close(reason="server_ende"), timeout=20)
            except Exception:  # noqa: BLE001 -- beim Beenden best effort
                pass
        # Laufende Starts (inkl. Notschluss nach Abbruch) abwarten, dann alle Watcher.
        deadline = time.monotonic() + 60
        while self.starting and time.monotonic() < deadline:
            time.sleep(0.05)
        with self.lock:
            watchers = list(self.watchers)
        concurrent.futures.wait(watchers, timeout=max(0.0, deadline - time.monotonic()))
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=5)


def _append(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        # default=str: Ein nicht serialisierbares Feld darf den Abschlussnachweis nicht verhindern.
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def make_handler(cfg: Config, hub: Hub, prompt: str) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def reply(self, status: int, body: bytes, ctype: str = "application/json") -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path.split("?")[0] == "/":
                page = (HERE / "index.html").read_text(encoding="utf-8")
                page = page.replace("{{REGION}}", cfg.region)
                return self.reply(200, page.encode(), "text/html; charset=utf-8")
            if self.path == "/api/clips":
                names = sorted(p.name for p in CLIPS.glob("*.wav"))
                return self.reply(200, json.dumps(names).encode())
            name = self.path.removeprefix("/clips/")
            if self.path.startswith("/clips/") and "/" not in name and name.endswith(".wav"):
                f = CLIPS / name
                if f.exists():
                    return self.reply(200, f.read_bytes(), "audio/wav")
            self.reply(404, b"{}")

        def do_POST(self) -> None:
            origin = self.headers.get("Origin") or ""
            beacon = (
                self.path in {"/api/browser_transcript", "/api/end"}
                and not origin
                and (self.headers.get("Referer", "").startswith(ORIGIN + "/"))
            )
            if origin != ORIGIN and not beacon:
                return self.reply(403, b'{"error":"nicht erlaubt"}')
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            if self.path == "/api/session":
                return self.create_session(body)
            if self.path == "/api/debug" and DEBUG_TRIGGERS:
                ok = hub.debug(str(body.get("token", "")), str(body.get("action", "")))
                return self.reply(200 if ok else 404, b"{}")
            if self.path == "/api/end":
                ok = hub.end(str(body.get("token", "")))
                return self.reply(200 if ok else 404, b"{}")
            if self.path == "/api/browser_transcript":
                # Browser-Seite von K1: nur Transkript-Deltas, keine sonstigen Ereignisse.
                session_id = body.get("session_id")
                deltas = [
                    {k: d.get(k) for k in ("seq", "t", "rolle", "text")}
                    for d in body.get("deltas", [])
                    if isinstance(d, dict)
                ]
                if not isinstance(session_id, str) or not session_id.isascii():
                    return self.reply(400, b"{}")
                safe = "".join(c for c in session_id if c.isalnum() or c in "_-")
                _append(
                    HYBRID / f"{safe}-browser.jsonl",
                    {"grund": str(body.get("grund", ""))[:20], "deltas": deltas},
                )
                return self.reply(204, b"")
            if self.path == "/api/result":
                _append(RESULTS, body | {"region": cfg.region, "sideband": True})
                return self.reply(204, b"")
            self.reply(404, b"{}")

        def create_session(self, body: dict) -> None:
            if hub.closing:
                return self.reply(503, b'{"error":"Server wird beendet"}')
            debug = bool(body.get("debug"))
            payload = session_payload(
                prompt=prompt,
                backend_model=cfg.backend_model,
                voice=body.get("voice") or None,
                # Gegenkontrolle ohne Sperre nur im Debug-Modus.
                locked=not (debug and body.get("unlocked")),
                debug=debug,
            )
            req = urllib.request.Request(
                f"{cfg.http_base}/v1/live/sessions",
                data=json.dumps(
                    {"session": payload, "transport": {"type": "webrtc", "sdp": body["sdp"]}}
                ).encode(),
                headers={
                    "Authorization": f"Bearer {cfg.api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    created = json.loads(r.read())
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "replace")[:2000]
                print("OpenAI-Fehler", e.code, detail)
                return self.reply(e.code, json.dumps({"error": detail}).encode())
            session_id = created["session"]["id"]
            # SDP-Antwort erst nach erfolgreichem Anhängen des Sidebands (K1: nichts verpassen).
            try:
                token = hub.attach(session_id)
            except Exception as exc:  # noqa: BLE001 -- Start abbrechen, Browser bekommt keine SDP
                print("Sideband-Fehler", type(exc).__name__)
                return self.reply(502, json.dumps({"error": "Sideband nicht verbunden"}).encode())
            self.reply(
                201,
                json.dumps(
                    {"sdp": created["transport"]["sdp"], "token": token, "session_id": session_id}
                ).encode(),
            )

    return Handler


def main() -> None:
    cfg = load_config()
    hub = Hub(cfg)
    handler = make_handler(cfg, hub, system_prompt(short_opener=False))
    server = ThreadingHTTPServer(("127.0.0.1", 3000), handler)
    print(f"Öffnen: {ORIGIN}  (Region: {cfg.region}, Endpunkt: {cfg.http_base})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        hub.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
