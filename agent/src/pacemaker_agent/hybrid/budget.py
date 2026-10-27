"""Monatsbudget in Mikro-Dollar; ungeklärte Kosten bleiben gebunden."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal

from .contracts import (
    BudgetExhausted,
    BudgetStatus,
    CloseOutcome,
    OpLog,
    StartsBlocked,
    UsageSummary,
)
from .journal import Journal, JournalError, durable


@dataclass(frozen=True)
class Reservation:
    month: str
    live_micro: int
    backend_micro: int
    live_per_minute_micro: int
    input_per_million_micro: int
    output_per_million_micro: int

    @property
    def total(self) -> int:
        return self.live_micro + self.backend_micro


class Budget:
    def __init__(
        self,
        journal: Journal,
        *,
        limit_micro: int = 25_000_000,
        warn_ratio: float = 0.8,
        live_reserve_micro: int = 500_000,
        backend_reserve_micro: int = 50_000,
        live_per_minute_micro: int = 50_000,
        input_per_million_micro: int = 400_000,
        output_per_million_micro: int = 1_600_000,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        oplog: OpLog | None = None,
    ) -> None:
        values = (
            limit_micro,
            live_reserve_micro,
            backend_reserve_micro,
            live_per_minute_micro,
            input_per_million_micro,
            output_per_million_micro,
        )
        if any(type(v) is not int or v <= 0 for v in values) or not 0 < warn_ratio <= 1:
            raise ValueError("Budget und Preise müssen positiv sein")
        self.journal = journal
        self.limit_micro = limit_micro
        self.warn_ratio = Decimal(str(warn_ratio))
        self._defaults = values[1:]
        self._clock = clock
        self._oplog = oplog
        self._lock = asyncio.Lock()
        self._provider_blocked = False
        self._open: dict[str, Reservation] = {}
        self._settled: dict[str, int] = {}
        self._released: set[str] = set()
        self._spent: dict[str, int] = {}
        try:
            for record in journal.records:
                event = record["event"]
                if not event.startswith("budget_"):
                    continue
                local_id = record["local_id"]
                if not isinstance(local_id, str) or not local_id:
                    raise ValueError
                if event == "budget_reserve":
                    if (
                        local_id in self._open
                        or local_id in self._settled
                        or local_id in self._released
                    ):
                        raise ValueError
                    reservation = Reservation(**record["reservation"])
                    if (
                        datetime.strptime(reservation.month, "%Y-%m").strftime("%Y-%m")
                        != reservation.month
                    ):
                        raise ValueError
                    if any(
                        type(v) is not int or v <= 0
                        for k, v in record["reservation"].items()
                        if k != "month"
                    ):
                        raise ValueError
                    self._open[local_id] = reservation
                elif event == "budget_settle":
                    reservation = self._open.pop(local_id)
                    amount = record["amount_micro"]
                    if (
                        type(amount) is not int
                        or amount < 0
                        or type(record["estimated"]) is not bool
                    ):
                        raise ValueError
                    self._settled[local_id] = amount
                    self._spent[reservation.month] = self._spent.get(reservation.month, 0) + amount
                elif event == "budget_release":
                    self._open.pop(local_id)
                    self._released.add(local_id)
        except (KeyError, TypeError, ValueError):
            journal.failed = True
            raise JournalError("Ungültiger Budgetzustand im Journal") from None

    def _month(self) -> str:
        now = self._clock()
        if now.tzinfo is None:
            raise ValueError("Budgetuhr benötigt eine Zeitzone")
        return now.astimezone(UTC).strftime("%Y-%m")

    @property
    def reservations(self) -> dict[str, Reservation]:
        return dict(self._open)

    def is_closed(self, local_id: str) -> bool:
        """Auch ein Absturz zwischen Buchung und Session-Abschluss ist rekonstruierbar."""
        return local_id in self._settled or local_id in self._released

    def has_id(self, local_id: str) -> bool:
        return local_id in self._open or self.is_closed(local_id)

    def set_provider_blocked(self, blocked: bool = True) -> None:
        """Guthabensperre freigeben; eine Journalsperre wird dadurch niemals aufgehoben."""
        self._provider_blocked = blocked

    def status(self) -> BudgetStatus:
        spent = self._spent.get(self._month(), 0)
        bound = sum(r.total for r in self._open.values())
        total = spent + bound
        return BudgetStatus(
            limit_micro=self.limit_micro,
            spent_micro=spent,
            bound_micro=bound,
            warning=total >= self.limit_micro * self.warn_ratio,
            blocked=(
                self._provider_blocked
                or self.journal.failed
                or total + sum(self._defaults[:2]) > self.limit_micro
            ),
        )

    def _warn(self) -> None:
        status = self.status()
        if status.warning and self._oplog is not None:
            try:
                self._oplog.write(
                    "budget_warnung", spent_micro=status.spent_micro, bound_micro=status.bound_micro
                )
            except OSError:
                # Ein fehlendes Log darf keine bereits persistierte Buchung zurückrollen.
                pass

    async def reserve(self, local_id: str) -> None:
        await durable(self._reserve(local_id))

    async def _reserve(self, local_id: str) -> None:
        async with self._lock:
            if self.journal.failed or self._provider_blocked:
                raise StartsBlocked
            if not isinstance(local_id, str) or not local_id:
                raise ValueError("Reservierungs-ID fehlt")
            if local_id in self._open or local_id in self._settled or local_id in self._released:
                raise ValueError("Reservierungs-ID bereits verwendet")
            if self.status().blocked:
                raise BudgetExhausted
            reservation = Reservation(self._month(), *self._defaults)
            await self.journal.append(
                "budget_reserve", local_id=local_id, reservation=asdict(reservation)
            )
            self._open[local_id] = reservation
            self._warn()

    async def settle(self, local_id: str, *, usage: UsageSummary, closure: CloseOutcome) -> int:
        return await durable(self._settle(local_id, usage=usage, closure=closure))

    async def _settle(self, local_id: str, *, usage: UsageSummary, closure: CloseOutcome) -> int:
        async with self._lock:
            if local_id in self._settled:
                return self._settled[local_id]
            reservation = self._open[local_id]
            if not closure.confirmed:
                return 0  # Keine Buchung; die volle Reservierung bleibt offen.
            live_missing = usage.live_seconds is None or not usage.final
            if usage.live_seconds is not None and (
                type(usage.live_seconds) is not int or usage.live_seconds < 0
            ):
                raise ValueError("Ungültige Live-Usage")
            seconds = usage.live_seconds or 0
            if closure.reason == "attach_fehler":
                seconds = max(15, seconds)
            live = (seconds * reservation.live_per_minute_micro + 59) // 60
            if live_missing:
                live = max(live, reservation.live_micro)
            tokens = usage.backend_tokens
            if any(type(v) is not int or v < 0 for v in tokens.values()):
                raise ValueError("Ungültige Backend-Usage")
            backend = (
                tokens.get("input_tokens", 0) * reservation.input_per_million_micro
                + tokens.get("output_tokens", 0) * reservation.output_per_million_micro
                + 999_999
            ) // 1_000_000
            backend_missing = not usage.backend_complete or not usage.final
            # Ein leeres vollständiges Aggregat bedeutet: kein Backend-Aufruf gesehen.
            if tokens and not {"input_tokens", "output_tokens"} <= tokens.keys():
                backend_missing = True
            if backend_missing:
                backend = max(backend, reservation.backend_micro)
            amount = live + backend
            await self.journal.append(
                "budget_settle",
                local_id=local_id,
                amount_micro=amount,
                estimated=live_missing or backend_missing,
            )
            self._settled[local_id] = amount
            self._spent[reservation.month] = self._spent.get(reservation.month, 0) + amount
            del self._open[local_id]
            self._warn()
            return amount

    async def release_uncreated(self, local_id: str) -> None:
        await durable(self._release(local_id))

    async def _release(self, local_id: str) -> None:
        async with self._lock:
            if local_id in self._released:
                return
            if local_id not in self._open:
                raise ValueError("Keine offene Reservierung")
            await self.journal.append("budget_release", local_id=local_id)
            del self._open[local_id]
            self._released.add(local_id)
