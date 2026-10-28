"""Atomare Platzvergabe und abbrechfestes Aufräumen des Hybrid-Registers."""

from __future__ import annotations

import asyncio
import math
import secrets
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any, get_args

from .budget import Budget
from .contracts import (
    CapacityExhausted,
    CloseOutcome,
    CreateUnclear,
    EndReason,
    OpLog,
    ProviderBlocked,
    SessionState,
    SidebandHandle,
    Starter,
    StartFailed,
    StartRefused,
    StartResult,
    StartsBlocked,
    UsageSummary,
    UserHasSession,
)
from .journal import Journal, JournalError, durable


def _unknown_usage() -> UsageSummary:
    return UsageSummary(None, backend_complete=False)


@dataclass
class _Session:
    local_id: str
    user_id: str
    state: SessionState = "startend"
    provider_id: str | None = None
    reason: EndReason | None = None
    handle: SidebandHandle | None = None
    watcher: asyncio.Task[None] | None = None
    heartbeat_watcher: asyncio.Task[None] | None = None
    closer: asyncio.Task[None] | None = None
    reconciler: asyncio.Task[None] | None = None
    observed_usage: UsageSummary = field(default_factory=_unknown_usage)
    close_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    finish_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    initializing: bool = False
    deadline: float = 0
    last_seen: float = 0


class SessionRegistry:
    """Vor dem ersten Start recover(), vor Journal.close() shutdown() aufrufen.

    user_id kommt ausschließlich aus der geprüften Anmeldung des HTTP-Layers.
    Das Register enthält nur offene/ungeklärte Sitzungen; Abschlüsse stehen im Journal.
    """

    def __init__(
        self,
        budget: Budget,
        starter: Starter,
        journal: Journal,
        oplog: OpLog,
        *,
        max_parallel: int = 20,
        max_duration_s: float = 600,
        idle_timeout_s: float = 120,
        close_timeout_s: float = 15,
        heartbeat_timeout_s: float = 15,
        heartbeat_check_s: float = 1,
        unclear_retry_offsets_s: tuple[float, ...] = (0, 5, 15, 30, 60),
        unclear_deadline_s: float = 120,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if (
            type(max_parallel) is not int
            or max_parallel < 1
            or not 0 < max_duration_s <= 600
            or not 0 < idle_timeout_s
            or not 0 < close_timeout_s <= 15
            or not math.isfinite(heartbeat_timeout_s)
            or not math.isfinite(heartbeat_check_s)
            or not 0 < heartbeat_check_s <= heartbeat_timeout_s
            or not math.isfinite(unclear_deadline_s)
            or unclear_deadline_s <= 0
            or not unclear_retry_offsets_s
            or unclear_retry_offsets_s[0] != 0
            or any(
                not math.isfinite(offset) or not 0 <= offset < unclear_deadline_s
                for offset in unclear_retry_offsets_s
            )
            or any(
                a >= b
                for a, b in zip(unclear_retry_offsets_s, unclear_retry_offsets_s[1:], strict=False)
            )
            or budget.journal is not journal
        ):
            raise ValueError("Ungültige Registerkonfiguration")
        self.budget = budget
        self.starter = starter
        self.journal = journal
        self.oplog = oplog
        self.max_parallel = max_parallel
        self.max_duration_s = max_duration_s
        self.idle_timeout_s = idle_timeout_s
        self.close_timeout_s = close_timeout_s
        self.heartbeat_timeout_s = heartbeat_timeout_s
        self.heartbeat_check_s = heartbeat_check_s
        self.unclear_retry_offsets_s = tuple(unclear_retry_offsets_s)
        self.unclear_deadline_s = unclear_deadline_s
        self._clock = clock
        self._lock = asyncio.Lock()
        self._recover_lock = asyncio.Lock()
        self._recovery: asyncio.Task[None] | None = None
        self._ready = False
        self._stopping = False
        self._sessions: dict[str, _Session] = {}
        self._tasks: set[asyncio.Task[Any]] = set()
        self._starts: set[asyncio.Task[StartResult]] = set()
        try:
            for record in journal.records:
                if record["event"] != "session":
                    continue
                local_id, user_id = record["local_id"], record["user_id"]
                state, provider_id, reason = (
                    record["state"],
                    record["provider_id"],
                    record["reason"],
                )
                if (
                    not isinstance(local_id, str)
                    or not local_id
                    or not isinstance(user_id, str)
                    or not user_id
                    or state not in get_args(SessionState)
                    or (
                        provider_id is not None
                        and (not isinstance(provider_id, str) or not provider_id)
                    )
                    or (reason is not None and reason not in get_args(EndReason))
                    or not budget.has_id(local_id)
                ):
                    raise ValueError
                old = self._sessions.get(local_id)
                if old and (
                    old.user_id != user_id
                    or (old.provider_id is not None and old.provider_id != provider_id)
                ):
                    raise ValueError
                if state == "beendet":
                    self._sessions.pop(local_id, None)
                else:
                    self._sessions[local_id] = _Session(
                        local_id, user_id, state, provider_id, reason
                    )
            self._sessions = {
                local_id: session
                for local_id, session in self._sessions.items()
                if not budget.is_closed(local_id)
            }
            # Eine Reservierung kann vor dem ersten Session-Eintrag liegen (Absturz beim Start).
            for local_id in budget.reservations:
                if local_id not in self._sessions:
                    self._sessions[local_id] = _Session(
                        local_id, "wiederanlauf_unbekannt", "erzeugung_ungeklaert"
                    )
        except (KeyError, TypeError, ValueError):
            journal.failed = True
            raise JournalError("Ungültiger Sitzungszustand im Journal") from None

    @property
    def ready(self) -> bool:
        return self._ready and not self._stopping and not self.journal.failed

    def snapshot(self) -> dict[str, SessionState]:
        """Nur lokale Referenzen und Zustände; keine Provider- oder Gesprächsdaten."""
        return {key: value.state for key, value in self._sessions.items()}

    def _spawn(self, operation: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
        task = asyncio.create_task(operation)
        self._tasks.add(task)

        def done(finished: asyncio.Task[Any]) -> None:
            self._tasks.discard(finished)
            if not finished.cancelled():
                finished.exception()  # Auch verwaiste Start-/Aufräumaufgaben werden konsumiert.

        task.add_done_callback(done)
        return task

    def _log(self, event: str, **fields: Any) -> None:
        try:
            self.oplog.write(event, **fields)
        except OSError:
            self._ready = False

    async def _record(self, session: _Session, state: SessionState) -> None:
        session.state = state
        heartbeat_watcher = session.heartbeat_watcher
        if (
            state != "laufend"
            and heartbeat_watcher is not None
            and heartbeat_watcher is not asyncio.current_task()
        ):
            heartbeat_watcher.cancel()
        await self.journal.append(
            "session",
            local_id=session.local_id,
            user_id=session.user_id,
            provider_id=session.provider_id,
            state=state,
            reason=session.reason,
        )
        self._log(
            "sitzung_status", session_ref=session.local_id, state=state, reason=session.reason
        )

    async def start(self, user_id: str, sdp: str, voice: str | None) -> StartResult:
        task = self._spawn(self._start(user_id, sdp, voice))
        self._starts.add(task)
        task.add_done_callback(self._starts.discard)
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            # Die Erzeugungsantwort darf nicht durch Abbruch der HTTP-Anfrage verlorengehen.
            cleanup = self._spawn(self._abandoned_start(task, user_id))
            await durable(self._join(cleanup))
            raise

    @staticmethod
    async def _join(task: asyncio.Task[Any]) -> Any:
        return await asyncio.shield(task)

    async def _abandoned_start(self, task: asyncio.Task[StartResult], user_id: str) -> None:
        try:
            result = await asyncio.shield(task)
        except (StartRefused, StartFailed):
            return
        await self.end(user_id, result.session_ref, reason="server_ende")

    def _sync_provider_block(self) -> None:
        """Guthabenfehler laufender Gespräche sofort übernehmen, nicht erst bei deren Ende."""
        for other in self._sessions.values():
            try:
                if other.handle is not None and other.handle.provider_blocked():
                    self.budget.set_provider_blocked()
                    return
            except Exception:
                continue

    async def _start(self, user_id: str, sdp: str, voice: str | None) -> StartResult:
        async with self._lock:
            self._sync_provider_block()  # Budget.reserve() prüft danach die Sperre
            if not self.ready:
                raise StartsBlocked
            if not user_id:
                raise StartsBlocked
            if any(s.user_id == user_id for s in self._sessions.values()):
                raise UserHasSession
            if len(self._sessions) >= self.max_parallel:
                raise CapacityExhausted
            session = _Session(secrets.token_urlsafe(24), user_id, initializing=True)
            try:
                await self.budget.reserve(session.local_id)
                self._sessions[session.local_id] = session
                await self._record(session, "startend")
            except JournalError:
                raise StartsBlocked from None

        deadline = session.deadline = self._clock() + self.max_duration_s
        try:
            try:
                async with asyncio.timeout(self.max_duration_s):
                    session.provider_id, answer = await self.starter.create(sdp, voice)
            except ProviderBlocked:
                self.budget.set_provider_blocked()
                await self._uncreated(session)
                raise  # Fehlerklasse bis zur App erhalten (Codex-Review)
            except StartFailed:
                await self._uncreated(session)
                raise
            except Exception as error:
                # CreateUnclear und unerwartete Fehler dürfen keine zweite Erzeugung auslösen.
                await self._record(session, "erzeugung_ungeklaert")
                session.initializing = False
                if isinstance(error, CreateUnclear):
                    raise
                raise CreateUnclear from None

            # Die Provider-ID muss vor dem Attach dauerhaft sein.
            await self._record(session, "startend")
            try:
                remaining = deadline - self._clock()
                if remaining <= 0:
                    raise TimeoutError
                async with asyncio.timeout(remaining):
                    session.handle = await self.starter.attach(
                        session.provider_id,
                        deadline_s=remaining,  # verbleibende Sekunden (Vertrag)
                        idle_timeout_s=self.idle_timeout_s,
                    )
            except Exception as error:
                if isinstance(error, ProviderBlocked):
                    self.budget.set_provider_blocked()
                session.reason = "attach_fehler"
                session.initializing = False
                await self._finish(session, await self._force_close(session), _unknown_usage())
                raise StartFailed from None

            session.last_seen = self._clock()
            await self._record(session, "laufend")
            session.initializing = False
            session.watcher = self._spawn(self._watch(session))
            session.heartbeat_watcher = self._spawn(self._watch_heartbeat(session))
            if session.reason is not None or self._stopping:
                await self._request_close(session, session.reason or "server_ende")
                raise StartFailed
            return StartResult(session.local_id, answer)
        except JournalError:
            # Auch bei defektem Datenträger bekannte Provider-Sitzungen schließen.
            if session.provider_id:
                session.initializing = False
                await self._request_close(session, "attach_fehler")
            raise StartFailed from None

    async def _uncreated(self, session: _Session) -> None:
        async with self._lock:
            await self.budget.release_uncreated(session.local_id)
            await self._record(session, "beendet")
            self._sessions.pop(session.local_id, None)

    async def _force_close(
        self, session: _Session, *, timeout_s: float | None = None
    ) -> CloseOutcome:
        reason = session.reason or "sideband_abbruch"
        if session.provider_id is None:
            return CloseOutcome(False, reason)
        try:
            async with asyncio.timeout(
                self.close_timeout_s if timeout_s is None else min(self.close_timeout_s, timeout_s)
            ):
                result = await self.starter.force_close(session.provider_id)
            return CloseOutcome(result.confirmed, reason)
        except ProviderBlocked:
            self.budget.set_provider_blocked()
        except Exception:
            pass
        return CloseOutcome(False, reason)

    async def _watch(self, session: _Session) -> None:
        assert session.handle is not None
        try:
            async with asyncio.timeout(max(0, session.deadline - self._clock())):
                closure, usage = await session.handle.wait_closed()
        except TimeoutError:
            await self._request_close(session, "zeitlimit")
            return
        except Exception as error:
            if isinstance(error, ProviderBlocked):
                self.budget.set_provider_blocked()
            closure, usage = CloseOutcome(False, "sideband_abbruch"), self._usage(session)
        self._sync_provider_block()
        if not closure.confirmed:
            # Mit einem gleichzeitig laufenden end() wird höchstens ein Notschluss ausgeführt.
            await self._request_close(session, session.reason or closure.reason, usage=usage)
        else:
            await self._finish(session, closure, usage)

    @staticmethod
    def _remember_usage(session: _Session, usage: UsageSummary) -> None:
        # Kumulative Zwischenstände nicht addieren und bei fehlenden Folgemeldungen behalten.
        previous = session.observed_usage
        seconds = [
            value
            for value in (previous.live_seconds, usage.live_seconds)
            if type(value) is int and value >= 0
        ]
        tokens = dict(previous.backend_tokens)
        for key in ("input_tokens", "output_tokens"):
            value = usage.backend_tokens.get(key)
            if type(value) is int and value >= 0:
                tokens[key] = max(tokens.get(key, 0), value)
        session.observed_usage = UsageSummary(
            max(seconds, default=None), tokens, backend_complete=False
        )

    @staticmethod
    def _usage(session: _Session) -> UsageSummary:
        try:
            usage = session.handle.usage() if session.handle is not None else _unknown_usage()
            SessionRegistry._remember_usage(session, usage)
            return usage
        except Exception:
            return _unknown_usage()

    async def _request_close(
        self, session: _Session, reason: EndReason, *, usage: UsageSummary | None = None
    ) -> None:
        async with self._lock:
            closer = self._schedule_close(session, reason, usage=usage)
        if closer is not None:
            await asyncio.shield(closer)

    def _schedule_close(
        self, session: _Session, reason: EndReason, *, usage: UsageSummary | None = None
    ) -> asyncio.Task[None] | None:
        """Unter self._lock genau einen initialen Abschlussauftrag speichern."""
        if usage is not None:
            self._remember_usage(session, usage)
        if session.state in {"beendet", "erzeugung_ungeklaert"}:
            return None
        session.reason = session.reason or reason
        if session.initializing or session.provider_id is None:
            # Ein Ende während create/attach wird nach erfolgreichem Attach beauftragt.
            return None
        if session.closer is None:
            session.closer = self._spawn(self._close(session, session.reason, usage=usage))
        return session.closer

    async def _close(
        self, session: _Session, reason: EndReason, *, usage: UsageSummary | None = None
    ) -> None:
        async with session.close_lock:
            if session.state in {"beendet", "erzeugung_ungeklaert"}:
                return
            session.reason = session.reason or reason
            if session.initializing or session.provider_id is None:
                # Start ist noch im create(); nach attach wird sofort geschlossen.
                return
            try:
                await self._record(session, "endend")
            except JournalError:
                pass
            closure = CloseOutcome(False, session.reason)
            if session.handle is not None and usage is None:
                try:
                    async with asyncio.timeout(self.close_timeout_s):
                        closure = await session.handle.close(reason=session.reason)
                except ProviderBlocked:
                    self.budget.set_provider_blocked()
                except Exception:
                    pass
            if session.state == "beendet":
                return  # Der Watcher hat die Bestätigung bereits abgerechnet.
            if not closure.confirmed:
                closure = await self._force_close(session)
            else:
                closure = CloseOutcome(True, session.reason)
            await self._finish(session, closure, usage or self._usage(session))

    async def _finish(
        self,
        session: _Session,
        closure: CloseOutcome,
        usage: UsageSummary,
        *,
        schedule_retry: bool = True,
    ) -> None:
        self._remember_usage(session, usage)
        # Jeder Abschluss läuft hier durch: Guthabenfehler dieser Sitzung vor dem Entfernen
        # übernehmen (auch im Zeitlimit-Pfad; Codex-Nachprüfung).
        try:
            if session.handle is not None and session.handle.provider_blocked():
                self.budget.set_provider_blocked()
        except Exception:
            pass
        async with session.finish_lock:
            if session.state == "beendet":
                return
            session.reason = session.reason or closure.reason
            async with self._lock:
                try:
                    if not closure.confirmed:
                        await self._record(session, "abschluss_ungeklaert")
                    else:
                        try:
                            await self.budget.settle(
                                session.local_id,
                                usage=usage,
                                closure=CloseOutcome(True, session.reason),
                            )
                        except ValueError:
                            await self.budget.settle(
                                session.local_id,
                                usage=_unknown_usage(),
                                closure=CloseOutcome(True, session.reason),
                            )
                        await self._record(session, "beendet")
                        self._sessions.pop(session.local_id, None)
                except JournalError:
                    session.state = "abschluss_ungeklaert"
            if (
                not closure.confirmed
                and schedule_retry
                and session.provider_id is not None
                and session.reconciler is None
                and not self._stopping
                and not self.journal.failed
            ):
                started = self._clock()
                session.reconciler = self._spawn(
                    self._reconcile(session, started, started + self.unclear_deadline_s)
                )
            watcher = session.watcher
            if watcher is not None and watcher is not asyncio.current_task() and not watcher.done():
                watcher.cancel()
            retry = session.reconciler
            if (
                session.state == "beendet"
                and schedule_retry
                and retry is not None
                and retry is not asyncio.current_task()
                and not retry.done()
            ):
                retry.cancel()

    async def _reconcile(
        self,
        session: _Session,
        started: float,
        deadline: float,
        semaphore: asyncio.Semaphore | None = None,
    ) -> None:
        """Nachbehandlung mit absoluter Frist; Wartezeiten halten keine Registersperre."""
        # Den auslösenden Abschluss zunächst seine Sperren freigeben lassen.
        await asyncio.sleep(0)
        semaphore = semaphore if semaphore is not None else asyncio.Semaphore(1)
        for offset in self.unclear_retry_offsets_s:
            await asyncio.sleep(max(0, started + offset - self._clock()))
            async with semaphore:
                async with session.close_lock:
                    if session.state == "beendet" or self._stopping or self.journal.failed:
                        return
                    remaining = deadline - self._clock()
                    if remaining <= 0:
                        break
                    closure = await self._force_close(session, timeout_s=remaining)
                    if closure.confirmed or session.state != "abschluss_ungeklaert":
                        await durable(
                            self._finish(
                                session, closure, self._usage(session), schedule_retry=False
                            )
                        )
                    if session.state == "beendet" or self.journal.failed:
                        return
        await asyncio.sleep(max(0, deadline - self._clock()))
        await durable(self._finish_unconfirmed(session))

    async def _finish_unconfirmed(self, session: _Session) -> None:
        async with session.finish_lock:
            async with self._lock:
                if session.state == "beendet" or self._stopping or self.journal.failed:
                    return
                self._sync_provider_block()
                self._usage(session)
                try:
                    try:
                        await self.budget.settle_unconfirmed(
                            session.local_id, usage=session.observed_usage
                        )
                    except ValueError:
                        await self.budget.settle_unconfirmed(
                            session.local_id, usage=_unknown_usage()
                        )
                    await self._record(session, "beendet")
                    self._sessions.pop(session.local_id, None)
                    self._log("abschluss_unbestaetigt", session_ref=session.local_id)
                except JournalError:
                    session.state = "abschluss_ungeklaert"

    async def end(self, user_id: str, session_ref: str, *, reason: EndReason) -> bool:
        if reason not in get_args(EndReason):
            raise ValueError("Unbekannter Abschlussgrund")
        async with self._lock:
            session = self._sessions.get(session_ref)
            if session is None or session.user_id != user_id or session.state == "beendet":
                return False
            closer = self._schedule_close(session, reason)
        if closer is not None:
            await asyncio.shield(closer)
        return True

    async def heartbeat(self, user_id: str, session_ref: str) -> bool:
        async with self._lock:
            session = self._sessions.get(session_ref)
            if (
                session is None
                or session.user_id != user_id
                or session.state not in {"startend", "laufend"}
            ):
                return False
            session.last_seen = self._clock()
            return True

    async def _watch_heartbeat(self, session: _Session) -> None:
        while True:
            await asyncio.sleep(self.heartbeat_check_s)
            async with self._lock:
                if session.state != "laufend" or self._stopping:
                    return
                if self._clock() - session.last_seen > self.heartbeat_timeout_s:
                    self._schedule_close(session, "herzschlag_fehlt")
                    return

    async def recover(self) -> None:
        # Provider-Wartezeiten sind abbrechbar; nur lokale Buchungen sind dauerhaft geschützt.
        if self._recovery is None or self._recovery.done():
            self._recovery = self._spawn(self._recover())
        await self._recovery

    async def _recover(self) -> None:
        async with self._recover_lock:
            if self.ready or self._stopping:
                return
            if self.journal.failed:
                raise StartsBlocked
            started = self._clock()
            deadline = started + self.unclear_deadline_s
            semaphore = asyncio.Semaphore(self.max_parallel)
            sessions = []
            for session in list(self._sessions.values()):
                if session.provider_id is None:
                    await self._record(session, "erzeugung_ungeklaert")
                else:
                    session.reason = session.reason or "wiederanlauf"
                    sessions.append(session)
            # gather wartet bei Fehlern auf alle Kinder; kein Provider-Zugriff nach Cleanup.
            results = await asyncio.gather(
                *(self._reconcile(s, started, deadline, semaphore) for s in sessions),
                return_exceptions=True,
            )
            if self.journal.failed or any(isinstance(result, BaseException) for result in results):
                raise StartsBlocked
            self._ready = not self.journal.failed

    async def shutdown(self) -> None:
        await durable(self._shutdown())

    async def _shutdown(self) -> None:
        async with self._lock:
            self._stopping = True
            self._ready = False
        retries = [
            task
            for s in self._sessions.values()
            for task in (s.reconciler, s.heartbeat_watcher)
            if task is not None and task is not asyncio.current_task() and not task.done()
        ]
        if self._recovery is not None and not self._recovery.done():
            retries.append(self._recovery)
        for task in retries:
            task.cancel()
        await asyncio.gather(*retries, return_exceptions=True)
        if self._starts:
            await asyncio.gather(*list(self._starts), return_exceptions=True)
        await asyncio.gather(
            *(self._request_close(s, "server_ende") for s in list(self._sessions.values()))
        )
        # Ein bestätigter force_close kann den alten Receiver bereits beendet haben. Ein
        # defekter Receiver darf den Shutdown aber nicht unbegrenzt festhalten.
        watchers = [s for s in self._tasks if s is not asyncio.current_task()]
        if watchers:
            _, pending = await asyncio.wait(watchers, timeout=self.close_timeout_s)
            for task in pending:
                task.cancel()
            await asyncio.gather(*watchers, return_exceptions=True)
