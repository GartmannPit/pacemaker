"""aiohttp-Anwendung des Hybrid-Servers (Plan §3 „HTTP“, A1, A6, A7).

Antworten enthalten nur lokale Fehlercodes und deutsche Meldungen, nie Provider- oder
Ausnahmetexte. Kein Access-Log (würde Pfade/IPs ungefiltert schreiben); Betriebsereignisse
gehen über das OpLog mit Feld-Allowlist.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from aiohttp import web

from .auth import Auth, AuthError, Overloaded, RateLimited
from .contracts import (
    BudgetStatus,
    CreateUnclear,
    OpLog,
    ProviderBlocked,
    StartFailed,
    StartRefused,
    StartResult,
)

LIMIT_SMALL = 4 * 1024
LIMIT_START = 80 * 1024
LIMIT_SDP = 64 * 1024
READ_TIMEOUT_S = 10.0
_REF = re.compile(r"[A-Za-z0-9_-]{16,64}")

MELDUNGEN = {
    "nicht_angemeldet": (401, "Bitte melden Sie sich an."),
    "anmeldung_fehlgeschlagen": (401, "Name oder Passwort ist falsch."),
    "zu_viele_versuche": (429, "Zu viele Versuche. Bitte warten Sie einen Moment."),
    "ueberlastet": (
        503,
        "Der Dienst ist gerade ausgelastet. Bitte versuchen Sie es gleich erneut.",
    ),
    "herkunft_ungueltig": (403, "Anfrage abgewiesen."),
    "anfrage_ungueltig": (400, "Die Anfrage ist ungültig."),
    "zu_gross": (413, "Die Anfrage ist zu groß."),
    "nutzer_hat_gespraech": (409, "Sie führen bereits ein Gespräch."),
    "kapazitaet_erschoepft": (
        503,
        "Gerade sind alle Plätze belegt. Bitte versuchen Sie es später.",
    ),
    "budget_erschoepft": (503, "Das Übungskontingent ist für diesen Monat aufgebraucht."),
    "starts_gesperrt": (503, "Gespräche sind vorübergehend nicht möglich."),
    "provider_gesperrt": (503, "Gespräche sind vorübergehend nicht möglich."),
    "start_fehlgeschlagen": (502, "Das Gespräch konnte nicht gestartet werden."),
    "erzeugung_ungeklaert": (504, "Das Gespräch konnte nicht sicher gestartet werden."),
    "angebot_abgelehnt": (400, "Ihr Browser hat eine ungültige Verbindung angeboten."),
    "provider_konfiguration": (503, "Gespräche sind vorübergehend nicht möglich."),
    "provider_nicht_verfuegbar": (503, "Der Sprachdienst ist gerade nicht erreichbar."),
    "nicht_gefunden": (404, "Nicht gefunden."),
    "interner_fehler": (500, "Ein interner Fehler ist aufgetreten."),
}


class Registry(Protocol):
    async def start(self, user_id: str, sdp: str, voice: str | None) -> StartResult: ...

    async def end(self, user_id: str, session_ref: str, *, reason: Any) -> bool: ...

    async def heartbeat(self, user_id: str, session_ref: str) -> Any: ...  # HeartbeatStatus | None


@dataclass(frozen=True)
class AppConfig:
    public_origin: str  # exakt, z. B. https://training.example.eu
    web_dist: Path  # gebautes web/dist (Plan Schritt 2 §3.2); Prüfung in check_web_dist()
    dev_loopback: bool = False  # unsicheres Cookie nur für http://localhost
    max_duration_s: float = 600  # nur Anzeige im Browser; durchgesetzt im Register
    voice: str | None = None  # Stimme der Persona, serverseitig fest (§4.5); None = API-Vorgabe

    @property
    def cookie_name(self) -> str:
        return "pm_login" if self.dev_loopback else "__Host-pm_login"


class Fehler(Exception):
    def __init__(self, code: str, *, retry_after: int | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.retry_after = retry_after


def _antwort(code: str, retry_after: int | None = None) -> web.Response:
    status, text = MELDUNGEN.get(code, MELDUNGEN["interner_fehler"])
    response = web.json_response({"fehler": code, "meldung": text}, status=status)
    if retry_after:
        response.headers["Retry-After"] = str(retry_after)
    return response


_ASSET = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_TYPES = {
    ".js": "text/javascript",
    ".css": "text/css",
    ".woff2": "font/woff2",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".webmanifest": "application/manifest+json",
}


def check_web_dist(dist: Path) -> None:
    """Startprüfung: index.html vorhanden, keine Symlinks im Build (kein stiller Rückfall)."""
    if not (dist / "index.html").is_file():
        raise ValueError(f"{dist}: index.html fehlt (pnpm build in web/ ausführen)")
    for root, dirs, names in os.walk(dist):
        for name in dirs + names:
            if os.path.islink(os.path.join(root, name)):
                raise ValueError(f"{dist}: Symlink im Build nicht erlaubt ({name})")


def _web_file(dist: Path, parts: list[str]) -> Path | None:
    """Datei aus dist/ oder dist/assets/ – nur flache, geprüfte Namen, keine Symlinks."""
    if not 1 <= len(parts) <= 2 or not all(_ASSET.fullmatch(p) for p in parts):
        return None
    if len(parts) == 2 and parts[0] != "assets":
        return None
    path = dist.joinpath(*parts)
    if path.suffix not in _TYPES or path.is_symlink() or not path.is_file():
        return None
    real = os.path.realpath(path)
    return path if real.startswith(os.path.realpath(dist) + os.sep) else None


def create_app(
    *,
    auth: Auth,
    registry: Registry,
    budget_status: Callable[[], BudgetStatus],
    ready: Callable[[], bool],
    config: AppConfig,
    oplog: OpLog,
) -> web.Application:
    check_web_dist(config.web_dist)
    csp = (
        "default-src 'none'; script-src 'self'; style-src 'self'; "
        "connect-src 'self'; media-src 'self' blob:; img-src 'self'; font-src 'self'; "
        "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    )
    secure = not config.dev_loopback

    @web.middleware
    async def schutz(request: web.Request, handler):
        intern = False
        try:
            response = await handler(request)
        except Fehler as exc:
            response = _antwort(exc.code, exc.retry_after)
        except web.HTTPException as exc:
            response = _antwort("nicht_gefunden" if exc.status == 404 else "anfrage_ungueltig")
        except Exception:  # keine Ausnahmetexte nach außen oder ins Log
            oplog.write("http_request", method=request.method, status=500)
            intern = True
            response = _antwort("interner_fehler")
        if request.path == "/api/end" and not intern:
            # Jede Ende-Anfrage (auch Beacon) mit Status; ohne Pfad, Body oder Header
            oplog.write("http_request", method=request.method, status=response.status)
        headers = response.headers
        headers["Content-Security-Policy"] = csp
        headers["X-Content-Type-Options"] = "nosniff"
        headers["Referrer-Policy"] = "no-referrer"
        headers["X-Frame-Options"] = "DENY"
        # Gehashte Build-Dateien dürfen lange gecacht werden; alles andere nie (§3.2).
        immutable = request.path.startswith("/assets/") and response.status == 200
        headers["Cache-Control"] = (
            "public, max-age=31536000, immutable" if immutable else "no-store"
        )
        if secure:
            headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    def origin_ok(request: web.Request) -> bool:
        return request.headers.get("Origin") == config.public_origin

    async def read_json(request: web.Request, limit: int) -> dict:
        if request.content_length is not None and request.content_length > limit:
            raise Fehler("zu_gross")
        raw = bytearray()
        try:
            async with asyncio.timeout(READ_TIMEOUT_S):
                while chunk := await request.content.read(limit + 1 - len(raw)):
                    raw += chunk  # bis EOF lesen, auch bei fragmentierten Bodies
                    if len(raw) > limit:
                        raise Fehler("zu_gross")
        except TimeoutError as exc:
            raise Fehler("anfrage_ungueltig") from exc
        try:
            data = json.loads(raw)
        except ValueError as exc:
            raise Fehler("anfrage_ungueltig") from exc
        if not isinstance(data, dict):
            raise Fehler("anfrage_ungueltig")
        return data

    def current(request: web.Request):
        login = auth.resolve(request.cookies.get(config.cookie_name))
        if login is None:
            raise Fehler("nicht_angemeldet")
        return login

    async def index(_request: web.Request) -> web.Response:
        page = await asyncio.to_thread((config.web_dist / "index.html").read_bytes)
        return web.Response(body=page, content_type="text/html", charset="utf-8")

    async def asset(request: web.Request) -> web.Response:
        path = _web_file(config.web_dist, request.path.strip("/").split("/"))
        if path is None:
            raise Fehler("nicht_gefunden")
        body = await asyncio.to_thread(path.read_bytes)
        return web.Response(body=body, content_type=_TYPES[path.suffix])

    async def healthz(_request: web.Request) -> web.Response:
        return web.json_response({"bereit": ready()}, status=200 if ready() else 503)

    async def login(request: web.Request) -> web.Response:
        if not origin_ok(request):
            raise Fehler("herkunft_ungueltig")
        body = await read_json(request, LIMIT_SMALL)
        name, password = body.get("name"), body.get("passwort")
        if not isinstance(name, str) or not isinstance(password, str) or len(password) > 1024:
            raise Fehler("anfrage_ungueltig")
        try:
            login_id = await auth.login(name, password, request.remote or "-")
        except RateLimited as exc:
            oplog.write("anmeldung", status=429)
            raise Fehler("zu_viele_versuche", retry_after=exc.retry_after) from exc
        except Overloaded as exc:
            raise Fehler("ueberlastet") from exc
        except AuthError as exc:
            oplog.write("anmeldung", status=401)
            raise Fehler("anmeldung_fehlgeschlagen") from exc
        resolved = auth.resolve(login_id)
        oplog.write("anmeldung", status=200)
        response = web.json_response({"name": resolved.name if resolved else None})
        response.set_cookie(
            config.cookie_name,
            login_id,
            path="/",
            httponly=True,
            secure=secure,
            samesite="Strict",
            max_age=12 * 3600,
        )
        return response

    async def logout(request: web.Request) -> web.Response:
        if not origin_ok(request):
            raise Fehler("herkunft_ungueltig")
        auth.logout(request.cookies.get(config.cookie_name))
        oplog.write("abmeldung")
        response = web.json_response({})
        response.del_cookie(config.cookie_name, path="/")
        return response

    async def me(request: web.Request) -> web.Response:
        return web.json_response({"name": current(request).name})

    async def status(request: web.Request) -> web.Response:
        current(request)
        state = budget_status()
        return web.json_response({"kontingent_knapp": state.warning, "gesperrt": state.blocked})

    async def start(request: web.Request) -> web.Response:
        if not origin_ok(request):
            raise Fehler("herkunft_ungueltig")
        user = current(request)
        body = await read_json(request, LIMIT_START)
        if set(body) != {"sdp"}:
            # u. a. keine debug-/unlock-Felder (A6); Stimme legt der Server fest (§4.5)
            raise Fehler("anfrage_ungueltig")
        sdp = body["sdp"]
        if not isinstance(sdp, str) or not sdp or len(sdp) > LIMIT_SDP:
            raise Fehler("anfrage_ungueltig")
        try:
            result = await registry.start(user.user_id, sdp, config.voice)
        except StartRefused as exc:
            oplog.write("start_abgewiesen", code=exc.code)
            raise Fehler(exc.code) from exc
        except (ProviderBlocked, CreateUnclear, StartFailed) as exc:
            oplog.write(
                "provider_gesperrt" if isinstance(exc, ProviderBlocked) else "start_fehlgeschlagen",
                code=exc.code,
                provider_status=getattr(exc, "provider_status", None),
                provider_code=getattr(exc, "provider_code", None),
            )
            raise Fehler(exc.code) from exc
        return web.json_response(
            {
                "session_ref": result.session_ref,
                "sdp": result.answer_sdp,
                "max_dauer_s": int(config.max_duration_s),
            }
        )

    async def end(request: web.Request) -> web.Response:
        user = current(request)
        body = await read_json(request, LIMIT_SMALL)
        ref = body.get("session_ref")
        if set(body) - {"session_ref", "grund"} or ("grund" in body and body["grund"] != "tab"):
            raise Fehler("anfrage_ungueltig")
        if not isinstance(ref, str) or not _REF.fullmatch(ref):
            raise Fehler("anfrage_ungueltig")
        origin = request.headers.get("Origin")
        if origin is not None and origin != config.public_origin:
            raise Fehler("herkunft_ungueltig")
        # Beacon beim Schließen des Tabs: Kennzeichen "grund" (Chrome sendet Origin mit) oder
        # ohne Origin; dann genügen gültiges Cookie (SameSite=Strict) plus eigene session_ref.
        # Der Browser ist nicht vertrauenswürdig: Der Grund unterscheidet nur zwei Nutzer-Enden.
        reason = "tab_geschlossen" if "grund" in body or not origin else "nutzer"
        if not await registry.end(user.user_id, ref, reason=reason):
            raise Fehler("nicht_gefunden")
        return web.json_response({})

    async def heartbeat(request: web.Request) -> web.Response:
        # Lebenszeichen der Gesprächsseite; bleibt es aus, beendet das Register die Sitzung.
        # Kein Beacon-Pfad: exakter Origin Pflicht. Nicht ins Betriebslog (alle 5 s je Nutzer).
        if not origin_ok(request):
            raise Fehler("herkunft_ungueltig")
        user = current(request)
        body = await read_json(request, LIMIT_SMALL)
        ref = body.get("session_ref")
        if set(body) != {"session_ref"} or not isinstance(ref, str) or not _REF.fullmatch(ref):
            raise Fehler("anfrage_ungueltig")
        status = await registry.heartbeat(user.user_id, ref)
        if status is None:
            raise Fehler("nicht_gefunden")  # unbekannt, fremd oder abgelaufen: gleich behandelt
        # Ende und Grund erfährt die Seite nur hier, nicht aus dem Datenkanal (§4.1, §4.2)
        return web.json_response({"zustand": status.state, "grund": status.reason})

    app = web.Application(middlewares=[schutz], client_max_size=LIMIT_START)
    app.router.add_get("/", index)
    app.router.add_get("/assets/{name}", asset)
    app.router.add_get(r"/{name:[A-Za-z0-9][A-Za-z0-9._-]*\.(?:svg|png|ico|webmanifest)}", asset)
    app.router.add_get("/healthz", healthz)
    app.router.add_post("/api/login", login)
    app.router.add_post("/api/logout", logout)
    app.router.add_get("/api/me", me)
    app.router.add_get("/api/status", status)
    app.router.add_post("/api/session", start)
    app.router.add_post("/api/end", end)
    app.router.add_post("/api/herzschlag", heartbeat)
    return app
