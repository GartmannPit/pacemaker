"""Sideband-Vertrag mit künstlichen Ereignissen und einem WebSocket ohne Netz."""

from __future__ import annotations

import asyncio
import base64
import importlib
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

AUDIO = base64.b64encode((3000).to_bytes(2, "little", signed=True) * 240).decode()
SILENCE = base64.b64encode(b"\x00\x00" * 240).decode()


class FakeWebSocket:
    def __init__(self, *, auto_close: bool = True, auto_pong: bool = True) -> None:
        self.incoming: asyncio.Queue = asyncio.Queue()
        self.sent: list[dict] = []
        self.auto_close = auto_close
        self.auto_pong = auto_pong
        self.pong: asyncio.Future | None = None
        self.receiving = False
        self.close_count = 0

    def __aiter__(self) -> FakeWebSocket:
        return self

    async def __anext__(self) -> str:
        self.receiving = True
        value = await self.incoming.get()
        if value is None:
            raise StopAsyncIteration
        if isinstance(value, Exception):
            raise value
        return value

    def feed(self, value: dict | str | Exception | None) -> None:
        self.incoming.put_nowait(json.dumps(value) if isinstance(value, dict) else value)

    async def ping(self) -> asyncio.Future:
        assert self.receiving
        self.pong = asyncio.get_running_loop().create_future()
        if self.auto_pong:
            self.pong.set_result(None)
        return self.pong

    async def send(self, data: str) -> None:
        event = json.loads(data)
        self.sent.append(event)
        if event["type"] == "session.close" and self.auto_close:
            self.feed({"type": "session.closed", "reason": "client_requested"})

    async def close(self) -> None:
        self.close_count += 1


@pytest.fixture
def module(monkeypatch):
    # Derselbe Import funktioniert im direkt gestarteten server.py als `import sideband`.
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "tools"))
    module = importlib.import_module("gptlive_browser.sideband")
    monkeypatch.setattr(module, "OUTPUT_QUIET_S", 0.03)
    monkeypatch.setattr(module, "FAREWELL_TIMEOUT_S", 0.2)
    monkeypatch.setattr(module, "ATTACH_TIMEOUT_S", 0.2)
    monkeypatch.setattr(module, "SEND_TIMEOUT_S", 0.1)
    return module


async def until(predicate) -> None:
    async with asyncio.timeout(2):
        while not predicate():
            await asyncio.sleep(0.001)


async def attach(module, monkeypatch, tmp_path, ws=None, **kwargs):
    ws = ws or FakeWebSocket()
    connect = AsyncMock(return_value=ws)
    monkeypatch.setattr(module, "websocket_connect", connect)
    session = await module.SidebandSession.attach(
        session_id="sess_mock",
        base_url="wss://eu.example.test/v1/live/sessions/",
        api_key="synthetischer-key",
        output_dir=tmp_path,
        max_duration_s=kwargs.pop("max_duration_s", 5),
        hangup_tool_name="auflegen",
        **kwargs,
    )
    return session, ws, connect


def rows(tmp_path) -> list[dict]:
    return [json.loads(line) for line in (tmp_path / "sess_mock.jsonl").read_text().splitlines()]


def response(ws, inner_type, *, delegation_id="del_mock", **kwargs) -> None:
    ws.feed(
        {
            "type": "response.event",
            "delegation_id": delegation_id,
            "event": {"type": inner_type, **kwargs},
        }
    )


def tool(ws, *, call_id="call_mock", status="completed", name="auflegen", arguments=None) -> None:
    response(
        ws,
        "response.output_item.done",
        item={
            "type": "function_call",
            "status": status,
            "call_id": call_id,
            "name": name,
            "arguments": arguments or json.dumps({"abschiedssatz": "Auf Wiederhören."}),
        },
    )


def sent(ws, event_type) -> list[dict]:
    return [event for event in ws.sent if event["type"] == event_type]


def test_attach_waits_for_receiver_and_pong_without_session_start(module, monkeypatch, tmp_path):
    async def run():
        ws = FakeWebSocket(auto_pong=False)
        task = asyncio.create_task(attach(module, monkeypatch, tmp_path, ws))
        await until(lambda: ws.pong is not None)
        assert not task.done()
        assert ws.sent == []
        ws.pong.set_result(None)
        session, _, connect = await task
        connect.assert_awaited_once_with(
            uri="wss://eu.example.test/v1/live/sessions/sess_mock/attach",
            additional_headers={"Authorization": "Bearer synthetischer-key"},
            open_timeout=0.2,
            close_timeout=2.0,
        )
        assert (await session.close(reason="nutzer")).complete
        assert [e["type"] for e in ws.sent] == ["session.close"]
        assert ws.close_count == 1

    asyncio.run(run())


def test_transcript_order_timestamps_usage_and_no_payload_persistence(
    module, monkeypatch, tmp_path
):
    async def run():
        session, ws, _ = await attach(module, monkeypatch, tmp_path)
        for kind, text, start in (
            ("input", "Guten ", 0),
            ("output", "Hallo.", 10),
            ("input", "Tag.", 20),
        ):
            ws.feed(
                {
                    "type": f"session.{kind}_transcript.delta",
                    "delta": text,
                    "start_ms": start,
                    "end_ms": start + 10,
                    "audio": "GEHEIMES_AUDIO",
                    "sdp": "GEHEIME_SDP",
                }
            )
        ws.feed({"type": "session.output_audio.delta", "delta": "GEHEIMES_AUDIO"})
        ws.feed({"type": "neu", "payload": "GEHEIMER_PAYLOAD", "client_event_id": "fremd"})
        ws.feed('{"type":"session.output_audio.delta","delta":{"geheim":"PARSEGEHEIM"}}')
        for seconds in (4, 7):
            ws.feed({"type": "session.usage.updated", "usage": {"seconds": seconds}})
        for rid in ("r1", "r1", "r2"):
            response(
                ws,
                "response.completed",
                response={
                    "id": rid,
                    "usage": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
                    "payload": "GEHEIMER_PAYLOAD",
                },
            )
        ws.feed({"type": "session.closed", "reason": "remote", "usage": {"seconds": 8}})
        result = await session.wait_closed()
        assert result.reason == "remote"
        assert not result.complete  # Parserfehler ist kein vollständiger Mitschnitt.
        assert result.usage_seconds == 8
        assert result.backend_tokens == {"input_tokens": 20, "output_tokens": 4, "total_tokens": 24}
        assert "unbekannte_bestaetigungs_id" in result.diagnostics
        transcript = [r for r in rows(tmp_path) if r["type"] == "transcript"]
        assert [(r["role"], r["text"]) for r in transcript] == [
            ("user", "Guten "),
            ("assistant", "Hallo."),
            ("user", "Tag."),
        ]
        assert [r["start_ms"] for r in transcript] == [0, 10, 20]
        assert all(r["timestamp"].endswith("+00:00") for r in rows(tmp_path))
        text = (tmp_path / "sess_mock.jsonl").read_text()
        for secret in ("GEHEIM", "PARSEGEHEIM", "synthetischer-key", "Authorization", "sdp"):
            assert secret not in text
        assert rows(tmp_path)[-1]["backend_tokens"] == result.backend_tokens

    asyncio.run(run())


def test_hangup_batches_tools_deduplicates_and_waits_for_both_outputs(
    module, monkeypatch, tmp_path
):
    async def run():
        session, ws, _ = await attach(module, monkeypatch, tmp_path)
        ws.feed(
            {
                "type": "session.delegation.created",
                "delegation": {"id": "del_mock", "target": "responses"},
            }
        )
        response(ws, "response.created")
        tool(ws, status="in_progress", call_id="ignorieren")
        tool(ws)
        tool(ws)
        tool(ws, call_id="call_zwei", name="unbekannt")
        await until(lambda: len(sent(ws, "response.item.create")) == 2)
        assert not sent(ws, "response.create")
        output = json.loads(sent(ws, "response.item.create")[0]["item"]["output"])
        assert output["abschiedssatz"] == "Auf Wiederhören."
        assert "Sprechen Sie" in output["instruction"]
        response(ws, "response.completed")
        await until(lambda: bool(sent(ws, "response.create")))
        tool(ws)  # Auch nach Abschluss desselben Aufrufs nicht erneut ausführen.
        response(ws, "response.completed")
        await asyncio.sleep(0.04)
        assert not sent(ws, "session.close")  # Vor dem ersten Abschied nicht ruhen lassen.
        ws.feed({"type": "session.output_transcript.delta", "delta": "Auf Wiederhören."})
        await asyncio.sleep(0.04)
        assert not sent(ws, "session.close")  # Transkript allein belegt kein Audio-Ende.
        ws.feed({"type": "session.output_audio.delta", "delta": AUDIO})
        await asyncio.sleep(0.02)
        ws.feed({"type": "session.output_audio.delta", "delta": AUDIO})
        await asyncio.sleep(0.02)
        assert not sent(ws, "session.close")  # Neue Ausgabe setzt die Ruhefrist zurück.
        result = await asyncio.wait_for(session.wait_closed(), 2)
        assert result.complete
        assert result.reason == "auflegen"
        assert len(sent(ws, "response.item.create")) == 2
        assert len(sent(ws, "response.create")) == 1
        assert len(sent(ws, "session.close")) == 1
        assert AUDIO not in (tmp_path / "sess_mock.jsonl").read_text()
        assert "instruction" not in (tmp_path / "sess_mock.jsonl").read_text()

    asyncio.run(run())


@pytest.mark.parametrize("speech", [True, False])
def test_continuous_silence_does_not_prevent_close_or_count_as_farewell_audio(
    module, monkeypatch, tmp_path, speech
):
    async def run():
        session, ws, _ = await attach(module, monkeypatch, tmp_path)
        tool(ws)
        response(ws, "response.completed")
        await until(lambda: bool(sent(ws, "response.create")))
        ws.feed({"type": "session.output_transcript.delta", "delta": "Auf Wiederhören."})
        if speech:
            ws.feed({"type": "session.output_audio.delta", "delta": AUDIO})

        async def silence():
            while True:
                ws.feed({"type": "session.output_audio.delta", "delta": SILENCE})
                await asyncio.sleep(0.005)

        stream = asyncio.create_task(silence())
        try:
            result = await asyncio.wait_for(session.wait_closed(), 2)
        finally:
            stream.cancel()
            await asyncio.gather(stream, return_exceptions=True)
        assert result.complete is speech
        assert ("abschied_timeout" in result.diagnostics) is not speech
        assert SILENCE not in (tmp_path / "sess_mock.jsonl").read_text()

    asyncio.run(run())


def test_farewell_timeout_marks_incomplete_and_still_closes(module, monkeypatch, tmp_path):
    async def run():
        session, ws, _ = await attach(module, monkeypatch, tmp_path)
        tool(ws)
        response(ws, "response.completed")
        result = await asyncio.wait_for(session.wait_closed(), 2)
        assert result.reason == "auflegen"
        assert not result.complete
        assert "abschied_timeout" in result.diagnostics
        assert len(sent(ws, "session.close")) == 1

    asyncio.run(run())


def test_remote_close_before_farewell_is_incomplete(module, monkeypatch, tmp_path):
    async def run():
        session, ws, _ = await attach(module, monkeypatch, tmp_path)
        tool(ws)
        response(ws, "response.completed")
        await until(lambda: bool(sent(ws, "response.create")))
        ws.feed({"type": "session.closed", "reason": "remote"})
        result = await session.wait_closed()
        assert not result.complete
        assert "abschied_vorzeitig_beendet" in result.diagnostics
        assert rows(tmp_path)[-1]["complete"] is False

    asyncio.run(run())


def test_deadline_overrides_pending_farewell(module, monkeypatch, tmp_path):
    async def run():
        session, ws, _ = await attach(module, monkeypatch, tmp_path, max_duration_s=0.04)
        tool(ws)
        response(ws, "response.completed")
        result = await asyncio.wait_for(session.wait_closed(), 2)
        assert result.reason == "zeitlimit"
        assert result.complete
        assert len(sent(ws, "session.close")) == 1
        assert "reason" not in sent(ws, "session.close")[0]  # Pipecats API-Schema.

    asyncio.run(run())


@pytest.mark.parametrize("failure", [None, RuntimeError("VERTRAULICHER_TRANSPORTFEHLER")])
def test_disconnect_is_incomplete_without_reconnect(module, monkeypatch, tmp_path, failure):
    async def run():
        session, ws, connect = await attach(module, monkeypatch, tmp_path)
        ws.feed({"type": "session.input_transcript.delta", "delta": "Test"})
        ws.feed(failure)
        result = await asyncio.wait_for(session.wait_closed(), 2)
        assert result.reason == "unvollstaendig"
        assert not result.complete
        assert rows(tmp_path)[-1]["reason"] == "unvollstaendig"
        assert "VERTRAULICH" not in (tmp_path / "sess_mock.jsonl").read_text()
        assert connect.await_count == 1
        assert ws.close_count == 1
        assert await session.close(reason="spaeter") is result

    asyncio.run(run())


def test_close_idempotent_receives_until_closed_and_stops_tools(module, monkeypatch, tmp_path):
    async def run():
        session, ws, _ = await attach(
            module, monkeypatch, tmp_path, FakeWebSocket(auto_close=False)
        )
        first = asyncio.create_task(session.close(reason="nutzer", timeout_s=1))
        await until(lambda: bool(sent(ws, "session.close")))
        second = asyncio.create_task(session.close(reason="tab", timeout_s=0.001))
        assert not first.done()
        tool(ws)
        response(ws, "response.completed")
        ws.feed({"type": "session.output_transcript.delta", "delta": "Letztes Fragment."})
        ws.feed({"type": "session.closed", "reason": "client_requested"})
        a, b = await asyncio.gather(first, second)
        assert a is b is await session.wait_closed()
        assert a.reason == "nutzer" and a.complete
        assert not sent(ws, "response.item.create")
        assert not sent(ws, "response.create")
        assert len(sent(ws, "session.close")) == 1
        assert any(r.get("text") == "Letztes Fragment." for r in rows(tmp_path))
        assert await session.close(reason="wiederholt") is a

    asyncio.run(run())


def test_close_timeout_and_cancellation_of_waiter(module, monkeypatch, tmp_path):
    async def run():
        session, ws, _ = await attach(
            module, monkeypatch, tmp_path, FakeWebSocket(auto_close=False)
        )
        waiter = asyncio.create_task(session.close(reason="nutzer", timeout_s=0.03))
        await until(lambda: bool(sent(ws, "session.close")))
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        result = await asyncio.wait_for(session.wait_closed(), 2)
        assert not result.complete
        assert result.reason == "unvollstaendig"
        assert "session_closed_timeout" in result.diagnostics
        assert len(sent(ws, "session.close")) == 1
        assert ws.close_count == 1

    asyncio.run(run())


@pytest.mark.parametrize("mode", ["connect", "pong", "cancel"])
def test_attach_failure_propagates_and_cleans_up(module, monkeypatch, tmp_path, mode):
    async def run():
        ws = FakeWebSocket(auto_pong=mode not in ("pong", "cancel"))
        if mode == "connect":
            monkeypatch.setattr(module, "websocket_connect", AsyncMock(side_effect=RuntimeError))
            with pytest.raises(RuntimeError):
                await module.SidebandSession.attach(
                    session_id="sess_mock",
                    base_url="wss://eu.example.test/v1/live/sessions",
                    api_key="mock",
                    output_dir=tmp_path,
                    max_duration_s=1,
                    hangup_tool_name="auflegen",
                )
            return
        task = asyncio.create_task(attach(module, monkeypatch, tmp_path, ws))
        if mode == "cancel":
            await until(lambda: ws.pong is not None)
            task.cancel()
        with pytest.raises((TimeoutError, RuntimeError, asyncio.CancelledError)):
            await asyncio.wait_for(task, 2)
        assert ws.close_count == 1
        assert rows(tmp_path)[-1]["complete"] is False
        assert "NICHT_PROTOKOLLIEREN" not in (tmp_path / "sess_mock.jsonl").read_text()

    asyncio.run(run())


@pytest.mark.parametrize("arguments", ["{", "[]", '{"abschiedssatz":3}'])
def test_invalid_tool_arguments_return_error_without_hangup(
    module, monkeypatch, tmp_path, arguments
):
    async def run():
        session, ws, _ = await attach(module, monkeypatch, tmp_path)
        tool(ws, arguments=arguments)
        response(ws, "response.completed")
        await until(lambda: bool(sent(ws, "response.create")))
        assert "error" in json.loads(sent(ws, "response.item.create")[0]["item"]["output"])
        result = await session.close(reason="nutzer")
        assert not result.complete
        assert "ungueltige_auflegen_argumente" in result.diagnostics

    asyncio.run(run())


def test_persistence_failure_terminates_session(module, monkeypatch, tmp_path):
    async def run():
        monkeypatch.setattr(module, "_append_record", lambda *_: (_ for _ in ()).throw(OSError()))
        session, ws, _ = await attach(module, monkeypatch, tmp_path)
        result = await asyncio.wait_for(session.wait_closed(), 2)
        assert not result.complete
        assert result.reason == "unvollstaendig"
        assert "persistenz_fehler" in result.diagnostics
        assert ws.close_count == 1

    asyncio.run(run())


@pytest.mark.parametrize("phase", ["tool", "close", "transport_close"])
def test_send_and_transport_close_failures_are_incomplete(module, monkeypatch, tmp_path, phase):
    async def run():
        session, ws, _ = await attach(module, monkeypatch, tmp_path)
        if phase == "transport_close":
            ws.close = AsyncMock(side_effect=RuntimeError("NICHT_SPEICHERN"))
        else:
            ws.send = AsyncMock(side_effect=RuntimeError("NICHT_SPEICHERN"))
        if phase == "tool":
            tool(ws)
            result = await session.wait_closed()
        else:
            result = await session.close(reason="nutzer")
        assert not result.complete
        assert "NICHT_SPEICHERN" not in (tmp_path / "sess_mock.jsonl").read_text()

    asyncio.run(run())


def test_server_error_is_recorded_without_text_and_not_fatal(module, monkeypatch, tmp_path):
    # V2: abgewiesene Browserbefehle dürfen den Sideband nicht beenden.
    async def run() -> None:
        session, ws, _ = await attach(module, monkeypatch, tmp_path)
        ws.feed(
            {
                "type": "error",
                "error": {
                    "type": "invalid_request_error",
                    "code": "client_event_not_allowed",
                    "message": "NICHT_PROTOKOLLIEREN",
                    "client_event_id": "fremd",
                },
            }
        )
        ws.feed({"type": "session.instructions.appended", "client_event_id": "fremd"})
        await until(lambda: "server_fehler" in session._diagnostics)
        assert not session._terminal.is_set()
        await asyncio.wait_for(session.close(reason="test"), 2)
        text = (tmp_path / "sess_mock.jsonl").read_text()
        assert "NICHT_PROTOKOLLIEREN" not in text
        control = [r for r in rows(tmp_path) if r.get("type") == "steuerereignis"]
        assert [(r["event"], r["eigen"]) for r in control] == [
            ("error", False),
            ("session.instructions.appended", False),
        ]
        assert control[0]["code"] == "client_event_not_allowed"

    asyncio.run(run())


def test_emergency_close_when_sideband_fails_without_close(module, monkeypatch, tmp_path):
    # K5: Bricht der Sideband ab (hier: Persistenzfehler), wird die Sitzung trotzdem geschlossen.
    async def run() -> None:
        session, ws, _ = await attach(
            module, monkeypatch, tmp_path, FakeWebSocket(auto_close=False)
        )
        session._fail("test_abbruch")
        session._stop_receiver()
        result = await asyncio.wait_for(session.wait_closed(), 2)
        assert not result.complete
        assert "notschluss_gesendet" in result.diagnostics
        assert len(sent(ws, "session.close")) == 1

    asyncio.run(run())
