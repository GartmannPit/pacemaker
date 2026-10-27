"""Dauerhaftes Lebenszyklusjournal mit exklusiver Prozesssperre."""

from __future__ import annotations

import asyncio
import fcntl
import json
import os
from collections.abc import Coroutine
from pathlib import Path
from typing import Any


class JournalError(Exception):
    """Der Zustand ist nicht zuverlässig lesbar oder schreibbar."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Doppeltes Journalfeld")
        result[key] = value
    return result


def _invalid_constant(_value: str) -> None:
    raise ValueError("Ungültiger JSON-Zahlenwert")


class Journal:
    """Ein Eigentümer je State-Verzeichnis; erst nach Registry.shutdown() schließen.

    Lesen und Sperren erfolgen beim Aufbau, Schreibzugriffe außerhalb des Event-Loops.
    Nach einem Schreibfehler bleibt das Journal bis zum Neustart gesperrt.
    """

    def __init__(self, state_dir: str | Path) -> None:
        self.state_dir = Path(state_dir)
        self.failed = False
        self._closed = False
        self._lock = asyncio.Lock()
        self._records: list[dict[str, Any]] = []
        self._lock_fd: int | None = None
        self._fd: int | None = None
        try:
            self.state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.chmod(self.state_dir, 0o700)
            self._lock_fd = os.open(self.state_dir / "state.lock", os.O_CREAT | os.O_RDWR, 0o600)
            fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            path = self.state_dir / "journal.jsonl"
            self._fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_APPEND, 0o600)
            os.fchmod(self._fd, 0o600)
            with path.open("rb") as stream:
                for line in stream:
                    # Auch eine syntaktisch vollständige letzte Zeile braucht den Commit-Umbruch.
                    if not line.endswith(b"\n"):
                        raise ValueError("Unvollständige Journalzeile")
                    record = json.loads(
                        line, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
                    )
                    self._validate(record)
                    self._records.append(record)
            os.fsync(self._fd)
            directory = os.open(self.state_dir, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except (OSError, ValueError, TypeError):
            self.failed = True
            self.close()
            raise JournalError("State-Verzeichnis gesperrt oder Journal beschädigt") from None

    @staticmethod
    def _validate(record: Any) -> None:
        if (
            not isinstance(record, dict)
            or type(record.get("version")) is not int
            or record.get("version") != 1
            or record.get("event")
            not in {"budget_reserve", "budget_settle", "budget_release", "session"}
        ):
            raise ValueError("Ungültiger Journaleintrag")

    @property
    def records(self) -> list[dict[str, Any]]:
        """Kopie des bisher dauerhaft gespeicherten Zustands."""
        return [json.loads(json.dumps(record)) for record in self._records]

    def _write(self, data: bytes) -> None:
        if self._fd is None or self._closed:
            raise OSError("Journal geschlossen")
        view = memoryview(data)
        while view:
            written = os.write(self._fd, view)
            if written <= 0:
                raise OSError("Journal nicht geschrieben")
            view = view[written:]
        os.fsync(self._fd)

    async def append(self, event: str, **fields: Any) -> None:
        """Eine vollständige Zeile schreiben; kein stiller Rückfall auf flüchtigen Zustand."""
        async with self._lock:
            if self.failed or self._closed:
                raise JournalError("Journal gesperrt")
            record = {"version": 1, "event": event, **fields}
            try:
                self._validate(record)
                data = (json.dumps(record, allow_nan=False, separators=(",", ":")) + "\n").encode()
                write = asyncio.create_task(asyncio.to_thread(self._write, data))
                try:
                    await asyncio.shield(write)
                except asyncio.CancelledError:
                    # Den Dateideskriptor erst nach Abschluss des Schreibens freigeben.
                    await write
                    self._records.append(record)
                    raise
                self._records.append(record)
            except (OSError, ValueError, TypeError):
                self.failed = True
                raise JournalError("Journal konnte nicht dauerhaft geschrieben werden") from None

    def close(self) -> None:
        """Nach Abschluss aller asynchronen Operationen Dateideskriptoren freigeben."""
        self._closed = True
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        if self._lock_fd is not None:
            os.close(self._lock_fd)
            self._lock_fd = None

    def __enter__(self) -> Journal:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


async def durable[T](operation: Coroutine[Any, Any, T]) -> T:
    """Eine lokale Transaktion trotz Abbruch ihres Aufrufers zu Ende führen."""
    task = asyncio.create_task(operation)
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        # Wiederholtes cancel() darf die Transaktion ebenfalls nicht abbrechen.
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
        task.result()
        raise
