"""Sitzungsfehler und unverfaelschte Usage/Rate-Limits aus Pipecat 1.12.

Live-Usage ist kumulativ in Sekunden; Backend-Tokens sind keine Live-Tokens.
Keine Header, Exception-Texte, Prompts, Audiodaten oder Transkripte speichern.
Die privaten Hooks sind gegen die installierte Version mit Mocks abgesichert.
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, datetime

from .collector import RUNS_DIR
from .run_manifest import update_manifest


def instrument(base: type, run_id: str) -> type:
    """Erfasst Ereignisse vor Pipecats Dispatch, auch unbekannte Rate-Limit-Typen."""
    path = RUNS_DIR / "live_usage" / f"{run_id}.jsonl"
    errors: list[dict] = []
    error_lock = asyncio.Lock()

    def append(row: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")

    class ObservedLiveService(base):
        _load_closing = False
        _load_error_details: dict | None = None

        async def _load_write(self, **data) -> None:
            await asyncio.to_thread(
                append,
                {"run_id": run_id, "ts": datetime.now(UTC).isoformat(), "t": time.time(), **data},
            )

        async def _load_error(self, kind: str, **data) -> None:
            row = {"ts": datetime.now(UTC).isoformat(), "kind": kind, **data}
            async with error_lock:
                errors.append(row)
                # Auch Fehler vor dem ersten Clip und parallele Sende-/Empfangsfehler sichern.
                await asyncio.to_thread(update_manifest, run_id, service_errors=list(errors))
            await self._load_write(type="service_error", error=row)

        async def push_error(
            self, error_msg: str, exception: Exception | None = None, **kwargs
        ) -> None:
            response = getattr(exception, "response", None)
            status = getattr(response, "status_code", None) or getattr(
                exception, "status_code", None
            )
            await self._load_error(
                "sitzungsablehnung" if not self._session_started_on_connection else "dienstfehler",
                http_status=status,
                exception=type(exception).__name__ if exception else None,
                **(self._load_error_details or {}),
            )
            return await super().push_error(error_msg, exception=exception, **kwargs)

        async def _handle_server_event(self, evt):
            kind = evt.type
            if (
                kind not in {"session.started", "session.closed", "response.event", "error"}
                and not hasattr(evt, "usage")
                and "rate_limit" not in kind
            ):
                return await super()._handle_server_event(evt)
            payload = evt.model_dump(exclude_none=True)
            usage = payload.get("usage")
            if kind == "response.event":
                inner = payload.get("event", {})
                response = inner.get("response") or {}
                usage = response.get("usage")
                if usage is not None:
                    await self._load_write(
                        type=inner.get("type"),
                        source="backend",
                        usage=usage,
                        response_id=response.get("id"),
                        event_id=evt.event_id,
                    )
            elif usage is not None or "rate_limit" in kind:
                await self._load_write(
                    type=kind,
                    source="live",
                    usage=usage,
                    rate_limits=payload.get("rate_limits"),
                    rate_limit_event=payload if "rate_limit" in kind else None,
                    context_window=payload.get("context_window"),
                    event_id=evt.event_id,
                )
            if kind == "session.started":
                await self._load_write(type=kind, source="live", session_id=evt.session.id)
            if kind == "session.closed" and not self._load_closing:
                await self._load_error("unerwartetes_sitzungsende", code=payload.get("reason"))
                await super().push_error(
                    "Unerwartetes session.closed", force_treat_as_permanent=True
                )
            if kind == "error":
                error = payload.get("error", {})
                self._load_error_details = {
                    "code": error.get("code"),
                    "error_type": error.get("type"),
                }
            try:
                return await super()._handle_server_event(evt)
            finally:
                self._load_error_details = None

        async def _receive_task_handler(self):
            before = len(errors)
            try:
                return await super()._receive_task_handler()
            finally:
                # async-for endet bei sauberem WebSocket-Close (1000/1001) ohne Exception.
                if not self._load_closing and len(errors) == before:
                    await self._load_error("verbindungsabbruch")
                    await super().push_error(
                        "Unerwartetes Ende des Live-WebSockets", force_treat_as_permanent=True
                    )

        async def _close_session(self):
            self._load_closing = True
            result = await super()._close_session()
            if getattr(self, "_session_started", False):
                await self._load_error("sitzungsende_unbestaetigt")
            return result

        async def _disconnect(self):
            self._load_closing = True
            return await super()._disconnect()

    return ObservedLiveService
