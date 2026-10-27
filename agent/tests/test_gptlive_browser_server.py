"""Server des Hybrid-Prototyps (agent/tools/gptlive_browser/server.py), ohne Netz."""

from __future__ import annotations

import asyncio
import importlib
import io
import json
import sys
import types
from pathlib import Path
from unittest.mock import Mock

import pytest

TOOL_DIR = Path(__file__).resolve().parents[1] / "tools" / "gptlive_browser"


class FakeSideband:
    attached: list[dict] = []
    closed: list[str] = []
    forced: list[str] = []

    def __init__(self) -> None:
        self.done = asyncio.Event()

    @classmethod
    async def attach(cls, **kwargs):
        cls.attached.append(kwargs)
        return cls()

    async def close(self, *, reason: str, timeout_s: float = 12.0):
        FakeSideband.closed.append(reason)
        self.done.set()
        return {"reason": reason, "complete": True}

    async def wait_closed(self):
        await self.done.wait()
        return {"reason": FakeSideband.closed[-1], "complete": True}


@pytest.fixture
def server(monkeypatch):
    async def force_close(**kwargs):
        FakeSideband.forced.append(kwargs["session_id"])

    fake = types.SimpleNamespace(SidebandSession=FakeSideband, force_close=force_close)
    monkeypatch.setitem(sys.modules, "sideband", fake)
    monkeypatch.syspath_prepend(str(TOOL_DIR))
    sys.modules.pop("server", None)
    module = importlib.import_module("server")
    yield module
    sys.modules.pop("server", None)


def test_payload_locks_data_channel_and_registers_hangup(server) -> None:
    payload = server.session_payload(
        prompt="P", backend_model="gpt-4.1-mini", voice=None, locked=True, debug=False
    )
    channel = payload["client"]["data_channel"]
    assert channel["allowed_client_events"] == []
    assert channel["allowed_server_events"] == server.BROWSER_SERVER_EVENTS
    responses = payload["delegation"]["responses"]
    assert "store" not in responses  # von der Live-API abgelehnt (unknown_parameter)
    tool = responses["tools"][0]
    assert tool["type"] == "function" and tool["name"] == server.HANGUP_TOOL_NAME
    assert "function" not in tool  # Responses-Format ist flach
    assert tool["parameters"]["required"] == ["abschiedssatz"]
    assert "audio" not in payload


def test_unlocked_only_as_explicit_control(server) -> None:
    payload = server.session_payload(
        prompt="P", backend_model="m", voice="vesper", locked=False, debug=True
    )
    assert payload["client"]["data_channel"] == {
        "allowed_client_events": "all",
        "allowed_server_events": "all",
    }
    assert payload["audio"] == {"output": {"voice": "vesper"}}


@pytest.mark.parametrize("region", ["", "us", "EU"])
def test_region_required_without_fallback(server, monkeypatch, region) -> None:
    monkeypatch.setattr(server, "load_dotenv", lambda *_a, **_k: None)
    monkeypatch.setenv("OPENAI_LIVE_REGION", region)
    with pytest.raises(SystemExit):
        server.load_config()


@pytest.mark.parametrize(
    "region,host", [("eu", "eu.api.openai.com"), ("referenz", "api.openai.com")]
)
def test_same_host_for_creation_and_sideband(server, monkeypatch, region, host) -> None:
    monkeypatch.setattr(server, "load_dotenv", lambda *_a, **_k: None)
    monkeypatch.setenv("OPENAI_LIVE_REGION", region)
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    cfg = server.load_config()
    assert cfg.http_base == f"https://{host}"
    assert cfg.sideband_base == f"wss://{host}/v1/live/sessions"


def test_hub_attach_end_and_log(server, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(server, "HYBRID", tmp_path)
    FakeSideband.attached.clear()
    FakeSideband.closed.clear()
    cfg = server.Config("referenz", "k", "https://h", "wss://h/v1/live/sessions", "m")
    hub = server.Hub(cfg)
    try:
        token = hub.attach("sess_1")
        assert FakeSideband.attached[0]["session_id"] == "sess_1"
        assert FakeSideband.attached[0]["hangup_tool_name"] == server.HANGUP_TOOL_NAME
        assert hub.session_id(token) == "sess_1"
        assert hub.end(token)
        assert FakeSideband.closed == ["nutzer"]
        for _ in range(100):
            if (tmp_path / "sitzungen.jsonl").exists() and hub.session_id(token) is None:
                break
            asyncio.run(asyncio.sleep(0.01))
        assert "sess_1" in (tmp_path / "sitzungen.jsonl").read_text()
        assert not hub.end(token)  # nach Abschluss unbekannt
    finally:
        hub.shutdown()


def test_failed_attach_closes_created_session(server, monkeypatch, tmp_path) -> None:
    # Codex-Review P1: keine OpenAI-Sitzung ohne Besitzer (Kosten).
    monkeypatch.setattr(server, "HYBRID", tmp_path)
    FakeSideband.forced.clear()

    async def failing_attach(**_kwargs):
        raise ConnectionError

    monkeypatch.setattr(FakeSideband, "attach", failing_attach)
    hub = server.Hub(server.Config("referenz", "k", "https://h", "wss://h/v1/live/sessions", "m"))
    try:
        with pytest.raises(ConnectionError):
            hub.attach("sess_2")
        assert FakeSideband.forced == ["sess_2"]
        row = (tmp_path / "sitzungen.jsonl").read_text()
        assert "start_abgebrochen" in row and "ConnectionError" in row
    finally:
        hub.shutdown()


def test_shutdown_waits_for_emergency_close(server, monkeypatch, tmp_path) -> None:
    # Codex-Review P1: Shutdown darf Notschluss und Protokoll nicht abschneiden.
    monkeypatch.setattr(server, "HYBRID", tmp_path)
    FakeSideband.forced.clear()

    class Incomplete(FakeSideband):
        async def wait_closed(self):
            await self.done.wait()
            await asyncio.sleep(0.2)
            return types.SimpleNamespace(complete=False, reason="unvollstaendig")

    monkeypatch.setattr(server, "SidebandSession", Incomplete)
    hub = server.Hub(server.Config("referenz", "k", "https://h", "wss://h/v1/live/sessions", "m"))
    hub.attach("sess_3")
    hub.shutdown()
    assert FakeSideband.forced == ["sess_3"]
    assert "notschluss_extern" in (tmp_path / "sitzungen.jsonl").read_text()
    assert not hub.thread.is_alive()


def test_debug_triggers_only_for_known_session(server, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(server, "HYBRID", tmp_path)
    hub = server.Hub(server.Config("referenz", "k", "https://h", "wss://h/v1/live/sessions", "m"))
    try:
        assert not hub.debug("unbekannt", "sideband_trennen")
        token = hub.attach("sess_4")
        assert not hub.debug(token, "unbekannte_aktion")
    finally:
        hub.shutdown()


@pytest.mark.parametrize(
    "origin,referer,status",
    [
        (None, "http://localhost:3000/", 200),
        (None, "http://localhost:3000/?debug=1", 200),
        (None, None, 403),
        (None, "http://localhost:3000", 403),
        (None, "http://localhost:3000.evil/", 403),
        (None, "https://fremd.example/", 403),
        ("https://fremd.example", "http://localhost:3000/", 403),
        ("http://localhost:3000", None, 200),
    ],
)
def test_end_beacon_origin_and_referer(server, origin, referer, status) -> None:
    # Handler direkt mit Bytes aufrufen: keine Netzwerkverbindung, auch kein localhost.
    hub = types.SimpleNamespace(end=Mock(return_value=True))
    cfg = server.Config("referenz", "k", "https://h", "wss://h/v1/live/sessions", "m")
    handler_class = server.make_handler(cfg, hub, "synthetisch")
    handler = handler_class.__new__(handler_class)
    handler.path = "/api/end"
    body = json.dumps({"token": "synthetisches-token"}).encode()
    handler.headers = {"Content-Length": str(len(body)), "Content-Type": "application/json"}
    if origin is not None:
        handler.headers["Origin"] = origin
    if referer is not None:
        handler.headers["Referer"] = referer
    handler.rfile = io.BytesIO(body)
    handler.reply = Mock()
    handler.do_POST()
    assert handler.reply.call_args.args[0] == status
    if status == 200:
        hub.end.assert_called_once_with("synthetisches-token")
    else:
        hub.end.assert_not_called()
