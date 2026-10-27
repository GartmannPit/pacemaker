"""Atomare Platzvergabe und abbrechfestes Aufräumen des Hybrid-Registers."""

from __future__ import annotations

import asyncio
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
    closer: asyncio.Task[None] | None = None
    close_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    finish_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    initializing: bool = False
    deadline: float = 0


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
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if (
            type(max_parallel) is not int
            or max_parallel < 1
            or not 0 < max_duration_s <= 600
            or not 0 < idle_timeout_s
            or not 0 < close_timeout_s <= 15
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
        self._clock = clock
        self._lock = asyncio.Lock()
        self._recover_lock = asyncio.Lock()
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

    async def _start(self, user_id: str, sdp: str, voice: str | None) -> StartResult:
        async with self._lock:
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

            await self._record(session, "laufend")
            session.initializing = False
            session.watcher = self._spawn(self._watch(session))
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

    async def _force_close(self, session: _Session) -> CloseOutcome:
        reason = session.reason or "sideband_abbruch"
        if session.provider_id is None:
            return CloseOutcome(False, reason)
        try:
            async with asyncio.timeout(self.close_timeout_s):
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
            if session.handle.provider_blocked():
                # Guthaben-/Quota-Fehler während des Gesprächs: keine neuen Starts (Review).
                self.budget.set_provider_blocked()
        except TimeoutError:
            await self._request_close(session, "zeitlimit")
            return
        except Exception as error:
            if isinstance(error, ProviderBlocked):
                self.budget.set_provider_blocked()
            closure, usage = CloseOutcome(False, "sideband_abbruch"), self._usage(session)
        if not closure.confirmed:
            # Mit einem gleichzeitig laufenden end() wird höchstens ein Notschluss ausgeführt.
            await self._request_close(session, session.reason or closure.reason, usage=usage)
        else:
            await self._finish(session, closure, usage)

    @staticmethod
    def _usage(session: _Session) -> UsageSummary:
        try:
            return session.handle.usage() if session.handle is not None else _unknown_usage()
        except Exception:
            return _unknown_usage()

    async def _request_close(
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

    async def _finish(self, session: _Session, closure: CloseOutcome, usage: UsageSummary) -> None:
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
            watcher = session.watcher
            if watcher is not None and watcher is not asyncio.current_task() and not watcher.done():
                watcher.cancel()

    async def end(self, user_id: str, session_ref: str, *, reason: EndReason) -> bool:
        if reason not in get_args(EndReason):
            raise ValueError("Unbekannter Abschlussgrund")
        async with self._lock:
            session = self._sessions.get(session_ref)
            if session is None or session.user_id != user_id or session.state == "beendet":
                return False
            if session.closer is None or session.closer.done():
                session.closer = self._spawn(self._request_close(session, reason))
            closer = session.closer
        await asyncio.shield(closer)
        return True

    async def recover(self) -> None:
        await durable(self._recover())

    async def _recover(self) -> None:
        async with self._recover_lock:
            if self.ready or self._stopping:
                return
            if self.journal.failed:
                raise StartsBlocked
            for session in list(self._sessions.values()):
                if session.provider_id is None:
                    await self._record(session, "erzeugung_ungeklaert")
                else:
                    session.reason = "wiederanlauf"
                    await self._finish(session, await self._force_close(session), _unknown_usage())
            # Ohne bestätigten Notschluss bleibt der Server insgesamt nicht bereit.
            self._ready = not self.journal.failed and not any(
                s.state == "abschluss_ungeklaert" for s in self._sessions.values()
            )

    async def shutdown(self) -> None:
        await durable(self._shutdown())

    async def _shutdown(self) -> None:
        async with self._lock:
            self._stopping = True
            self._ready = False
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
