"""Betriebslog ohne Freitext, Payloads oder Exception-Darstellung."""

from __future__ import annotations

import json
import logging
import math
import os
import re
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, get_args

from .contracts import EndReason, SessionState

EVENTS = frozenset(
    {
        "budget_warnung",
        "sitzung_status",
        "framework_log",
        "provider_gesperrt",
        "start_abgewiesen",
        "start_fehlgeschlagen",
        "anmeldung",
        "abmeldung",
        "http_request",
        "server_start",
        "server_ende",
    }
)
_IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
_CODES = frozenset(
    {
        "start_abgewiesen",
        "nutzer_hat_gespraech",
        "kapazitaet_erschoepft",
        "budget_erschoepft",
        "starts_gesperrt",
        "start_fehlgeschlagen",
        "provider_gesperrt",
        "erzeugung_ungeklaert",
        "angebot_abgelehnt",
        "provider_konfiguration",
        "provider_nicht_verfuegbar",
    }
)


class OpLog:
    """Nur bekannte Ereignisse und typisierte Metadaten werden geschrieben.

    Insbesondere werden message, args, exc_info und Stacktraces nie formatiert.
    session_ref darf ausschließlich die lokal erzeugte Zufallsreferenz enthalten.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._fd = os.open(self.path, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
        os.fchmod(self._fd, 0o600)
        self._lock = threading.Lock()

    def write(self, event: str, **fields: Any) -> None:
        if event not in EVENTS:
            return
        row: dict[str, Any] = {"timestamp": datetime.now(UTC).isoformat(), "event": event}
        for key, value in fields.items():
            if key in {"spent_micro", "bound_micro", "limit_micro", "status", "level", "count"}:
                if type(value) is int and 0 <= value <= 2**63 - 1:
                    row[key] = value
            elif key == "duration_s":
                if type(value) in (int, float) and math.isfinite(value) and value >= 0:
                    row[key] = value
            elif key == "session_ref":
                if isinstance(value, str) and _IDENTIFIER.fullmatch(value):
                    row[key] = value
            elif key == "state" and isinstance(value, str) and value in get_args(SessionState):
                row[key] = value
            elif key == "reason" and isinstance(value, str) and value in get_args(EndReason):
                row[key] = value
            elif key == "code" and isinstance(value, str) and value in _CODES:
                row[key] = value
            elif key == "method" and value in ("GET", "POST", "HEAD", "OPTIONS"):
                row[key] = value
            elif key == "provider_status":
                if type(value) is int and 100 <= value <= 599:
                    row[key] = value
            elif key == "provider_code":
                # Nur Bezeichner wie "insufficient_quota", nie Fehlertext des Providers
                if isinstance(value, str) and _IDENTIFIER.fullmatch(value):
                    row[key] = value
        data = (json.dumps(row, allow_nan=False, separators=(",", ":")) + "\n").encode()
        with self._lock:
            view = memoryview(data)
            while view:
                written = os.write(self._fd, view)
                if written <= 0:
                    raise OSError("Betriebslog nicht geschrieben")
                view = view[written:]

    def logging_handler(self) -> logging.Handler:
        return _SafeHandler(self)

    def loguru_sink(self, message: Any) -> None:
        """Loguru-Record nur über den numerischen Level übernehmen."""
        self.write("framework_log", level=message.record["level"].no)

    def close(self) -> None:
        with self._lock:
            if self._fd >= 0:
                os.close(self._fd)
                self._fd = -1


class _SafeHandler(logging.Handler):
    def __init__(self, oplog: OpLog) -> None:
        super().__init__()
        self.oplog = oplog

    def emit(self, record: logging.LogRecord) -> None:
        # Auch bei Schreibfehlern kein handleError(): dessen stderr enthält den Roh-Record.
        self.oplog.write("framework_log", level=record.levelno)


def configure_logging(oplog: OpLog, *, include_loguru: bool = True) -> None:
    """Vor Serverstart bisherige Handler ersetzen, einschließlich Access-/Exception-Logs.

    Danach neu eingerichtete Framework-Handler muss die Anwendung ebenfalls entfernen.
    Die Anwendung darf keine separaten Access-Logdateien konfigurieren.
    """
    root = logging.getLogger()
    root.handlers[:] = [oplog.logging_handler()]
    root.setLevel(logging.INFO)
    for logger in logging.Logger.manager.loggerDict.copy().values():
        if isinstance(logger, logging.Logger):
            logger.handlers.clear()
            logger.propagate = True
    if include_loguru:
        from loguru import logger

        logger.remove()
        logger.add(oplog.loguru_sink, backtrace=False, diagnose=False, catch=False)
