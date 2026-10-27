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
        await registry.start("a", "SDP", None)
        if watch_error:
            starter.handles[0].future.set_exception(watch_error)
        else:
            starter.handles[0].finish(reason, confirmed=confirmed)
        await until(lambda: not registry.snapshot())
        assert_closed(journal, budget, registry, spent=50_056, reason=reason)
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
        assert_closed(journal, budget, registry, spent=50_056, reason="nutzer")
        await registry.shutdown()
        journal.close()
        log.close()

    asyncio.run(run())


def test_deadline_forwarding_and_registry_fallback(tmp_path):
    async def run():
        journal, log, budget, starter, registry = make(tmp_path, max_duration_s=0.08)
        await registry.recover()
        await registry.start("a", "SDP", None)
        deadline, idle = starter.attach_parameters[0]
        assert 0 < deadline <= 0.08  # verbleibende Sekunden (contracts.Starter.attach)
        assert idle == 120
        await until(lambda: not registry.snapshot())
        assert_closed(journal, budget, registry, reason="zeitlimit")
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
        journal, log, budget, starter, registry = make(tmp_path)
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
        assert registry.ready == confirmed
        if not confirmed:
            assert registry.snapshot() == {"local": "abschluss_ungeklaert"}
            with pytest.raises(StartsBlocked):
                await registry.start("b", "SDP", None)
            assert budget.status().spent_micro == 0
            starter.force_confirmed = True
            await registry.recover()
        assert registry.ready
        assert_closed(journal, budget, registry, spent=550_000, reason="wiederanlauf")
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
