"""Hybrid-Server Teil B: Anmeldung, Provider-Modul, Sideband, Web-App (ohne Netz)."""

from __future__ import annotations

import asyncio
import base64
import json
import stat
from pathlib import Path

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from pacemaker_agent.hybrid import auth as auth_mod
from pacemaker_agent.hybrid import live, sideband
from pacemaker_agent.hybrid.app import AppConfig, create_app
from pacemaker_agent.hybrid.contracts import (
    BudgetStatus,
    CreateUnclear,
    ProviderBlocked,
    ProviderConfig,
    StartFailed,
    StartResult,
    UserHasSession,
)

HANGUP = {
    "name": "auflegen",
    "description": "Beendet das Telefonat.",
    "properties": {"abschiedssatz": {"type": "string", "description": "Letzter Satz."}},
    "required": ["abschiedssatz"],
}


@pytest.fixture(autouse=True)
def fast_scrypt(monkeypatch):
    # Testgeschwindigkeit; Produktionsparameter prüft test_scrypt_parameters_in_hash.
    monkeypatch.setattr(auth_mod, "SCRYPT", {"n": 2**10, "r": 8, "p": 1, "dklen": 32})


# --- Anmeldung -----------------------------------------------------------------------------------


def test_scrypt_parameters_in_hash(monkeypatch) -> None:
    monkeypatch.setattr(auth_mod, "SCRYPT", {"n": 2**17, "r": 8, "p": 1, "dklen": 32})
    stored = auth_mod.hash_password("geheimes-passwort")
    assert stored.startswith("scrypt$v1$131072$8$1$")
    assert auth_mod.verify_password("geheimes-passwort", stored)
    assert not auth_mod.verify_password("falsch", stored)


def test_user_file_permissions_and_errors(tmp_path) -> None:
    users = auth_mod.UserFile(tmp_path / "u" / "nutzer.json")
    user = users.upsert("  Pit ", "ein-langes-passwort")
    assert user.name == "pit"
    assert stat.S_IMODE(users.path.stat().st_mode) == 0o600
    assert stat.S_IMODE(users.path.parent.stat().st_mode) == 0o700
    with pytest.raises(ValueError):
        users.upsert("kurz", "zu-kurz")
    users.path.write_text("{kaputt")
    with pytest.raises(ValueError):
        auth_mod.Auth(users)


def test_login_rate_limit_and_revocation(tmp_path) -> None:
    async def run() -> None:
        now = [0.0]
        users = auth_mod.UserFile(tmp_path / "nutzer.json")
        users.upsert("pit", "ein-langes-passwort")
        auth = auth_mod.Auth(users, clock=lambda: now[0])
        login_id = await auth.login("PIT", "ein-langes-passwort", "1.2.3.4")
        assert auth.resolve(login_id).name == "pit"
        for _ in range(5):
            with pytest.raises(auth_mod.AuthError):
                await auth.login("pit", "falsch-falsch-falsch", "1.2.3.4")
        with pytest.raises(auth_mod.RateLimited):
            await auth.login("pit", "ein-langes-passwort", "1.2.3.4")
        with pytest.raises(auth_mod.AuthError):  # unbekannter Nutzer: gleiche Meldung
            await auth.login("niemand", "ein-langes-passwort", "5.6.7.8")
        # Sperre und Passwortänderung per CLI (eigener Prozess) widerrufen bestehende Logins
        users.set_disabled("pit", True)
        assert auth.resolve(login_id) is None
        users.set_disabled("pit", False)
        now[0] += auth_mod.WINDOW_S
        second = await auth.login("pit", "ein-langes-passwort", "1.2.3.4")
        users.upsert("pit", "ein-neues-langes-passwort")
        assert auth.resolve(second) is None
        third = await auth.login("pit", "ein-neues-langes-passwort", "9.9.9.9")
        now[0] += auth_mod.LOGIN_TTL_S
        assert auth.resolve(third) is None

    asyncio.run(run())


# --- Provider-Modul ------------------------------------------------------------------------------


def settings(region: str = "referenz") -> live.LiveSettings:
    return live.LiveSettings(region, "test-key", "gpt-4.1-mini", "Prompt", HANGUP)


def test_payload_always_locked_and_region_explicit() -> None:
    payload = live.session_payload(settings(), "vesper")
    assert payload["client"]["data_channel"]["allowed_client_events"] == []
    assert payload["client"]["data_channel"]["allowed_server_events"] == live.BROWSER_SERVER_EVENTS
    assert payload["delegation"]["responses"]["tools"][0]["name"] == "auflegen"
    assert "store" not in payload["delegation"]["responses"]
    assert payload["store"] is False  # keine Speicherung für Forking/Aufnahme-Download
    with pytest.raises(ValueError):
        live.session_payload(settings(), "unbekannt")
    with pytest.raises(ValueError):
        live.LiveSettings("us", "k", "m", "p", HANGUP)
    eu = settings("eu")
    assert eu.http_base == "https://eu.api.openai.com"
    assert eu.sideband_base == "wss://eu.api.openai.com/v1/live/sessions"


@pytest.mark.parametrize(
    "status,body,expected",
    [
        (201, {"session": {"id": "sess_1"}, "transport": {"sdp": "ANTWORT"}}, None),
        (
            429,
            {"error": {"code": "credit_balance_exhausted", "message": "GEHEIM"}},
            ProviderBlocked,
        ),
        (400, {"error": {"code": "unknown_parameter", "message": "GEHEIM"}}, StartFailed),
        (302, {}, StartFailed),  # keine Weiterleitung folgen
        (201, {"kaputt": True}, CreateUnclear),
    ],
)
def test_create_maps_provider_answers(status, body, expected) -> None:
    async def run() -> None:
        seen = {}

        async def handler(request: web.Request) -> web.Response:
            seen["body"] = await request.json()
            seen["auth"] = request.headers.get("Authorization")
            headers = {"Location": "https://anderswo.example/"} if status == 302 else None
            return web.json_response(body, status=status, headers=headers)

        app = web.Application()
        app.router.add_post("/v1/live/sessions", handler)
        async with TestServer(app) as server:
            async with TestClient(server) as client:
                starter = live.LiveStarter(settings(), client.session)
                starter._s = type(
                    "S",
                    (),
                    {
                        **{
                            k: getattr(settings(), k)
                            for k in ("api_key", "hangup_tool", "backend_model", "prompt")
                        },
                        "http_base": str(server.make_url("")).rstrip("/"),
                        "sideband_base": "wss://x",
                    },
                )()
                if expected is None:
                    assert await starter.create("SDP", None) == ("sess_1", "ANTWORT")
                else:
                    with pytest.raises(expected) as info:
                        await starter.create("SDP", None)
                    assert "GEHEIM" not in str(info.value)
                    if expected is not CreateUnclear:
                        # Fürs Betriebslog: Status und Code, nie der Fehlertext
                        assert info.value.provider_status == status
                        assert info.value.provider_code == (body.get("error") or {}).get("code")
        assert seen["auth"] == "Bearer test-key"
        assert seen["body"]["transport"] == {"type": "webrtc", "sdp": "SDP"}

    asyncio.run(run())


def test_create_timeout_is_unclear(monkeypatch) -> None:
    async def run() -> None:
        async def slow(_request: web.Request) -> web.Response:
            await asyncio.sleep(5)
            return web.json_response({})

        monkeypatch.setattr(live, "CREATE_TIMEOUT_S", 0.2)
        app = web.Application()
        app.router.add_post("/v1/live/sessions", slow)
        async with TestServer(app) as server, TestClient(server) as client:
            starter = live.LiveStarter(settings(), client.session)
            object.__setattr__(starter, "_s", settings())
            starter._s = type(
                "S",
                (),
                {
                    "api_key": "k",
                    "hangup_tool": HANGUP,
                    "backend_model": "m",
                    "prompt": "p",
                    "http_base": str(server.make_url("")).rstrip("/"),
                },
            )()
            with pytest.raises(CreateUnclear):
                await starter.create("SDP", None)

    asyncio.run(run())


def test_sideband_refuses_redirects() -> None:
    connector = sideband.connect_attach("wss://api.openai.com/v1/live/sessions", "sess_1", "k")
    error = RuntimeError("weiterleitung")
    assert connector.process_redirect(error) is error
    with pytest.raises(ValueError):
        sideband.connect_attach("ws://unsicher/v1", "sess_1", "k")
    with pytest.raises(ValueError):
        sideband.connect_attach("wss://api.openai.com/v1", "../böse", "k")


# --- Sideband ------------------------------------------------------------------------------------

AUDIO = base64.b64encode((3000).to_bytes(2, "little", signed=True) * 240).decode()


class FakeWS:
    def __init__(self, *, closes_on_close: bool = True) -> None:
        self.inbox: asyncio.Queue = asyncio.Queue()
        self.sent: list[dict] = []
        self.closes_on_close = closes_on_close
        self.closed = False

    def feed(self, event: dict | None) -> None:
        self.inbox.put_nowait(event)

    async def send(self, raw: str) -> None:
        event = json.loads(raw)
        self.sent.append(event)
        if event["type"] == "session.close" and self.closes_on_close:
            self.feed({"type": "session.closed", "usage": {"seconds": 42.2}})

    async def ping(self):
        future = asyncio.get_running_loop().create_future()
        future.set_result(0.0)
        return future

    async def close(self) -> None:
        self.closed = True
        self.feed(None)

    def __aiter__(self):
        return self

    async def __anext__(self) -> str:
        event = await self.inbox.get()
        if event is None:
            raise StopAsyncIteration
        return json.dumps(event)


async def attached(monkeypatch, ws: FakeWS, **kwargs) -> sideband.HybridSideband:
    async def fake_connect():
        return ws

    monkeypatch.setattr(sideband, "connect_attach", lambda *_a: fake_connect())
    return await sideband.HybridSideband.attach(
        provider_id="sess_1",
        base_url="wss://x",
        api_key="k",
        deadline_s=kwargs.get("deadline_s", 30),
        idle_timeout_s=kwargs.get("idle_timeout_s", 30),
        hangup_tool_name="auflegen",
    )


def types_sent(ws: FakeWS, kind: str) -> list[dict]:
    return [e for e in ws.sent if e["type"] == kind]


def test_sideband_user_end_transcript_in_memory_and_usage(monkeypatch) -> None:
    async def run() -> None:
        ws = FakeWS()
        sb = await attached(monkeypatch, ws)
        ws.feed({"type": "session.input_transcript.delta", "delta": "Hallo"})
        ws.feed({"type": "session.output_transcript.delta", "delta": "Ja?"})
        ws.feed({"type": "session.usage.updated", "usage": {"seconds": 10.0}})
        await asyncio.sleep(0.05)
        assert [p.text for p in sb.transcript] == ["Hallo", "Ja?"]
        assert sb.usage().live_seconds == 10
        outcome = await sb.close(reason="nutzer")
        assert outcome.confirmed and outcome.reason == "nutzer"
        assert await sb.close(reason="zeitlimit") == outcome  # idempotent
        _, usage = await sb.wait_closed()
        assert usage.live_seconds == 43 and usage.final  # kumulativ ersetzt, aufgerundet
        assert len(types_sent(ws, "session.close")) == 1

    asyncio.run(run())


def test_sideband_hangup_waits_for_farewell_then_closes(monkeypatch) -> None:
    async def run() -> None:
        monkeypatch.setattr(sideband, "OUTPUT_QUIET_S", 0.1)
        ws = FakeWS()
        sb = await attached(monkeypatch, ws)
        call = {
            "type": "function_call",
            "status": "completed",
            "call_id": "c1",
            "name": "auflegen",
            "arguments": json.dumps({"abschiedssatz": "Tschüss."}),
        }
        item = {
            "type": "response.event",
            "delegation_id": "d1",
            "event": {"type": "response.output_item.done", "item": call},
        }
        ws.feed(item)
        ws.feed(item)  # doppelte call_id wird nur einmal beantwortet
        ws.feed(
            {
                "type": "response.event",
                "delegation_id": "d1",
                "event": {
                    "type": "response.completed",
                    "response": {"id": "r1", "usage": {"input_tokens": 3000, "output_tokens": 20}},
                },
            }
        )
        await asyncio.sleep(0.05)
        assert len(types_sent(ws, "response.item.create")) == 1
        assert len(types_sent(ws, "response.create")) == 1
        assert not types_sent(ws, "session.close")  # Abschied noch nicht gesprochen
        ws.feed({"type": "session.output_transcript.delta", "delta": "Tschüss."})
        ws.feed({"type": "session.output_audio.delta", "delta": AUDIO})
        outcome, usage = await asyncio.wait_for(sb.wait_closed(), 3)
        assert outcome.reason == "auflegen" and outcome.confirmed
        assert usage.backend_tokens == {"input_tokens": 3000, "output_tokens": 20}
        assert usage.backend_complete

    asyncio.run(run())


def test_sideband_idle_deadline_and_incomplete_backend(monkeypatch) -> None:
    async def run() -> None:
        ws = FakeWS()
        sb = await attached(monkeypatch, ws, idle_timeout_s=0.2)
        ws.feed(
            {
                "type": "response.event",
                "event": {"type": "response.failed", "response": {"id": "r2"}},
            }
        )
        outcome, usage = await asyncio.wait_for(sb.wait_closed(), 3)
        assert outcome.reason == "inaktiv"
        assert not usage.backend_complete
        ws2 = FakeWS()
        sb2 = await attached(monkeypatch, ws2, deadline_s=0.2)
        outcome2, _ = await asyncio.wait_for(sb2.wait_closed(), 3)
        assert outcome2.reason == "zeitlimit"

    asyncio.run(run())


def test_sideband_unconfirmed_close_and_drop(monkeypatch) -> None:
    async def run() -> None:
        monkeypatch.setattr(sideband, "CLOSE_CONFIRM_S", 0.2)
        ws = FakeWS(closes_on_close=False)
        sb = await attached(monkeypatch, ws)
        outcome = await asyncio.wait_for(sb.close(reason="nutzer"), 3)
        assert not outcome.confirmed and outcome.reason == "nutzer"
        ws2 = FakeWS(closes_on_close=False)
        sb2 = await attached(monkeypatch, ws2)
        ws2.feed(None)  # Verbindung bricht ab
        outcome2, _ = await asyncio.wait_for(sb2.wait_closed(), 3)
        assert outcome2.reason == "sideband_abbruch" and not outcome2.confirmed
        assert types_sent(ws2, "session.close")  # Notschluss versucht

    asyncio.run(run())


# --- Web-App -------------------------------------------------------------------------------------

ORIGIN = "http://localhost:8080"


class FakeRegistry:
    def __init__(self) -> None:
        self.started: list[tuple] = []
        self.ended: list[tuple] = []
        self.beats: list[tuple] = []
        self.refuse: Exception | None = None

    async def start(self, user_id, sdp, voice):
        if self.refuse:
            raise self.refuse
        self.started.append((user_id, sdp, voice))
        return StartResult(session_ref="R" * 32, answer_sdp="ANTWORT")

    async def end(self, user_id, session_ref, *, reason):
        self.ended.append((user_id, session_ref, reason))
        return session_ref == "R" * 32

    async def heartbeat(self, user_id, session_ref):
        self.beats.append((user_id, session_ref))
        return session_ref == "R" * 32


class FakeOpLog:
    def __init__(self) -> None:
        self.rows: list[tuple] = []

    def write(self, event, **fields):
        self.rows.append((event, fields))


async def client_for(tmp_path: Path, registry: FakeRegistry, oplog: FakeOpLog) -> TestClient:
    users = auth_mod.UserFile(tmp_path / "nutzer.json")
    users.upsert("pit", "ein-langes-passwort")
    app = create_app(
        auth=auth_mod.Auth(users),
        registry=registry,
        budget_status=lambda: BudgetStatus(25_000_000, 0, 0, True, False),
        ready=lambda: True,
        config=AppConfig(public_origin=ORIGIN, dev_loopback=True),
        oplog=oplog,
    )
    client = TestClient(TestServer(app))
    await client.start_server()
    return client


def test_app_login_start_end_and_headers(tmp_path) -> None:
    async def run() -> None:
        registry, oplog = FakeRegistry(), FakeOpLog()
        client = await client_for(tmp_path, registry, oplog)
        h = {"Origin": ORIGIN}
        try:
            r = await client.post("/api/session", json={"sdp": "x"}, headers=h)
            assert r.status == 401  # A1
            r = await client.post("/api/login", json={"name": "pit", "passwort": "x" * 12})
            assert r.status == 403  # ohne Origin
            r = await client.post(
                "/api/login", json={"name": "pit", "passwort": "falsch-falsch"}, headers=h
            )
            assert r.status == 401 and (await r.json())["fehler"] == "anmeldung_fehlgeschlagen"
            r = await client.post(
                "/api/login", json={"name": "pit", "passwort": "ein-langes-passwort"}, headers=h
            )
            assert r.status == 200
            assert (
                "HttpOnly" in r.headers["Set-Cookie"]
                and "SameSite=Strict" in r.headers["Set-Cookie"]
            )
            for header in ("Content-Security-Policy", "X-Content-Type-Options", "Referrer-Policy"):
                assert header in r.headers
            assert r.headers["Cache-Control"] == "no-store"
            r = await client.post("/api/session", json={"sdp": "x", "debug": True}, headers=h)
            assert r.status == 400  # A6: unbekannte Felder abgewiesen
            r = await client.post("/api/session", json={"sdp": "x", "stimme": "falsch"}, headers=h)
            assert r.status == 400
            r = await client.post(
                "/api/session",
                data="x" * (90 * 1024),
                headers={**h, "Content-Type": "application/json"},
            )
            assert r.status == 413
            r = await client.post(
                "/api/session", json={"sdp": "OFFER", "stimme": "vesper"}, headers=h
            )
            assert r.status == 200 and await r.json() == {"session_ref": "R" * 32, "sdp": "ANTWORT"}
            registry.refuse = UserHasSession()
            r = await client.post("/api/session", json={"sdp": "OFFER"}, headers=h)
            assert r.status == 409 and (await r.json())["fehler"] == "nutzer_hat_gespraech"
            registry.refuse = ProviderBlocked("credit_balance_exhausted")
            r = await client.post("/api/session", json={"sdp": "OFFER"}, headers=h)
            body = await r.json()
            assert r.status == 503 and "credit" not in json.dumps(body)
            failed = ProviderConfig("http_401:invalid_api_key")
            failed.provider_status, failed.provider_code = 401, "invalid_api_key"
            registry.refuse = failed
            r = await client.post("/api/session", json={"sdp": "OFFER"}, headers=h)
            assert r.status == 503
            starts = [row for row in oplog.rows if row[0].startswith(("start_", "provider_"))]
            assert [(event, fields.get("code")) for event, fields in starts] == [
                ("start_abgewiesen", "nutzer_hat_gespraech"),
                ("provider_gesperrt", "provider_gesperrt"),
                ("start_fehlgeschlagen", "provider_konfiguration"),
            ]
            assert starts[-1][1]["provider_status"] == 401
            assert starts[-1][1]["provider_code"] == "invalid_api_key"
            r = await client.post("/api/end", json={"session_ref": "R" * 32}, headers=h)
            assert r.status == 200 and registry.ended[-1][2] == "nutzer"
            r = await client.post("/api/end", json={"session_ref": "R" * 32})  # Beacon
            assert r.status == 200 and registry.ended[-1][2] == "tab_geschlossen"
            # Chrome sendet beim Beacon den Origin mit; das Kennzeichen entscheidet
            tab = {"session_ref": "R" * 32, "grund": "tab"}
            r = await client.post("/api/end", json=tab, headers=h)
            assert r.status == 200 and registry.ended[-1][2] == "tab_geschlossen"
            r = await client.post("/api/end", json=tab)
            assert r.status == 200 and registry.ended[-1][2] == "tab_geschlossen"
            ended = len(registry.ended)
            for falsch in (
                {"session_ref": "R" * 32, "grund": None},
                {"session_ref": "R" * 32, "grund": "nutzer"},
                {"session_ref": "R" * 32, "grund": 1},
                {"session_ref": "R" * 32, "extra": "x"},
            ):
                r = await client.post("/api/end", json=falsch, headers=h)
                assert r.status == 400
            r = await client.post("/api/end", json=tab, headers={"Origin": "https://boese.example"})
            assert r.status == 403 and len(registry.ended) == ended
            r = await client.get("/api/me")
            assert r.status == 200  # Beacon meldet nicht ab
            # Jede Ende-Anfrage landet mit Status im Betriebslog (Beacon-Diagnose)
            ends = [f["status"] for e, f in oplog.rows if e == "http_request"]
            assert ends == [200] * 4 + [400] * 4 + [403]
            r = await client.post("/api/end", json={"session_ref": "F" * 32}, headers=h)
            assert r.status == 404  # fremde Referenz
            r = await client.post(
                "/api/end",
                json={"session_ref": "R" * 32},
                headers={"Origin": "https://boese.example"},
            )
            assert r.status == 403
            r = await client.get("/api/status")
            assert (await r.json()) == {"kontingent_knapp": True, "gesperrt": False}
            r = await client.post("/api/logout", headers=h)
            r = await client.post("/api/session", json={"sdp": "OFFER"}, headers=h)
            assert r.status == 401  # Widerruf nach Logout
            logged = json.dumps(oplog.rows)
            assert "ein-langes-passwort" not in logged and "OFFER" not in logged
        finally:
            await client.close()

    asyncio.run(run())


def test_app_heartbeat_route(tmp_path) -> None:
    async def run() -> None:
        registry, oplog = FakeRegistry(), FakeOpLog()
        client = await client_for(tmp_path, registry, oplog)
        h = {"Origin": ORIGIN}
        ok = {"session_ref": "R" * 32}
        try:
            r = await client.post("/api/herzschlag", json=ok, headers=h)
            assert r.status == 401  # ohne Anmeldung
            r = await client.post(
                "/api/login", json={"name": "pit", "passwort": "ein-langes-passwort"}, headers=h
            )
            assert r.status == 200
            rows = len(oplog.rows)
            r = await client.post("/api/herzschlag", json=ok, headers=h)
            assert r.status == 200 and registry.beats[-1][1] == "R" * 32
            r = await client.post("/api/herzschlag", json={"session_ref": "F" * 32}, headers=h)
            assert r.status == 404  # unbekannt/fremd: Seite beendet lokal
            assert len(oplog.rows) == rows  # kein Betriebslog je Herzschlag
            beats = len(registry.beats)
            r = await client.post("/api/herzschlag", json=ok)
            assert r.status == 403  # kein Beacon-Pfad ohne Origin
            r = await client.post(
                "/api/herzschlag", json=ok, headers={"Origin": "https://boese.example"}
            )
            assert r.status == 403
            for falsch in (
                {},
                {"session_ref": 1},
                {"session_ref": "kurz"},
                {"session_ref": "R" * 32, "grund": "tab"},
            ):
                r = await client.post("/api/herzschlag", json=falsch, headers=h)
                assert r.status == 400
            r = await client.post(
                "/api/herzschlag",
                data="x" * (5 * 1024),
                headers={**h, "Content-Type": "application/json"},
            )
            assert r.status == 413
            assert len(registry.beats) == beats  # abgewiesene Anfragen erreichen das Register nicht
        finally:
            await client.close()

    asyncio.run(run())


def test_server_config_requires_explicit_safe_values(monkeypatch, tmp_path) -> None:
    from pacemaker_agent.hybrid import server

    monkeypatch.setattr(server, "load_dotenv", lambda *_a, **_k: None)
    base = {
        "OPENAI_LIVE_REGION": "referenz",
        "OPENAI_API_KEY": "k",
        "PACEMAKER_USERS_FILE": str(tmp_path / "u.json"),
        "PACEMAKER_STATE_DIR": str(tmp_path / "state"),
        "PACEMAKER_PUBLIC_ORIGIN": "http://localhost:8080",
        "PACEMAKER_DEV_LOOPBACK": "1",
    }
    for key, value in base.items():
        monkeypatch.setenv(key, value)
    cfg = server.load_config()
    assert cfg.app.dev_loopback and cfg.budget_micro == 25_000_000 and cfg.max_duration_s == 600
    for key, value in [
        ("PACEMAKER_DEV_LOOPBACK", "0"),  # http ohne Dev-Modus
        ("PACEMAKER_MAX_DURATION_S", "900"),
        ("OPENAI_LIVE_REGION", "us"),
    ]:
        monkeypatch.setenv(key, value)
        with pytest.raises(SystemExit):
            server.load_config()
        monkeypatch.setenv(key, base.get(key, "600"))
    monkeypatch.setenv("PACEMAKER_DEV_LOOPBACK", "1")
    monkeypatch.setenv("PACEMAKER_PUBLIC_ORIGIN", "https://training.example.eu")
    with pytest.raises(SystemExit):  # Dev-Modus nur für localhost
        server.load_config()


def test_server_build_recovers_and_serves_health(monkeypatch, tmp_path) -> None:
    from pacemaker_agent.hybrid import server

    async def run() -> None:
        monkeypatch.setattr(server, "load_dotenv", lambda *_a, **_k: None)
        # Globales Logging nicht umbiegen (eigene Tests in test_hybrid_register.py)
        monkeypatch.setattr(server, "configure_logging", lambda *_a, **_k: None)
        for key, value in {
            "OPENAI_LIVE_REGION": "referenz",
            "OPENAI_API_KEY": "k",
            "PACEMAKER_USERS_FILE": str(tmp_path / "u.json"),
            "PACEMAKER_STATE_DIR": str(tmp_path / "state"),
            "PACEMAKER_PUBLIC_ORIGIN": "http://localhost:8080",
            "PACEMAKER_DEV_LOOPBACK": "1",
        }.items():
            monkeypatch.setenv(key, value)
        app = server.build(server.load_config())
        async with TestClient(TestServer(app)) as client:
            r = await client.get("/healthz")
            assert r.status == 200 and (await r.json()) == {"bereit": True}
            r = await client.get("/")
            assert "KI-Trainingsfigur" in await r.text()

    asyncio.run(run())


# --- Korrekturen aus dem Codex-Review (Schritt 1) ----------------------------------------------


def test_review_sideband_usage_and_block(monkeypatch) -> None:
    async def run() -> None:
        ws = FakeWS(closes_on_close=False)
        sb = await attached(monkeypatch, ws)
        ws.feed({"type": "session.usage.updated", "usage": {"seconds": 30.0}})
        ws.feed(
            {
                "type": "response.event",
                "event": {"type": "response.created", "response": {"id": "r9"}},
            }
        )
        ws.feed({"type": "error", "error": {"code": "credit_balance_exhausted", "message": "x"}})
        ws.feed({"type": "session.closed"})  # ohne Usage
        _, usage = await asyncio.wait_for(sb.wait_closed(), 3)
        assert usage.final and usage.live_seconds is None  # Reserve statt Zwischenstand
        assert not usage.backend_complete  # offene Response r9
        assert sb.provider_blocked()

    asyncio.run(run())


def test_review_disable_enable_keeps_logins_revoked(tmp_path) -> None:
    async def run() -> None:
        users = auth_mod.UserFile(tmp_path / "nutzer.json")
        users.upsert("pit", "ein-langes-passwort")
        auth = auth_mod.Auth(users)
        first = await auth.login("pit", "ein-langes-passwort", "1.1.1.1")
        second = await auth.login("pit", "ein-langes-passwort", "1.1.1.1")
        users.set_disabled("pit", True)
        assert auth.resolve(first) is None
        users.set_disabled("pit", False)
        assert auth.resolve(second) is None  # auch der zweite bleibt widerrufen

    asyncio.run(run())


def test_review_payload_without_raw_errors_and_transport_unclear(monkeypatch) -> None:
    assert all(set(e) == {"type"} for e in live.BROWSER_SERVER_EVENTS)
    assert "error" not in {e["type"] for e in live.BROWSER_SERVER_EVENTS}

    class Boom:
        def post(self, *_a, **_k):
            raise ConnectionResetError("nach dem Senden")

    async def run() -> None:
        starter = live.LiveStarter(settings(), Boom())
        with pytest.raises(CreateUnclear):
            await starter.create("SDP", None)

    asyncio.run(run())


def test_review_fragmented_body_is_read_completely(tmp_path) -> None:
    async def run() -> None:
        registry, oplog = FakeRegistry(), FakeOpLog()
        client = await client_for(tmp_path, registry, oplog)
        h = {"Origin": ORIGIN}
        try:
            await client.post(
                "/api/login", json={"name": "pit", "passwort": "ein-langes-passwort"}, headers=h
            )

            async def chunks():
                for part in (b'{"sdp": "OF', b'FER", "stim', b'me": "vesper"}'):
                    yield part
                    await asyncio.sleep(0.01)

            r = await client.post(
                "/api/session", data=chunks(), headers={**h, "Content-Type": "application/json"}
            )
            assert r.status == 200 and registry.started[-1][1:] == ("OFFER", "vesper")
        finally:
            await client.close()

    asyncio.run(run())


# --- HTTP während überwachter Hintergrund-Recovery -------------------------------------------


def recovery_server_config(tmp_path):
    from pacemaker_agent.hybrid.server import ServerConfig

    return ServerConfig(
        live=settings(),
        users_file=tmp_path / "users.json",
        state_dir=tmp_path / "state",
        app=AppConfig(public_origin=ORIGIN, dev_loopback=True),
        host="127.0.0.1",
        port=0,
        max_parallel=2,
        max_duration_s=600,
        budget_micro=25_000_000,
    )


@pytest.mark.parametrize("finish_recovery", [True, False])
@pytest.mark.parametrize("transport", ["http", "in_process"])
def test_server_serves_unready_health_and_cancels_recovery_before_resources_close(
    tmp_path, monkeypatch, finish_recovery, transport
):
    from aiohttp.test_utils import make_mocked_request

    from pacemaker_agent.hybrid import server
    from pacemaker_agent.hybrid.budget import Budget
    from pacemaker_agent.hybrid.contracts import CloseOutcome, StartsBlocked
    from pacemaker_agent.hybrid.journal import Journal
    from pacemaker_agent.hybrid.sessions import SessionRegistry

    async def run():
        cfg = recovery_server_config(tmp_path)
        with Journal(cfg.state_dir) as journal:
            budget = Budget(journal)
            await budget.reserve("local")
            await journal.append(
                "session",
                local_id="local",
                user_id="user",
                provider_id="provider_synthetic",
                state="abschluss_ungeklaert",
                reason="nutzer",
            )
        calls, resources = [], {}
        entered, gate = asyncio.Event(), asyncio.Event()

        class Starter:
            def __init__(self, _cfg, http):
                resources["http"] = http

            async def force_close(self, provider_id):
                calls.append(provider_id)
                entered.set()
                try:
                    await gate.wait()
                except asyncio.CancelledError:
                    assert not resources["http"].closed
                    assert not resources["journal"]._closed
                    resources["cancelled"] = True
                    raise
                return CloseOutcome(True, "wiederanlauf")

        def registry(*args, **kwargs):
            resources["journal"] = args[2]
            # Shutdown darf den synthetisch hängenden Provider nur kurz abwarten.
            result = SessionRegistry(*args, close_timeout_s=0.2, **kwargs)
            resources["registry"] = result
            return result

        monkeypatch.setattr(server, "configure_logging", lambda *_a, **_k: None)
        monkeypatch.setattr(server, "LiveStarter", Starter)
        monkeypatch.setattr(server, "SessionRegistry", registry)
        app = server.build(cfg)
        client = TestClient(TestServer(app)) if transport == "http" else None
        runner = web.AppRunner(app, access_log=None)

        async def health():
            if client is not None:
                response = await client.get("/healthz")
                return response.status, await response.json()
            request = make_mocked_request("GET", "/healthz", app=app)
            route = await app.router.resolve(request)
            response = await route.handler(request)
            return response.status, json.loads(response.body)

        try:
            # Listener muss auch bei hängender Recovery starten können.
            await asyncio.wait_for(client.start_server() if client else runner.setup(), 1)
            await asyncio.wait_for(entered.wait(), 1)
            assert await health() == (503, {"bereit": False})
            assert not resources["registry"].ready
            with pytest.raises(StartsBlocked):
                await resources["registry"].start("user", "SDP", None)
            if finish_recovery:
                gate.set()
                async with asyncio.timeout(1):
                    while not resources["registry"].ready:
                        await asyncio.sleep(0.001)
                assert await health() == (200, {"bereit": True})
        finally:
            await asyncio.wait_for(client.close() if client else runner.cleanup(), 1)
        assert resources["http"].closed and resources["journal"]._closed
        assert resources.get("cancelled", False) == (not finish_recovery)
        assert all(t.done() for t in resources["registry"]._tasks)
        rows = [
            json.loads(line) for line in (cfg.state_dir / "journal.jsonl").read_text().splitlines()
        ]
        bookings = [r for r in rows if r["event"] == "budget_settle"]
        assert len(bookings) == (1 if finish_recovery else 0)

    asyncio.run(run())


def test_server_reports_background_recovery_failure_without_exception_text(tmp_path, monkeypatch):
    from aiohttp.test_utils import make_mocked_request

    from pacemaker_agent.hybrid import server

    async def run():
        failed = asyncio.Event()

        class BrokenRegistry:
            ready = False

            def __init__(self, *_args, **_kwargs):
                pass

            async def recover(self):
                failed.set()
                raise RuntimeError("GEHEIMER_PROVIDER_FEHLER")

            async def shutdown(self):
                pass

        monkeypatch.setattr(server, "configure_logging", lambda *_a, **_k: None)
        monkeypatch.setattr(server, "SessionRegistry", BrokenRegistry)
        cfg = recovery_server_config(tmp_path)
        app = server.build(cfg)
        runner = web.AppRunner(app, access_log=None)
        try:
            await runner.setup()
            await asyncio.wait_for(failed.wait(), 1)
            request = make_mocked_request("GET", "/healthz", app=app)
            route = await app.router.resolve(request)
            response = await route.handler(request)
            assert response.status == 503 and json.loads(response.body) == {"bereit": False}
        finally:
            await runner.cleanup()
        text = (cfg.state_dir / "betrieb.jsonl").read_text()
        rows = [json.loads(line) for line in text.splitlines()]
        assert sum(r["event"] == "wiederanlauf_fehlgeschlagen" for r in rows) == 1
        assert "GEHEIMER" not in text and "RuntimeError" not in text

    asyncio.run(run())
