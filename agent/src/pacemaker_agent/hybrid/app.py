"""aiohttp-Anwendung des Hybrid-Servers (Plan §3 „HTTP“, A1, A6, A7).

Antworten enthalten nur lokale Fehlercodes und deutsche Meldungen, nie Provider- oder
Ausnahmetexte. Kein Access-Log (würde Pfade/IPs ungefiltert schreiben); Betriebsereignisse
gehen über das OpLog mit Feld-Allowlist.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from importlib.resources import files
from typing import Any, Protocol

from aiohttp import web

from .auth import Auth, AuthError, Overloaded, RateLimited
from .contracts import (
    VOICES,
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


@dataclass(frozen=True)
class AppConfig:
    public_origin: str  # exakt, z. B. https://training.example.eu
    dev_loopback: bool = False  # unsicheres Cookie nur für http://localhost

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


def _page() -> tuple[bytes, str, str]:
    html = files("pacemaker_agent.hybrid").joinpath("static/index.html").read_text("utf-8")

    def digest(tag: str) -> str:
        block = re.search(rf"<{tag}>(.*?)</{tag}>", html, re.S)
        raw = hashlib.sha256((block.group(1) if block else "").encode()).digest()
        return "'sha256-" + base64.b64encode(raw).decode() + "'"

    return html.encode(), digest("script"), digest("style")


def create_app(
    *,
    auth: Auth,
    registry: Registry,
    budget_status: Callable[[], BudgetStatus],
    ready: Callable[[], bool],
    config: AppConfig,
    oplog: OpLog,
) -> web.Application:
    page, script_hash, style_hash = _page()
    csp = (
        "default-src 'none'; "
        f"script-src {script_hash}; style-src {style_hash}; "
        "connect-src 'self'; media-src 'self' blob:; img-src 'self'; "
        "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    )
    secure = not config.dev_loopback

    @web.middleware
    async def schutz(request: web.Request, handler):
        try:
            response = await handler(request)
        except Fehler as exc:
            response = _antwort(exc.code, exc.retry_after)
        except web.HTTPException as exc:
            response = _antwort("nicht_gefunden" if exc.status == 404 else "anfrage_ungueltig")
        except Exception:  # keine Ausnahmetexte nach außen oder ins Log
            oplog.write("http_request", method=request.method, status=500)
            response = _antwort("interner_fehler")
        headers = response.headers
        headers["Content-Security-Policy"] = csp
        headers["X-Content-Type-Options"] = "nosniff"
        headers["Referrer-Policy"] = "no-referrer"
        headers["X-Frame-Options"] = "DENY"
        headers["Cache-Control"] = "no-store"
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
        return web.Response(body=page, content_type="text/html", charset="utf-8")

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
        if set(body) - {"sdp", "stimme"}:
            raise Fehler("anfrage_ungueltig")  # u. a. keine debug-/unlock-Felder (A6)
        sdp, voice = body.get("sdp"), body.get("stimme")
        if not isinstance(sdp, str) or not sdp or len(sdp) > LIMIT_SDP:
            raise Fehler("anfrage_ungueltig")
        if voice is not None and voice not in VOICES:
            raise Fehler("anfrage_ungueltig")
        try:
            result = await registry.start(user.user_id, sdp, voice)
        except StartRefused as exc:
            raise Fehler(exc.code) from exc
        except (ProviderBlocked, CreateUnclear, StartFailed) as exc:
            raise Fehler(exc.code) from exc
        return web.json_response({"session_ref": result.session_ref, "sdp": result.answer_sdp})

    async def end(request: web.Request) -> web.Response:
        user = current(request)
        body = await read_json(request, LIMIT_SMALL)
        ref = body.get("session_ref")
        if not isinstance(ref, str) or not _REF.fullmatch(ref):
            raise Fehler("anfrage_ungueltig")
        origin = request.headers.get("Origin")
        if origin is not None and origin != config.public_origin:
            raise Fehler("herkunft_ungueltig")
        # Ohne Origin nur als Beacon: gültiges Cookie (SameSite=Strict) plus eigene session_ref
        reason = "nutzer" if origin else "tab_geschlossen"
        if not await registry.end(user.user_id, ref, reason=reason):
            raise Fehler("nicht_gefunden")
        return web.json_response({})

    app = web.Application(middlewares=[schutz], client_max_size=LIMIT_START)
    app.router.add_get("/", index)
    app.router.add_get("/healthz", healthz)
    app.router.add_post("/api/login", login)
    app.router.add_post("/api/logout", logout)
    app.router.add_get("/api/me", me)
    app.router.add_get("/api/status", status)
    app.router.add_post("/api/session", start)
    app.router.add_post("/api/end", end)
    return app
