"""Lebenszyklus und Kosten ausschließlich mit synthetischen Daten und Attrappen."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import UTC, datetime

import pytest

from pacemaker_agent.hybrid.budget import Budget
from pacemaker_agent.hybrid.contracts import (
    BudgetExhausted,
    CapacityExhausted,
    CloseOutcome,
    CreateUnclear,
    HeartbeatStatus,
    ProviderBlocked,
    StartFailed,
    StartsBlocked,
    UsageSummary,
    UserHasSession,
)
from pacemaker_agent.hybrid.journal import Journal, JournalError
from pacemaker_agent.hybrid.oplog import OpLog, configure_logging
from pacemaker_agent.hybrid.sessions import SessionRegistry


class Handle:
    def __init__(self) -> None:
        self.future = asyncio.get_running_loop().create_future()
        self.summary = UsageSummary(60, {"input_tokens": 100, "output_tokens": 10}, final=True)
        self.close_confirmed = True
        self.close_error = None
        self.close_gate = asyncio.Event()
        self.close_gate.set()
        self.close_calls = []

    async def close(self, *, reason):
        self.close_calls.append(reason)
        await self.close_gate.wait()
        if self.close_error:
            raise self.close_error
        outcome = CloseOutcome(self.close_confirmed, reason)
        if not self.future.done():
            self.future.set_result((outcome, self.summary))
        return outcome

    async def wait_closed(self):
        return await asyncio.shield(self.future)

    def usage(self):
        return self.summary

    def provider_blocked(self):
        return getattr(self, "blocked", False)

    async def greet(self):
        self.greet_calls = getattr(self, "greet_calls", 0) + 1
        if getattr(self, "greet_error", None):
            raise self.greet_error
        return getattr(self, "greet_result", True)

    def greeting_audio_ms(self):
        return getattr(self, "greet_ms", None)

    def greeting_rejected(self):
        return getattr(self, "greet_rejected", False)

    def finish(self, reason="auflegen", *, confirmed=True):
        self.future.set_result((CloseOutcome(confirmed, reason), self.summary))


class FakeStarter:
    def __init__(self, journal: Journal) -> None:
        self.journal = journal
        self.create_error = None
        self.attach_error = None
        self.force_error = None
        self.force_confirmed = True
        self.create_gate = asyncio.Event()
        self.create_gate.set()
        self.attach_gate = asyncio.Event()
        self.attach_gate.set()
        self.force_gate = asyncio.Event()
        self.force_gate.set()
        self.calls = []
        self.handles: list[Handle] = []
        self.attach_parameters = []

    async def create(self, sdp, voice):
        self.calls.append(("create",))
        assert any(r["event"] == "budget_reserve" for r in self.journal.records)
        await self.create_gate.wait()
        if self.create_error:
            raise self.create_error
        return f"provider_{len(self.calls)}", "SYNTHETISCHE_SDP_ANTWORT"

    async def attach(self, provider_id, *, deadline_s, idle_timeout_s):
        self.calls.append(("attach", provider_id))
        # Die ID ist auf der Platte, bevor der erste Attach-Aufruf beginnt.
        rows = read_rows(self.journal.state_dir / "journal.jsonl")
        assert rows[-1]["provider_id"] == provider_id
        self.attach_parameters.append((deadline_s, idle_timeout_s))
        await self.attach_gate.wait()
        if self.attach_error:
            raise self.attach_error
        handle = Handle()
        self.handles.append(handle)
        return handle

    async def force_close(self, provider_id):
        self.calls.append(("force", provider_id))
        await self.force_gate.wait()
        if self.force_error:
            raise self.force_error
        return CloseOutcome(self.force_confirmed, "wiederanlauf")


def read_rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def make(tmp_path, *, budget_options=None, **registry_options):
    journal = Journal(tmp_path / "state")
    log = OpLog(tmp_path / "operations.jsonl")
    budget = Budget(journal, oplog=log, **(budget_options or {}))
    starter = FakeStarter(journal)
    registry = SessionRegistry(budget, starter, journal, log, **registry_options)
    return journal, log, budget, starter, registry


async def until(predicate):
    async with asyncio.timeout(3):
        while not predicate():
            await asyncio.sleep(0.001)


def assert_closed(journal, budget, registry, *, spent=None, reason=None):
    assert registry.snapshot() == {}
    assert budget.status().bound_micro == 0
    if spent is not None:
        assert budget.status().spent_micro == spent
    rows = [r for r in journal.records if r["event"] == "session"]
    assert rows[-1]["state"] == "beendet"
    if reason:
        assert rows[-1]["reason"] == reason


@pytest.mark.parametrize("reason", ["nutzer", "tab_geschlossen", "server_ende"])
def test_end_owned_session_and_idempotent_settlement(tmp_path, reason):
    async def run():
        with Journal(tmp_path / "state") as journal:
            log = OpLog(tmp_path / "op.jsonl")
            budget = Budget(journal)
            starter = FakeStarter(journal)
            registry = SessionRegistry(budget, starter, journal, log)
            await registry.recover()
            start = await registry.start("user_a", "SYNTHETISCHE_SDP", None)
            assert len(start.session_ref) == 32
            assert start.session_ref != starter.calls[1][1]
            assert budget.status().bound_micro == 550_000
            assert not await registry.end("user_b", start.session_ref, reason=reason)
            assert not await registry.end("user_a", "fremd", reason=reason)
            assert starter.handles[0].close_calls == []
            assert registry.snapshot() == {start.session_ref: "laufend"}
            assert await registry.end("user_a", start.session_ref, reason=reason)
            assert_closed(journal, budget, registry, spent=50_056, reason=reason)
            assert await registry.heartbeat("user_a", start.session_ref) == HeartbeatStatus(
                "beendet", reason
            )
            assert not await registry.end("user_a", start.session_ref, reason=reason)
            assert (
                await budget.settle(
                    start.session_ref,
                    usage=UsageSummary(600),
                    closure=CloseOutcome(True, reason),
                )
                == 50_056
            )
            assert len([r for r in journal.records if r["event"] == "budget_settle"]) == 1
            await registry.shutdown()
            log.close()

    asyncio.run(run())


@pytest.mark.parametrize(
    "reason,confirmed,watch_error",
    [
        ("auflegen", True, None),
        ("verbindung_verloren", True, None),
        ("inaktiv", True, None),
        ("sideband_abbruch", False, None),
        ("sideband_abbruch", False, RuntimeError("GEHEIMER_PROVIDER_TEXT")),
        ("sideband_abbruch", False, ProviderBlocked()),
    ],
)
def test_watcher_for_remote_and_transport_ends(tmp_path, reason, confirmed, watch_error):
    async def run():
        journal, log, budget, starter, registry = make(tmp_path)
        await registry.recover()
        result = await registry.start("a", "SDP", None)
        if watch_error:
            starter.handles[0].future.set_exception(watch_error)
        else:
            starter.handles[0].finish(reason, confirmed=confirmed)
        await until(lambda: not registry.snapshot())
        assert_closed(journal, budget, registry, spent=50_056, reason=reason)
        assert await registry.heartbeat("a", result.session_ref) == HeartbeatStatus(
            "beendet", reason
        )
        assert sum(c[0] == "force" for c in starter.calls) == (0 if confirmed else 1)
        assert budget.status().blocked == isinstance(watch_error, ProviderBlocked)
        await registry.shutdown()
        journal.close()
        assert "GEHEIMER" not in log.path.read_text()
        log.close()

    asyncio.run(run())


@pytest.mark.parametrize("same_user", [True, False])
def test_atomic_simultaneous_starts_and_starting_places(tmp_path, same_user):
    async def run():
        journal, log, budget, starter, registry = make(tmp_path, max_parallel=1)
        await registry.recover()
        starter.create_gate.clear()
        tasks = [
            asyncio.create_task(registry.start("a" if same_user else str(i), "SDP", None))
            for i in range(8)
        ]
        await until(lambda: len(starter.calls) == 1)
        await until(lambda: sum(t.done() for t in tasks) == 7)
        assert list(registry.snapshot().values()) == ["startend"]
        assert budget.status().bound_micro == 550_000
        starter.create_gate.set()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        error_type = UserHasSession if same_user else CapacityExhausted
        assert sum(isinstance(r, error_type) for r in results) == 7
        assert sum(c[0] == "create" for c in starter.calls) == 1
        await registry.shutdown()
        assert_closed(journal, budget, registry, reason="server_ende")
        journal.close()
        log.close()

    asyncio.run(run())


def test_parallel_different_users_and_ending_places(tmp_path):
    async def run():
        journal, log, budget, starter, registry = make(tmp_path, max_parallel=2)
        await registry.recover()
        first, _second = await asyncio.gather(
            registry.start("a", "SDP", None), registry.start("b", "SDP", None)
        )
        starter.handles[0].close_gate.clear()
        ending = asyncio.create_task(registry.end("a", first.session_ref, reason="nutzer"))
        await until(lambda: "endend" in registry.snapshot().values())
        with pytest.raises(CapacityExhausted):
            await registry.start("c", "SDP", None)
        with pytest.raises(UserHasSession):
            await registry.start("a", "SDP", None)
        assert budget.status().bound_micro == 1_100_000
        assert sum(c[0] == "create" for c in starter.calls) == 2
        starter.handles[0].close_gate.set()
        assert await ending
        assert len(registry.snapshot()) == 1
        await registry.shutdown()
        assert_closed(journal, budget, registry)
        journal.close()
        log.close()

    asyncio.run(run())


@pytest.mark.parametrize(
    "error,state,bound,blocked,raised",
    [
        (StartFailed(), None, 0, False, StartFailed),
        (ProviderBlocked(), None, 0, True, ProviderBlocked),
        (CreateUnclear(), "erzeugung_ungeklaert", 550_000, False, CreateUnclear),
        (RuntimeError("GEHEIM"), "erzeugung_ungeklaert", 550_000, False, CreateUnclear),
    ],
)
def test_create_error_paths(tmp_path, error, state, bound, blocked, raised):
    async def run():
        journal, log, budget, starter, registry = make(tmp_path)
        await registry.recover()
        starter.create_error = error
        with pytest.raises(raised):  # Fehlerklasse bleibt bis zur App erhalten
            await registry.start("a", "SDP", None)
        assert list(registry.snapshot().values()) == ([state] if state else [])
        assert budget.status().bound_micro == bound
        assert budget.status().spent_micro == 0
        assert budget.status().blocked == blocked
        assert starter.calls == [("create",)]
        if blocked:
            with pytest.raises(StartsBlocked):
                await registry.start("b", "SDP", None)
            budget.set_provider_blocked(False)
            starter.create_error = None
            await registry.start("b", "SDP", None)
        await registry.shutdown()
        assert list(registry.snapshot().values()) == ([state] if state else [])
        assert "GEHEIM" not in log.path.read_text()
        journal.close()
        log.close()

    asyncio.run(run())


@pytest.mark.parametrize("confirmed", [True, False])
@pytest.mark.parametrize("blocked", [True, False])
def test_attach_failure_and_unclear_close(tmp_path, confirmed, blocked):
    async def run():
        journal, log, budget, starter, registry = make(tmp_path)
        await registry.recover()
        starter.attach_error = ProviderBlocked() if blocked else StartFailed()
        starter.force_confirmed = confirmed
        with pytest.raises(StartFailed):
            await registry.start("a", "SDP", None)
        assert budget.status().blocked == blocked
        if confirmed:
            assert_closed(journal, budget, registry, spent=550_000, reason="attach_fehler")
        else:
            assert list(registry.snapshot().values()) == ["abschluss_ungeklaert"]
            assert budget.status().bound_micro == 550_000
            assert budget.status().spent_micro == 0
        assert [c[0] for c in starter.calls] == ["create", "attach", "force"]
        await registry.shutdown()
        journal.close()
        log.close()

    asyncio.run(run())


@pytest.mark.parametrize("phase", ["create", "attach", "end"])
def test_cancelled_http_coroutine_still_cleans_up(tmp_path, phase):
    async def run():
        journal, log, budget, starter, registry = make(tmp_path)
        await registry.recover()
        if phase == "end":
            start = await registry.start("a", "SDP", None)
            starter.handles[0].close_gate.clear()
            task = asyncio.create_task(registry.end("a", start.session_ref, reason="nutzer"))
            await until(lambda: starter.handles[0].close_calls)
        else:
            gate = starter.create_gate if phase == "create" else starter.attach_gate
            gate.clear()
            task = asyncio.create_task(registry.start("a", "SDP", None))
            await until(lambda: any(c[0] == phase for c in starter.calls))
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()  # Wiederholter Abbruch zerstört keine lokale Transaktion.
        if phase == "end":
            starter.handles[0].close_gate.set()
        else:
            gate.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        await until(lambda: not registry.snapshot())
        assert_closed(journal, budget, registry, spent=50_056)
        await registry.shutdown()
        journal.close()
        log.close()

    asyncio.run(run())


@pytest.mark.parametrize("phase", ["create", "attach"])
def test_end_and_shutdown_during_start(tmp_path, phase):
    async def run():
        journal, log, budget, starter, registry = make(tmp_path)
        await registry.recover()
        gate = starter.create_gate if phase == "create" else starter.attach_gate
        gate.clear()
        start = asyncio.create_task(registry.start("a", "SDP", None))
        await until(lambda: any(c[0] == phase for c in starter.calls))
        ref = next(iter(registry.snapshot()))
        assert await registry.end("a", ref, reason="nutzer")
        assert await registry.heartbeat("a", ref) == HeartbeatStatus("endend", "nutzer")
        stop = asyncio.create_task(registry.shutdown())
        await asyncio.sleep(0)
        gate.set()
        with pytest.raises(StartFailed):
            await start
        await stop
        assert_closed(journal, budget, registry, spent=50_056, reason="nutzer")
        assert not registry.ready
        with pytest.raises(StartsBlocked):
            await registry.start("b", "SDP", None)
        journal.close()
        log.close()

    asyncio.run(run())


@pytest.mark.parametrize("force_error", [None, ProviderBlocked(), RuntimeError("GEHEIM")])
def test_close_timeout_then_force_and_retry_unconfirmed(tmp_path, force_error):
    async def run():
        journal, log, budget, starter, registry = make(tmp_path, close_timeout_s=0.02)
        await registry.recover()
        result = await registry.start("a", "SDP", None)
        starter.handles[0].close_gate.clear()
        starter.force_error = force_error
        assert await registry.end("a", result.session_ref, reason="nutzer")
        if force_error:
            assert list(registry.snapshot().values()) == ["abschluss_ungeklaert"]
            assert budget.status().bound_micro == 550_000
            assert budget.status().spent_micro == 0
            starter.force_error = None
            assert await registry.end("a", result.session_ref, reason="nutzer")
            await until(lambda: not registry.snapshot())  # Die Nachbehandlung wiederholt Close.
        assert_closed(journal, budget, registry, spent=50_056, reason="nutzer")
        await registry.shutdown()
        journal.close()
        log.close()

    asyncio.run(run())


def test_deadline_forwarding_and_registry_fallback(tmp_path):
    async def run():
        journal, log, budget, starter, registry = make(tmp_path, max_duration_s=0.08)
        await registry.recover()
        result = await registry.start("a", "SDP", None)
        deadline, idle = starter.attach_parameters[0]
        assert 0 < deadline <= 0.08  # verbleibende Sekunden (contracts.Starter.attach)
        assert idle == 120
        await until(lambda: not registry.snapshot())
        assert_closed(journal, budget, registry, reason="zeitlimit")
        assert await registry.heartbeat("a", result.session_ref) == HeartbeatStatus(
            "beendet", "zeitlimit"
        )
        await registry.shutdown()
        journal.close()
        log.close()

    asyncio.run(run())


def test_budget_limit_warning_and_no_provider_for_rejected_start(tmp_path):
    async def run():
        journal, log, budget, starter, registry = make(
            tmp_path, budget_options={"limit_micro": 1_100_000}
        )
        await registry.recover()
        await asyncio.gather(registry.start("a", "SDP", None), registry.start("b", "SDP", None))
        status = budget.status()
        assert status.bound_micro == status.limit_micro
        assert status.blocked and status.warning
        assert any(r["event"] == "budget_warnung" for r in read_rows(log.path))
        with pytest.raises(BudgetExhausted):
            await registry.start("c", "SDP", None)
        assert sum(c[0] == "create" for c in starter.calls) == 2
        await registry.shutdown()
        assert_closed(journal, budget, registry)
        assert not budget.status().warning
        journal.close()
        log.close()

    asyncio.run(run())


@pytest.mark.parametrize(
    "usage,reason,expected,estimated",
    [
        (
            UsageSummary(60, {"input_tokens": 100, "output_tokens": 10}, final=True),
            "nutzer",
            50_056,
            False,
        ),
        (UsageSummary(None, backend_complete=False, final=True), "nutzer", 550_000, True),
        (UsageSummary(0, final=True), "attach_fehler", 12_500, False),
        (UsageSummary(60, {"input_tokens": 1}, final=True), "nutzer", 100_000, True),
        (
            UsageSummary(
                60,
                {"input_tokens": 1_000_000, "output_tokens": 1_000_000},
                backend_complete=False,
                final=True,
            ),
            "nutzer",
            2_050_000,
            True,
        ),
        (UsageSummary(5), "nutzer", 550_000, True),
        (UsageSummary(600, final=True), "nutzer", 500_000, False),
    ],
)
def test_budget_costs_missing_usage_and_attach_floor(tmp_path, usage, reason, expected, estimated):
    async def run():
        with Journal(tmp_path) as journal:
            budget = Budget(journal)
            await budget.reserve("a")
            assert await budget.settle("a", usage=usage, closure=CloseOutcome(False, reason)) == 0
            assert budget.status().bound_micro == 550_000
            assert budget.status().spent_micro == 0
            amount = await budget.settle("a", usage=usage, closure=CloseOutcome(True, reason))
            assert amount == expected
            assert budget.status().spent_micro == expected
            assert budget.status().bound_micro == 0
            assert journal.records[-1]["estimated"] == estimated
            assert (
                await budget.settle("a", usage=usage, closure=CloseOutcome(True, reason)) == amount
            )

    asyncio.run(run())


def test_month_of_start_and_month_independent_open_reservations(tmp_path):
    async def run():
        now = [datetime(2026, 10, 31, 23, 59, tzinfo=UTC)]
        with Journal(tmp_path) as journal:
            budget = Budget(journal, limit_micro=1_100_000, clock=lambda: now[0])
            await budget.reserve("october")
            now[0] = datetime(2026, 11, 1, tzinfo=UTC)
            await budget.reserve("november")
            with pytest.raises(BudgetExhausted):
                await budget.reserve("rejected")
            await budget.settle(
                "october",
                usage=UsageSummary(None, backend_complete=False),
                closure=CloseOutcome(True, "nutzer"),
            )
            assert budget.status().spent_micro == 0
            assert budget.status().bound_micro == 550_000
            await budget.release_uncreated("november")
            await budget.release_uncreated("november")
            budget = Budget(journal, clock=lambda: now[0])
            assert budget.status().spent_micro == budget.status().bound_micro == 0
            now[0] = datetime(2026, 10, 31, tzinfo=UTC)
            assert budget.status().spent_micro == 550_000

    asyncio.run(run())


@pytest.mark.parametrize("state", ["startend", "laufend", "endend", "abschluss_ungeklaert"])
@pytest.mark.parametrize("confirmed", [True, False])
def test_recover_open_provider_id_before_readiness(tmp_path, state, confirmed):
    async def run():
        with Journal(tmp_path / "state") as journal:
            budget = Budget(journal)
            await budget.reserve("local")
            await journal.append(
                "session",
                local_id="local",
                user_id="a",
                provider_id="provider_synthetic",
                state=state,
                reason=None,
            )
        journal, log, budget, starter, registry = make(
            tmp_path, unclear_retry_offsets_s=(0, 0.01), unclear_deadline_s=0.04
        )
        starter.force_confirmed = confirmed
        starter.force_gate.clear()
        with pytest.raises(StartsBlocked):
            await registry.start("b", "SDP", None)
        recovery = asyncio.create_task(registry.recover())
        await until(lambda: starter.calls)
        assert not registry.ready
        assert budget.status().bound_micro == 550_000
        starter.force_gate.set()
        await recovery
        assert registry.ready
        assert_closed(journal, budget, registry, spent=550_000, reason="wiederanlauf")
        assert await registry.heartbeat("a", "local") == HeartbeatStatus("beendet", "wiederanlauf")
        assert all(c[0] == "force" for c in starter.calls)
        await registry.recover()
        await registry.shutdown()
        journal.close()
        log.close()

    asyncio.run(run())


@pytest.mark.parametrize("write_session", [True, False])
def test_recovery_unknown_creation_keeps_full_reserve(tmp_path, write_session):
    async def run():
        with Journal(tmp_path / "state") as journal:
            await Budget(journal).reserve("unknown")
            if write_session:
                await journal.append(
                    "session",
                    local_id="unknown",
                    user_id="a",
                    provider_id=None,
                    state="startend",
                    reason=None,
                )
        journal, log, budget, starter, registry = make(tmp_path)
        await registry.recover()
        assert registry.ready
        assert registry.snapshot() == {"unknown": "erzeugung_ungeklaert"}
        assert budget.status().bound_micro == 550_000
        assert budget.status().spent_micro == 0
        assert starter.calls == []
        await registry.shutdown()
        journal.close()
        log.close()

    asyncio.run(run())


@pytest.mark.parametrize("settled", [True, False])
def test_recovery_after_booking_before_final_state(tmp_path, settled):
    async def run():
        with Journal(tmp_path / "state") as journal:
            budget = Budget(journal)
            await budget.reserve("local")
            await journal.append(
                "session",
                local_id="local",
                user_id="a",
                provider_id="provider" if settled else None,
                state="startend",
                reason=None,
            )
            if settled:
                await budget.settle(
                    "local",
                    usage=UsageSummary(60, final=True),
                    closure=CloseOutcome(True, "nutzer"),
                )
            else:
                await budget.release_uncreated("local")
        journal, log, budget, starter, registry = make(tmp_path)
        await registry.recover()
        assert registry.snapshot() == {}
        assert registry.ready
        assert budget.status().bound_micro == 0
        assert budget.status().spent_micro == (50_000 if settled else 0)
        assert starter.calls == []
        await registry.shutdown()
        journal.close()
        log.close()

    asyncio.run(run())


@pytest.mark.parametrize("phase", ["reserve", "provider_id", "settle"])
def test_journal_write_failure_blocks_starts_and_never_discards_state(tmp_path, monkeypatch, phase):
    async def run():
        journal, log, budget, starter, registry = make(tmp_path)
        await registry.recover()
        original_write = journal._write

        def fail(data):
            event = json.loads(data)
            if (
                (phase == "reserve" and event["event"] == "budget_reserve")
                or (phase == "provider_id" and event.get("provider_id"))
                or (phase == "settle" and event["event"] == "budget_settle")
            ):
                raise OSError("SYNTHETISCH_VOLLER_DATENTRAEGER")
            original_write(data)

        monkeypatch.setattr(journal, "_write", fail)
        if phase == "settle":
            result = await registry.start("a", "SDP", None)
            await registry.end("a", result.session_ref, reason="nutzer")
        else:
            with pytest.raises(StartsBlocked if phase == "reserve" else StartFailed):
                await registry.start("a", "SDP", None)
        assert journal.failed and budget.status().blocked and not registry.ready
        budget.set_provider_blocked(False)
        with pytest.raises(StartsBlocked):
            await registry.start("b", "SDP", None)
        if phase == "reserve":
            assert registry.snapshot() == {}
            assert budget.status().bound_micro == 0
            assert starter.calls == []
        else:
            assert list(registry.snapshot().values()) == ["abschluss_ungeklaert"]
            assert budget.status().bound_micro == 550_000
            if phase == "provider_id":
                assert [c[0] for c in starter.calls] == ["create", "force"]
        assert budget.status().spent_micro == 0
        await registry.shutdown()
        journal.close()
        log.close()

    asyncio.run(run())


@pytest.mark.parametrize(
    "data",
    [
        b"kaputt\n",
        b"{}\n",
        b"{}",
        b"\n",
        b'{"version":9}\n',
        b'{"version":true,"event":"session"}\n',
        b'{"version":1,"event":"session","event":"session"}\n',
        b'{"version":1,"event":"session","count":NaN}\n',
    ],
)
def test_corrupt_journal_fails_closed(tmp_path, data):
    (tmp_path / "journal.jsonl").write_bytes(data)
    with pytest.raises(JournalError):
        Journal(tmp_path)
    assert (tmp_path / "journal.jsonl").read_bytes() == data


def test_process_lock_permissions_and_fsync(tmp_path, monkeypatch):
    syncs = []
    original = os.fsync

    def sync(fd):
        syncs.append(fd)
        original(fd)

    monkeypatch.setattr(os, "fsync", sync)
    with Journal(tmp_path) as journal:
        with pytest.raises(JournalError):
            Journal(tmp_path)
        asyncio.run(journal.append("budget_release", local_id="synthetic"))
        assert len(syncs) >= 3
        assert (tmp_path.stat().st_mode & 0o777) == 0o700
        assert ((tmp_path / "journal.jsonl").stat().st_mode & 0o777) == 0o600
    with Journal(tmp_path) as journal:
        assert len(journal.records) == 1


def test_semantically_corrupt_journal_does_not_reset_budget(tmp_path):
    async def run():
        with Journal(tmp_path) as journal:
            await journal.append(
                "budget_settle", local_id="missing", amount_micro=1, estimated=True
            )
        with Journal(tmp_path) as journal:
            with pytest.raises(JournalError):
                Budget(journal)
            assert journal.failed

    asyncio.run(run())


def test_oplog_allowlist_framework_exception_and_access_logs(tmp_path):
    log = OpLog(tmp_path / "operations.jsonl")
    log.write(
        "sitzung_status",
        session_ref="local_synthetic",
        state="laufend",
        reason="GEHEIM",
        sdp="GEHEIM",
        audio="GEHEIM",
        text="GEHEIM",
        authorization="GEHEIM",
        cookie="GEHEIM",
        password="GEHEIM",
        api_key="GEHEIM",
        provider_error="GEHEIM",
        count=True,
    )
    log.write("GEHEIM", message="GEHEIM")
    log.write("http_request", status=200, method="POST", duration_s=0.2, path="GEHEIM")
    log.write(
        "start_fehlgeschlagen",
        code="provider_konfiguration",
        provider_status=401,
        provider_code="invalid_api_key",
    )
    log.write("start_fehlgeschlagen", provider_status=99, provider_code="Fehler mit GEHEIM")
    root = logging.getLogger()
    previous_handlers, previous_level = root.handlers[:], root.level
    previous_loggers = [
        (logger, logger.handlers[:], logger.propagate)
        for logger in logging.Logger.manager.loggerDict.copy().values()
        if isinstance(logger, logging.Logger)
    ]
    name = "pacemaker_synthetic_framework"
    framework = logging.getLogger(name)
    previous_framework = framework.handlers[:], framework.propagate
    try:
        framework.addHandler(logging.FileHandler(tmp_path / "unfiltered.log"))
        configure_logging(log, include_loguru=False)
        framework.warning("GEHEIMER_COOKIE %s", "GEHEIMER_KEY")
        try:
            raise RuntimeError("GEHEIMER_PROVIDERFEHLER")
        except RuntimeError:
            framework.exception("GEHEIME_SDP")
        logging.getLogger("aiohttp.access").info("GEHEIMER_AUTH_HEADER")
        assert (tmp_path / "unfiltered.log").read_text() == ""
    finally:
        root.handlers[:], root.level = previous_handlers, previous_level
        for logger, handlers, propagate in previous_loggers:
            logger.handlers[:], logger.propagate = handlers, propagate
        framework.handlers[:], framework.propagate = previous_framework
        log.close()
    rows = read_rows(log.path)
    assert rows[0].keys() == {"timestamp", "event", "session_ref", "state"}
    assert rows[1]["status"] == 200
    assert rows[2]["provider_status"] == 401 and rows[2]["provider_code"] == "invalid_api_key"
    assert rows[3].keys() == {"timestamp", "event"}  # unzulässige Werte verworfen
    assert sum(r["event"] == "framework_log" for r in rows) == 3
    assert "GEHEIM" not in log.path.read_text()


def test_simultaneous_end_and_remote_hangup_settle_once(tmp_path):
    async def run():
        journal, log, budget, starter, registry = make(tmp_path)
        await registry.recover()
        result = await registry.start("a", "SDP", None)
        starter.handles[0].finish()
        await asyncio.gather(
            *(registry.end("a", result.session_ref, reason="nutzer") for _ in range(10))
        )
        await until(lambda: not registry.snapshot())
        assert_closed(journal, budget, registry, spent=50_056)
        assert len([r for r in journal.records if r["event"] == "budget_settle"]) == 1
        await registry.shutdown()
        journal.close()
        log.close()

    asyncio.run(run())


@pytest.mark.parametrize("phase", ["create", "attach", "force"])
def test_network_timeouts_keep_uncertain_reservations(tmp_path, phase):
    async def run():
        journal, log, budget, starter, registry = make(
            tmp_path, max_duration_s=0.03, close_timeout_s=0.02
        )
        await registry.recover()
        gate = getattr(starter, f"{phase}_gate")
        gate.clear()
        if phase == "force":
            result = await registry.start("a", "SDP", None)
            starter.handles[0].close_confirmed = False
            await registry.end("a", result.session_ref, reason="nutzer")
        else:
            with pytest.raises(CreateUnclear if phase == "create" else StartFailed):
                await registry.start("a", "SDP", None)
        if phase == "attach":
            assert_closed(journal, budget, registry, spent=550_000, reason="attach_fehler")
        else:
            state = "erzeugung_ungeklaert" if phase == "create" else "abschluss_ungeklaert"
            assert list(registry.snapshot().values()) == [state]
            assert budget.status().spent_micro == 0
            assert budget.status().bound_micro == 550_000
        await registry.shutdown()
        journal.close()
        log.close()

    asyncio.run(run())


def test_warning_exact_threshold_and_cumulative_live_seconds(tmp_path):
    async def run():
        with Journal(tmp_path) as journal:
            budget = Budget(journal, limit_micro=687_500)
            await budget.reserve("local")
            assert budget.status().warning  # Genau 80 Prozent, einschließlich Reserven.
            for seconds in (5, 10):
                await budget.settle(
                    "local", usage=UsageSummary(seconds), closure=CloseOutcome(False, "nutzer")
                )
            assert budget.status().bound_micro == 550_000
            assert (
                await budget.settle(
                    "local",
                    usage=UsageSummary(20, final=True),
                    closure=CloseOutcome(True, "nutzer"),
                )
                == 16_667
            )  # Kumulativ 20 Sekunden, nicht 5 + 10 + 20.

    asyncio.run(run())


def test_provider_block_of_running_session_blocks_new_starts(tmp_path):
    # Codex-Nachprüfung: Sperre sofort, nicht erst beim Ende des betroffenen Gesprächs.
    async def run():
        journal, log, budget, starter, registry = make(tmp_path)
        await registry.recover()
        await registry.start("a", "SDP", None)
        handle = next(iter(registry._sessions.values())).handle
        handle.blocked = True
        with pytest.raises(StartsBlocked):
            await registry.start("b", "SDP", None)
        assert budget.status().blocked
        await registry.shutdown()
        journal.close()
        log.close()

    asyncio.run(run())


def test_provider_block_survives_deadline_close(tmp_path):
    # Codex-Nachprüfung: Zeitlimit-Pfad entfernt die Sitzung erst nach Übernahme der Sperre.
    async def run():
        journal, log, budget, starter, registry = make(tmp_path, max_duration_s=0.08)
        await registry.recover()
        await registry.start("a", "SDP", None)
        next(iter(registry._sessions.values())).handle.blocked = True
        await until(lambda: not registry.snapshot())
        assert budget.status().blocked
        with pytest.raises(StartsBlocked):
            await registry.start("b", "SDP", None)
        await registry.shutdown()
        journal.close()
        log.close()

    asyncio.run(run())


# --- Begrenzte Nachbehandlung ungeklärter Abschlüsse ------------------------------------------


async def seed_open_sessions(tmp_path, count=1, *, reason=None):
    with Journal(tmp_path / "state") as journal:
        budget = Budget(journal)
        for i in range(count):
            local_id = f"local_{i}"
            await budget.reserve(local_id)
            await journal.append(
                "session",
                local_id=local_id,
                user_id=f"user_{i}",
                provider_id=f"provider_{i}",
                state="abschluss_ungeklaert",
                reason=reason,
            )


def test_recovery_retries_until_confirmed_and_preserves_reason(tmp_path, monkeypatch):
    async def run():
        await seed_open_sessions(tmp_path, reason="zeitlimit")
        journal, log, budget, starter, registry = make(
            tmp_path, unclear_retry_offsets_s=(0, 0.015, 0.04), unclear_deadline_s=0.08
        )
        calls = []
        started = asyncio.get_running_loop().time()

        async def force(provider_id):
            calls.append(asyncio.get_running_loop().time() - started)
            return CloseOutcome(len(calls) >= 3, "wiederanlauf")

        monkeypatch.setattr(starter, "force_close", force)
        try:
            await registry.recover()
            assert registry.ready
            assert len(calls) == 3
            assert calls[1] >= 0.015 and calls[2] >= 0.04
            assert_closed(journal, budget, registry, spent=550_000, reason="zeitlimit")
            booking = next(r for r in journal.records if r["event"] == "budget_settle")
            assert not booking.get("unconfirmed", False)
            assert not any(r["event"] == "abschluss_unbestaetigt" for r in read_rows(log.path))
        finally:
            await registry.shutdown()
            journal.close()
            log.close()

    asyncio.run(run())


@pytest.mark.parametrize("count", [1, 8])
def test_recovery_unconfirmed_shares_deadline_and_frees_places(tmp_path, monkeypatch, count):
    async def run():
        await seed_open_sessions(tmp_path, count)
        journal, log, budget, starter, registry = make(
            tmp_path,
            max_parallel=2,
            unclear_retry_offsets_s=(0, 0.02, 0.04),
            unclear_deadline_s=0.08,
        )
        active, peak = 0, 0

        async def force(provider_id):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            try:
                await asyncio.sleep(0.003)
                return CloseOutcome(False, "wiederanlauf")  # etwa anhaltender HTTP 503
            finally:
                active -= 1

        monkeypatch.setattr(starter, "force_close", force)
        try:
            started = asyncio.get_running_loop().time()
            await registry.recover()
            elapsed = asyncio.get_running_loop().time() - started
            assert 0.075 <= elapsed < 0.3  # Acht Sitzungen brauchen keine acht Fristen.
            assert peak == min(count, 2)
            assert registry.ready
            assert_closed(journal, budget, registry, spent=count * 550_000, reason="wiederanlauf")
            bookings = [r for r in journal.records if r["event"] == "budget_settle"]
            assert len(bookings) == count and all(r["unconfirmed"] for r in bookings)
            warnings = [r for r in read_rows(log.path) if r["event"] == "abschluss_unbestaetigt"]
            assert {r["session_ref"] for r in warnings} == {f"local_{i}" for i in range(count)}
            assert len(warnings) == count
            # Sowohl der bisher belegte Nutzerplatz als auch die globale Kapazität sind frei.
            await registry.start("user_0", "SYNTHETISCHE_SDP", None)
        finally:
            await registry.shutdown()
            journal.close()
            log.close()

    asyncio.run(run())


def test_recovery_hanging_force_close_respects_shared_deadline(tmp_path):
    async def run():
        await seed_open_sessions(tmp_path, 5)
        journal, log, budget, starter, registry = make(
            tmp_path,
            max_parallel=2,
            unclear_retry_offsets_s=(0,),
            unclear_deadline_s=0.06,
        )
        starter.force_gate.clear()  # Niemals zurückkehrender, aber abbrechbarer Provider-Aufruf.
        try:
            started = asyncio.get_running_loop().time()
            await asyncio.wait_for(registry.recover(), 0.4)
            elapsed = asyncio.get_running_loop().time() - started
            assert 0.055 <= elapsed < 0.3
            assert len(starter.calls) == 2  # Wartende Aufrufe starten nach Fristende nicht mehr.
            assert registry.ready
            assert_closed(journal, budget, registry, spent=5 * 550_000)
        finally:
            await registry.shutdown()
            journal.close()
            log.close()

    asyncio.run(run())


@pytest.mark.parametrize("phase", ["booking", "final_state"])
def test_unconfirmed_journal_failure_and_crash_recovery(tmp_path, monkeypatch, phase):
    async def run():
        await seed_open_sessions(tmp_path)
        journal, log, budget, starter, registry = make(
            tmp_path, unclear_retry_offsets_s=(0,), unclear_deadline_s=0.025
        )
        starter.force_confirmed = False
        original_write = journal._write

        def fail(data):
            row = json.loads(data)
            if (phase == "booking" and row["event"] == "budget_settle") or (
                phase == "final_state" and row.get("state") == "beendet"
            ):
                raise OSError("GEHEIMER_FEHLERTEXT")
            original_write(data)

        monkeypatch.setattr(journal, "_write", fail)
        with pytest.raises(StartsBlocked):
            await registry.recover()
        assert not registry.ready and journal.failed
        bookings = [r for r in journal.records if r["event"] == "budget_settle"]
        assert len(bookings) == (1 if phase == "final_state" else 0)
        if bookings:
            assert bookings[0]["unconfirmed"] is True
        with pytest.raises(StartsBlocked):
            await registry.recover()
        await registry.shutdown()
        journal.close()
        log.close()
        assert "GEHEIMER" not in log.path.read_text()
        assert "GEHEIMER" not in (tmp_path / "state" / "journal.jsonl").read_text()

        # Echter Journal-Reload: Buchung vor fehlendem beendet-Eintrag ist bereits endgültig.
        journal, log, budget, starter, registry = make(tmp_path)
        try:
            await registry.recover()
            assert registry.ready
            assert budget.status().spent_micro == 550_000
            assert not registry.snapshot()
            assert len([r for r in journal.records if r["event"] == "budget_settle"]) == 1
            assert len(starter.calls) == (0 if phase == "final_state" else 1)
        finally:
            await registry.shutdown()
            journal.close()
            log.close()

    asyncio.run(run())


@pytest.mark.parametrize(
    "usage,amount",
    [
        (UsageSummary(None, backend_complete=False), 550_000),
        (UsageSummary(60, final=True), 550_000),
        (UsageSummary(1200, final=True), 1_000_000),
        (UsageSummary(None, {"output_tokens": 1_000_000}), 1_600_000),
        (UsageSummary(1200, {"input_tokens": 1_000_000}), 1_400_000),
    ],
)
def test_unconfirmed_budget_uses_maximum_of_reserve_and_observed_cost(tmp_path, usage, amount):
    async def run():
        with Journal(tmp_path) as journal:
            budget = Budget(journal)
            await budget.reserve("local")
            assert await budget.settle_unconfirmed("local", usage=usage) == amount
            assert await budget.settle_unconfirmed("local", usage=usage) == amount
            assert (
                await budget.settle(
                    "local", usage=UsageSummary(0, final=True), closure=CloseOutcome(True, "nutzer")
                )
                == amount
            )
            bookings = [r for r in journal.records if r["event"] == "budget_settle"]
            assert len(bookings) == 1
            assert bookings[0]["unconfirmed"] is True and bookings[0]["estimated"] is True
        with Journal(tmp_path) as journal:
            budget = Budget(journal)
            assert budget.status().spent_micro == amount and budget.status().bound_micro == 0
            assert await budget.settle_unconfirmed("local", usage=usage) == amount

    asyncio.run(run())


def test_running_unconfirmed_end_retries_and_books_latest_usage(tmp_path):
    async def run():
        journal, log, budget, starter, registry = make(
            tmp_path, max_parallel=1, unclear_retry_offsets_s=(0, 0.02), unclear_deadline_s=0.06
        )
        try:
            await registry.recover()
            result = await registry.start("user", "SDP", None)
            handle = starter.handles[0]
            handle.close_confirmed = False
            starter.force_confirmed = False
            assert await registry.end("user", result.session_ref, reason="nutzer")
            with pytest.raises(UserHasSession):
                await registry.start("user", "SDP", None)
            with pytest.raises(CapacityExhausted):
                await registry.start("other", "SDP", None)
            # Nach dem ersten Fehlversuch beobachtete Usage muss berücksichtigt werden.
            handle.summary = UsageSummary(1200, {"input_tokens": 1_000_000})
            await until(lambda: not registry.snapshot())
            # Die zuvor gemeldeten zehn Output-Tokens bleiben ebenfalls berücksichtigt.
            assert_closed(journal, budget, registry, spent=1_400_016, reason="nutzer")
            assert await registry.heartbeat("user", result.session_ref) == HeartbeatStatus(
                "beendet", "nutzer"
            )
            bookings = [r for r in journal.records if r["event"] == "budget_settle"]
            assert len(bookings) == 1 and bookings[0]["unconfirmed"] is True
            assert sum(c[0] == "force" for c in starter.calls) == 3
            assert registry.ready
            await registry.start("user", "SDP", None)
        finally:
            await registry.shutdown()
            journal.close()
            log.close()

    asyncio.run(run())


def test_running_end_and_watcher_share_one_retry_task(tmp_path):
    async def run():
        journal, log, budget, starter, registry = make(
            tmp_path, unclear_retry_offsets_s=(0, 0.02), unclear_deadline_s=0.06
        )
        try:
            await registry.recover()
            result = await registry.start("user", "SDP", None)
            session = registry._sessions[result.session_ref]
            handle = starter.handles[0]
            handle.close_confirmed = False
            starter.force_confirmed = False
            handle.finish("zeitlimit", confirmed=False)
            await asyncio.gather(
                *(registry.end("user", result.session_ref, reason="nutzer") for _ in range(12))
            )
            retry = session.reconciler
            assert retry is not None
            await until(lambda: not registry.snapshot())
            assert session.reconciler is retry
            assert len([r for r in journal.records if r["event"] == "budget_settle"]) == 1
            assert (
                len([r for r in read_rows(log.path) if r["event"] == "abschluss_unbestaetigt"]) == 1
            )
        finally:
            await registry.shutdown()
            journal.close()
            log.close()

    asyncio.run(run())


def test_shutdown_cancels_running_retries_without_replacement_booking(tmp_path):
    async def run():
        journal, log, budget, starter, registry = make(
            tmp_path,
            close_timeout_s=0.01,
            unclear_retry_offsets_s=(0, 0.03),
            unclear_deadline_s=0.08,
        )
        await registry.recover()
        result = await registry.start("user", "SDP", None)
        handle = starter.handles[0]
        handle.close_confirmed = False
        starter.force_confirmed = False
        handle.finish("zeitlimit", confirmed=False)
        endings = [
            asyncio.create_task(registry.end("user", result.session_ref, reason="nutzer"))
            for _ in range(8)
        ]
        await until(lambda: registry._sessions[result.session_ref].reconciler is not None)
        session = registry._sessions[result.session_ref]
        starter.force_gate.clear()
        await registry.shutdown()
        await asyncio.gather(*endings)
        assert session.reconciler.done()
        await asyncio.sleep(0.09)  # Über die ursprüngliche Frist hinaus passiert keine Buchung.
        assert budget.status().spent_micro == 0 and budget.status().bound_micro == 550_000
        assert not registry.ready
        assert not any(r["event"] == "budget_settle" for r in journal.records)
        assert all(t.done() for t in registry._tasks)
        journal.close()
        log.close()

    asyncio.run(run())


def test_shutdown_retries_close_after_unconfirmed_initial_close(tmp_path):
    # Codex-Integrationsreview: Shutdown bricht die Nachbehandlung ab und muss daher selbst
    # noch einmal schließen, auch wenn der initiale Auftrag schon erledigt ist.
    async def run():
        journal, log, budget, starter, registry = make(
            tmp_path,
            close_timeout_s=0.01,
            unclear_retry_offsets_s=(0, 5),
            unclear_deadline_s=10,
        )
        await registry.recover()
        result = await registry.start("user", "SDP", None)
        handle = starter.handles[0]
        handle.close_confirmed = False
        starter.force_confirmed = False
        await registry.end("user", result.session_ref, reason="nutzer")
        session = registry._sessions[result.session_ref]
        # Initialer Notschluss und erster Nachbehandlungsversuch (Offset 0) sind gelaufen;
        # der nächste Versuch käme erst nach 5 s.
        await until(lambda: starter.calls.count(("force", "provider_1")) >= 2)
        await asyncio.sleep(0.05)
        assert session.state == "abschluss_ungeklaert" and session.closer.done()
        forces = starter.calls.count(("force", "provider_1"))
        starter.force_confirmed = True  # Provider wieder erreichbar
        await registry.shutdown()
        assert starter.calls.count(("force", "provider_1")) > forces
        assert_closed(journal, budget, registry, reason="nutzer")
        assert not any(r.get("unconfirmed") for r in journal.records)
        assert all(t.done() for t in registry._tasks)
        journal.close()
        log.close()

    asyncio.run(run())


def test_unconfirmed_journal_marker_must_be_boolean(tmp_path):
    async def run():
        with Journal(tmp_path) as journal:
            budget = Budget(journal)
            await budget.reserve("local")
            await journal.append(
                "budget_settle",
                local_id="local",
                amount_micro=550_000,
                estimated=True,
                unconfirmed="true",
            )
            with pytest.raises(JournalError):
                Budget(journal)
            assert journal.failed

    asyncio.run(run())


def test_running_retry_confirmation_settles_normally(tmp_path, monkeypatch):
    async def run():
        journal, log, budget, starter, registry = make(
            tmp_path, unclear_retry_offsets_s=(0, 0.02), unclear_deadline_s=0.2
        )
        calls = []

        async def force(provider_id):
            calls.append(provider_id)
            return CloseOutcome(len(calls) >= 3, "wiederanlauf")

        monkeypatch.setattr(starter, "force_close", force)
        try:
            await registry.recover()
            result = await registry.start("user", "SDP", None)
            session = registry._sessions[result.session_ref]
            starter.handles[0].close_confirmed = False
            await registry.end("user", result.session_ref, reason="nutzer")
            await until(lambda: not registry.snapshot() and session.reconciler.done())
            assert len(calls) == 3
            assert_closed(journal, budget, registry, spent=50_056, reason="nutzer")
            bookings = [r for r in journal.records if r["event"] == "budget_settle"]
            assert len(bookings) == 1 and not bookings[0].get("unconfirmed", False)
        finally:
            await registry.shutdown()
            journal.close()
            log.close()

    asyncio.run(run())


def test_replacement_keeps_observed_usage_and_late_provider_block(tmp_path):
    async def run():
        journal, log, budget, starter, registry = make(
            tmp_path, unclear_retry_offsets_s=(0, 0.02), unclear_deadline_s=0.05
        )
        try:
            await registry.recover()
            result = await registry.start("user", "SDP", None)
            handle = starter.handles[0]
            handle.summary = UsageSummary(1200, {"input_tokens": 1_000_000})
            handle.close_confirmed = False
            starter.force_confirmed = False
            await registry.end("user", result.session_ref, reason="zeitlimit")
            handle.summary = UsageSummary(None, backend_complete=False)
            handle.blocked = True
            await until(lambda: not registry.snapshot())
            assert_closed(journal, budget, registry, spent=1_400_000, reason="zeitlimit")
            assert budget.status().blocked
            assert len([r for r in journal.records if r["event"] == "budget_settle"]) == 1
        finally:
            await registry.shutdown()
            journal.close()
            log.close()

    asyncio.run(run())


# --- Herzschlag der Gesprächsseite -----------------------------------------------------------


@pytest.mark.parametrize(
    "options",
    [{"heartbeat_timeout_s": value} for value in (0, -1, float("nan"), float("inf"), -float("inf"))]
    + [
        {"heartbeat_check_s": value}
        for value in (0, -1, float("nan"), float("inf"), -float("inf"), 16)
    ]
    + [{"heartbeat_timeout_s": 0.5, "heartbeat_check_s": 1}],
)
def test_invalid_heartbeat_configuration(tmp_path, options):
    with Journal(tmp_path / "state") as journal:
        log = OpLog(tmp_path / "op.jsonl")
        budget = Budget(journal)
        try:
            with pytest.raises(ValueError, match="Registerkonfiguration"):
                SessionRegistry(budget, FakeStarter(journal), journal, log, **options)
        finally:
            log.close()


def test_heartbeat_deadline_commissions_close_within_timeout_and_check(tmp_path, monkeypatch):
    async def run():
        journal, log, budget, starter, registry = make(
            tmp_path, heartbeat_timeout_s=0.075, heartbeat_check_s=0.02
        )
        commissioned = []
        schedule = registry._schedule_close

        def track(session, reason, **kwargs):
            commissioned.append((registry._clock() - session.last_seen, reason))
            return schedule(session, reason, **kwargs)

        monkeypatch.setattr(registry, "_schedule_close", track)
        try:
            await registry.recover()
            result = await registry.start("user", "SDP", None)
            session = registry._sessions[result.session_ref]
            await until(lambda: not registry.snapshot())
            assert 0.075 < commissioned[0][0] <= 0.095
            assert commissioned[0][1] == "herzschlag_fehlt"
            assert starter.handles[0].close_calls == ["herzschlag_fehlt"]
            assert_closed(journal, budget, registry, spent=50_056, reason="herzschlag_fehlt")
            assert await registry.heartbeat("user", result.session_ref) == HeartbeatStatus(
                "beendet", "herzschlag_fehlt"
            )
            assert session.heartbeat_watcher.done()
            assert len([r for r in journal.records if r["event"] == "budget_settle"]) == 1
            assert any(r.get("reason") == "herzschlag_fehlt" for r in read_rows(log.path))
        finally:
            await registry.shutdown()
            assert not registry._tasks
            journal.close()
            log.close()

    asyncio.run(run())


def test_regular_heartbeat_extends_deadline_and_exact_boundary_does_not_expire(tmp_path):
    async def run():
        now = 100.0
        journal, log, budget, starter, registry = make(
            tmp_path, clock=lambda: now, heartbeat_timeout_s=10, heartbeat_check_s=0.003
        )
        try:
            await registry.recover()
            result = await registry.start("user", "SDP", None)
            session = registry._sessions[result.session_ref]
            assert session.last_seen == now
            for now in (109.0, 118.0, 127.0, 136.0):
                assert await registry.heartbeat("user", result.session_ref) == HeartbeatStatus(
                    "laufend", None
                )
                assert session.last_seen == now
                await asyncio.sleep(0.012)  # Mehrere Prüftakte je Herzschlag.
                assert session.state == "laufend"
                assert session.closer is None
                assert starter.handles[0].close_calls == []
            now = 146.0  # Exakt die Frist seit dem letzten angenommenen Herzschlag.
            await asyncio.sleep(0.012)
            assert session.state == "laufend" and session.closer is None
            now = 147.0
            await until(lambda: not registry.snapshot())
            assert_closed(journal, budget, registry, reason="herzschlag_fehlt")
        finally:
            await registry.shutdown()
            journal.close()
            log.close()

    asyncio.run(run())


def test_heartbeat_during_start_is_volatile_and_running_resets_last_seen(tmp_path):
    async def run():
        now = 100.0
        journal, log, budget, starter, registry = make(tmp_path, clock=lambda: now)
        starter.create_gate.clear()
        try:
            await registry.recover()
            start = asyncio.create_task(registry.start("user", "SDP", None))
            await until(lambda: starter.calls)
            session = next(iter(registry._sessions.values()))
            before = (list(journal.records), log.path.read_text())
            now = 110.0
            assert await registry.heartbeat("user", session.local_id) == HeartbeatStatus(
                "laufend", None
            )
            assert session.last_seen == now
            assert (journal.records, log.path.read_text()) == before
            now = 120.0
            starter.create_gate.set()
            await start
            assert session.last_seen == now
            before = (list(journal.records), log.path.read_text())
            now = 121.0
            assert await registry.heartbeat("user", session.local_id) == HeartbeatStatus(
                "laufend", None
            )
            assert session.last_seen == now
            assert (journal.records, log.path.read_text()) == before
        finally:
            starter.create_gate.set()
            await registry.shutdown()
            journal.close()
            log.close()

    asyncio.run(run())


@pytest.mark.parametrize(
    "state",
    ["startend", "laufend", "endend", "abschluss_ungeklaert", "erzeugung_ungeklaert", "beendet"],
)
@pytest.mark.parametrize("reason", [None, "nutzer"])
def test_heartbeat_state_projection_and_ownership(tmp_path, state, reason):
    async def run():
        now = 100.0
        journal, log, budget, starter, registry = make(tmp_path, clock=lambda: now)
        try:
            await registry.recover()
            result = await registry.start("user", "SDP", None)
            session = registry._sessions[result.session_ref]
            session.state = state  # Vertrag für alle Zustände unabhängig von Provider-Fehlern.
            session.reason = reason
            before = (session.last_seen, list(journal.records), log.path.read_text())
            now = 105.0
            assert await registry.heartbeat("other", result.session_ref) is None
            assert await registry.heartbeat("user", "unbekannt") is None
            assert (session.last_seen, journal.records, log.path.read_text()) == before
            status = await registry.heartbeat("user", result.session_ref)
            if state in {"startend", "laufend"} and reason is None:
                assert status == HeartbeatStatus("laufend", None)
                assert session.last_seen == now
            else:
                expected = (
                    None
                    if state in {"erzeugung_ungeklaert", "beendet"}
                    else HeartbeatStatus("endend", reason)
                )
                assert status == expected
                assert session.last_seen == before[0]
            assert (journal.records, log.path.read_text()) == before[1:]
            assert session.closer is None
            assert starter.handles[0].close_calls == []
        finally:
            session.state = "laufend"
            await registry.shutdown()
            journal.close()
            log.close()

    asyncio.run(run())


@pytest.mark.parametrize("confirmed", [True, False])
def test_heartbeat_during_close_does_not_extend_deadline_or_restart_close(tmp_path, confirmed):
    async def run():
        now = 100.0
        journal, log, budget, starter, registry = make(tmp_path, clock=lambda: now)
        try:
            await registry.recover()
            result = await registry.start("user", "SDP", None)
            session = registry._sessions[result.session_ref]
            handle = starter.handles[0]
            handle.close_gate.clear()
            handle.close_confirmed = confirmed
            starter.force_confirmed = confirmed
            ending = asyncio.create_task(registry.end("user", result.session_ref, reason="nutzer"))
            await until(lambda: handle.close_calls)
            closer = session.closer
            before = (list(journal.records), log.path.read_text())
            now = 105.0
            assert await registry.heartbeat("user", result.session_ref) == HeartbeatStatus(
                "endend", "nutzer"
            )
            assert session.last_seen == 100.0
            assert session.closer is closer
            assert handle.close_calls == ["nutzer"]
            assert (journal.records, log.path.read_text()) == before
            handle.close_gate.set()
            assert await ending
            if not confirmed:
                assert session.state == "abschluss_ungeklaert"
                reconciler = session.reconciler
                before = (list(journal.records), log.path.read_text())
                now = 110.0
                assert await registry.heartbeat("user", result.session_ref) == HeartbeatStatus(
                    "endend", "nutzer"
                )
                assert session.last_seen == 100.0
                assert session.closer is closer and session.reconciler is reconciler
                assert handle.close_calls == ["nutzer"]
                assert (journal.records, log.path.read_text()) == before
        finally:
            starter.handles[0].close_gate.set()
            await registry.shutdown()
            journal.close()
            log.close()

    asyncio.run(run())


def test_completed_heartbeat_expires_without_refresh_or_side_effects(tmp_path):
    async def run():
        now = 100.0
        journal, log, budget, starter, registry = make(tmp_path, clock=lambda: now)
        try:
            await registry.recover()
            result = await registry.start("user", "SDP", None)
            session = registry._sessions[result.session_ref]
            now = 105.0
            assert await registry.end("user", result.session_ref, reason="nutzer")
            before = (
                list(journal.records),
                log.path.read_text(),
                list(starter.calls),
                list(starter.handles[0].close_calls),
            )
            for heartbeat_time in (110.0, 600.0, 704.999):
                now = heartbeat_time
                assert await registry.heartbeat("other", result.session_ref) is None
                assert await registry.heartbeat("user", result.session_ref) == HeartbeatStatus(
                    "beendet", "nutzer"
                )
                assert session.last_seen == 100.0
                assert registry.snapshot() == {}
            now = 705.0
            assert await registry.heartbeat("user", result.session_ref) is None
            assert not await registry.end("user", result.session_ref, reason="nutzer")
            assert (
                journal.records,
                log.path.read_text(),
                starter.calls,
                starter.handles[0].close_calls,
            ) == before
        finally:
            await registry.shutdown()
            journal.close()
            log.close()

    asyncio.run(run())


@pytest.mark.parametrize("max_parallel", [1, 2])
def test_completed_heartbeats_evict_oldest_completion_even_after_read(tmp_path, max_parallel):
    async def run():
        # Gleiche Zeitstempel: die tatsächliche Abschlussreihenfolge entscheidet.
        journal, log, budget, starter, registry = make(
            tmp_path, max_parallel=max_parallel, clock=lambda: 100.0
        )
        try:
            await registry.recover()
            refs = []
            for _ in range(2 * max_parallel):
                result = await registry.start("user", "SDP", None)
                refs.append(result.session_ref)
                assert await registry.end("user", result.session_ref, reason="nutzer")
            for ref in refs:
                assert await registry.heartbeat("user", ref) == HeartbeatStatus("beendet", "nutzer")
            result = await registry.start("user", "SDP", None)
            # Frühere Endstatus bleiben auch während eines neuen Gesprächs erreichbar.
            assert await registry.heartbeat("user", refs[0]) == HeartbeatStatus("beendet", "nutzer")
            assert await registry.heartbeat("user", result.session_ref) == HeartbeatStatus(
                "laufend", None
            )
            assert await registry.end("user", result.session_ref, reason="nutzer")
            assert await registry.heartbeat("user", refs[0]) is None
            for ref in [*refs[1:], result.session_ref]:
                assert await registry.heartbeat("user", ref) == HeartbeatStatus("beendet", "nutzer")
        finally:
            await registry.shutdown()
            journal.close()
            log.close()

    asyncio.run(run())


def test_completed_heartbeat_is_not_restored_from_journal(tmp_path):
    async def run():
        journal, log, budget, starter, registry = make(tmp_path)
        try:
            await registry.recover()
            result = await registry.start("user", "SDP", None)
            assert await registry.end("user", result.session_ref, reason="nutzer")
            assert await registry.heartbeat("user", result.session_ref) == HeartbeatStatus(
                "beendet", "nutzer"
            )
        finally:
            await registry.shutdown()
            journal.close()
            log.close()
        journal, log, budget, starter, registry = make(tmp_path)
        try:
            await registry.recover()
            before = (list(journal.records), log.path.read_text())
            assert await registry.heartbeat("user", result.session_ref) is None
            assert await registry.heartbeat("other", result.session_ref) is None
            assert registry.snapshot() == {}
            assert starter.calls == []
            assert (journal.records, log.path.read_text()) == before
        finally:
            await registry.shutdown()
            journal.close()
            log.close()

    asyncio.run(run())


@pytest.mark.parametrize("first", ["heartbeat", "end"])
@pytest.mark.parametrize("mode", ["confirmed", "hanging", "unconfirmed"])
def test_heartbeat_and_end_share_initial_close_and_reconciler(tmp_path, monkeypatch, first, mode):
    async def run():
        now = 100.0
        journal, log, budget, starter, registry = make(
            tmp_path,
            clock=lambda: now,
            heartbeat_timeout_s=10,
            heartbeat_check_s=0.003,
            close_timeout_s=0.02,
            unclear_retry_offsets_s=(0,),
            unclear_deadline_s=0.04,
        )
        spawned = []
        spawn = registry._spawn

        def track(operation):
            task = spawn(operation)
            spawned.append((operation.cr_code.co_name, task))
            return task

        monkeypatch.setattr(registry, "_spawn", track)
        try:
            await registry.recover()
            result = await registry.start("user", "SDP", None)
            session = registry._sessions[result.session_ref]
            handle = starter.handles[0]
            handle.close_gate.clear()  # Der zweite Auslöser trifft einen offenen Auftrag.
            handle.close_confirmed = mode == "confirmed"
            starter.force_confirmed = mode == "confirmed"
            if first == "heartbeat":
                now = 111.0
                await until(lambda: handle.close_calls)
            else:
                # Beide Auslöser laufen los, während die Registersperre noch gehalten wird.
                async with registry._lock:
                    ending = asyncio.create_task(
                        registry.end("user", result.session_ref, reason="nutzer")
                    )
                    await asyncio.sleep(0)
                    now = 111.0
                    await asyncio.sleep(0.006)
            endings = [
                asyncio.create_task(registry.end("user", result.session_ref, reason="nutzer"))
                for _ in range(8)
            ]
            if first == "end":
                endings.append(ending)
            await until(lambda: handle.close_calls)
            closer = session.closer
            if mode != "hanging":
                handle.close_gate.set()
            assert all(await asyncio.gather(*endings))
            assert session.closer is closer
            assert len(handle.close_calls) == 1
            assert len([t for name, t in spawned if name == "_close"]) == 1
            assert session.heartbeat_watcher.done()
            if mode != "confirmed":
                await until(lambda: session.reconciler is not None)
                # Auch ein erneutes end() nach dem initialen Fehlversuch startet keinen Close.
                assert await registry.end("user", result.session_ref, reason="nutzer")
                assert session.closer is closer
                assert len([t for name, t in spawned if name == "_reconcile"]) == 1
                now += 1  # Die bestehende Nachbehandlung darf ihren Ersatzabschluss buchen.
            await until(lambda: not registry.snapshot())
            assert_closed(
                journal,
                budget,
                registry,
                spent=50_056 if mode == "confirmed" else 550_000,
                reason="herzschlag_fehlt" if first == "heartbeat" else "nutzer",
            )
            bookings = [r for r in journal.records if r["event"] == "budget_settle"]
            assert len(bookings) == 1
            assert bool(bookings[0].get("unconfirmed")) == (mode != "confirmed")
            assert sum(c[0] == "force" for c in starter.calls) == (0 if mode == "confirmed" else 2)
        finally:
            await registry.shutdown()
            assert all(task.done() for _, task in spawned)
            assert not registry._tasks
            journal.close()
            log.close()

    asyncio.run(run())


@pytest.mark.parametrize("trigger", ["end", "remote", "deadline", "shutdown"])
def test_heartbeat_task_cleanup_when_leaving_running(tmp_path, trigger):
    async def run():
        journal, log, budget, starter, registry = make(
            tmp_path, max_duration_s=0.04 if trigger == "deadline" else 600
        )
        try:
            await registry.recover()
            result = await registry.start("user", "SDP", None)
            session = registry._sessions[result.session_ref]
            heartbeat = session.heartbeat_watcher
            await asyncio.sleep(0)
            assert not heartbeat.done()
            if trigger == "end":
                await registry.end("user", result.session_ref, reason="nutzer")
            elif trigger == "remote":
                starter.handles[0].finish("inaktiv")
            elif trigger == "shutdown":
                starter.handles[0].close_gate.clear()
                stop = asyncio.create_task(registry.shutdown())
                await until(lambda: starter.handles[0].close_calls)
                assert heartbeat.done()  # Vor dem möglicherweise hängenden Close abgewartet.
                starter.handles[0].close_gate.set()
                await stop
            await until(lambda: not registry.snapshot())
            await until(heartbeat.done)
            reason = {
                "end": "nutzer",
                "remote": "inaktiv",
                "deadline": "zeitlimit",
                "shutdown": "server_ende",
            }[trigger]
            assert await registry.heartbeat("user", result.session_ref) == HeartbeatStatus(
                "beendet", reason
            )
        finally:
            await registry.shutdown()
            assert not registry._tasks
            journal.close()
            log.close()

    asyncio.run(run())


def test_greeting_once_for_own_running_session_and_logged(tmp_path):
    # Schritt 2b §4, B4: Begrüßung erst nach "bereit", genau einmal, nur eigene laufende Sitzung.
    async def run():
        with Journal(tmp_path / "state") as journal:
            log = OpLog(tmp_path / "op.jsonl")
            budget = Budget(journal)
            starter = FakeStarter(journal)
            registry = SessionRegistry(budget, starter, journal, log)
            await registry.recover()
            start = await registry.start("user_a", "SYNTHETISCHE_SDP", None)
            handle = starter.handles[0]
            assert not hasattr(handle, "greet_calls")  # keine Begrüßung ohne "bereit"
            assert not await registry.greet("user_b", start.session_ref)
            assert not await registry.greet("user_a", "fremd")
            assert await registry.greet("user_a", start.session_ref)
            assert await registry.greet("user_a", start.session_ref)  # idempotent
            assert handle.greet_calls == 1
            assert await registry.claim_measurement("user_b", start.session_ref) is None
            assert await registry.claim_measurement("user_a", start.session_ref) is True
            assert await registry.claim_measurement("user_a", start.session_ref) is False
            handle.greet_ms = 1129
            assert await registry.end("user_a", start.session_ref, reason="nutzer")
            assert not await registry.greet("user_a", start.session_ref)
            assert await registry.claim_measurement("user_a", start.session_ref) is None
            await registry.shutdown()
            log.close()
            rows = read_rows(tmp_path / "op.jsonl")
            greet = [r for r in rows if r["event"].startswith("begruessung")]
            assert [r["event"] for r in greet] == ["begruessung_gesendet", "begruessung_audio"]
            assert greet[1]["dauer_ms"] == 1129
            assert all(r["session_ref"] == start.session_ref for r in greet)

    asyncio.run(run())


@pytest.mark.parametrize("failure", ["result", "error"])
def test_greeting_failure_is_logged_and_session_keeps_running(tmp_path, failure):
    async def run():
        with Journal(tmp_path / "state") as journal:
            log = OpLog(tmp_path / "op.jsonl")
            budget = Budget(journal)
            starter = FakeStarter(journal)
            registry = SessionRegistry(budget, starter, journal, log)
            await registry.recover()
            start = await registry.start("user_a", "SYNTHETISCHE_SDP", None)
            handle = starter.handles[0]
            if failure == "result":
                handle.greet_result = False
            else:
                handle.greet_error = ConnectionError("GEHEIMER_PROVIDER_TEXT")
            assert await registry.greet("user_a", start.session_ref)
            assert registry.snapshot() == {start.session_ref: "laufend"}
            assert await registry.end("user_a", start.session_ref, reason="nutzer")
            await registry.shutdown()
            log.close()
            text = (tmp_path / "op.jsonl").read_text()
            assert "begruessung_fehlgeschlagen" in text and "GEHEIM" not in text
            audio = [
                r for r in read_rows(tmp_path / "op.jsonl") if r["event"] == "begruessung_audio"
            ]
            assert len(audio) == 1 and "dauer_ms" not in audio[0]  # kein Audio gemessen

    asyncio.run(run())


def test_greeting_rejected_by_provider_is_logged(tmp_path):
    async def run():
        with Journal(tmp_path / "state") as journal:
            log = OpLog(tmp_path / "op.jsonl")
            budget = Budget(journal)
            starter = FakeStarter(journal)
            registry = SessionRegistry(budget, starter, journal, log)
            await registry.recover()
            start = await registry.start("user_a", "SYNTHETISCHE_SDP", None)
            assert await registry.greet("user_a", start.session_ref)
            starter.handles[0].greet_rejected = True
            assert await registry.end("user_a", start.session_ref, reason="nutzer")
            await registry.shutdown()
            log.close()
            events = [r["event"] for r in read_rows(tmp_path / "op.jsonl")]
            assert events.count("begruessung_gesendet") == 1
            assert events.count("begruessung_fehlgeschlagen") == 1

    asyncio.run(run())
