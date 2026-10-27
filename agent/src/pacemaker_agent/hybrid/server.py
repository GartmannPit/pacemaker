"""Verdrahtung und Start des Hybrid-Servers (`pacemaker-server serve`).

Reihenfolge (Teil-A-Bericht): Journal → Betriebslog → Budget → Register → Wiederanlauf;
Starts erst, wenn das Register bereit ist. Beenden: keine neuen Starts, Register schließen,
Journal und Betriebslog schließen.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import aiohttp
from aiohttp import web
from dotenv import load_dotenv

from ..personas.kaltakquise_head_of_ops import HANGUP_TOOL, system_prompt
from .app import AppConfig, create_app
from .auth import Auth, UserFile
from .budget import Budget
from .contracts import MICRO_USD
from .journal import Journal
from .live import LiveSettings, LiveStarter
from .oplog import OpLog, configure_logging
from .sessions import SessionRegistry

AGENT_DIR = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class ServerConfig:
    live: LiveSettings
    users_file: Path
    state_dir: Path
    app: AppConfig
    host: str
    port: int
    max_parallel: int
    max_duration_s: float
    budget_micro: int


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"{name} ist nicht gesetzt (siehe agent/.env.example).")
    return value


def load_config() -> ServerConfig:
    """Explizite Konfiguration, kein Fallback (CLAUDE.md); verständlich abbrechen."""
    load_dotenv(AGENT_DIR / ".env")
    origin = _require("PACEMAKER_PUBLIC_ORIGIN").rstrip("/")
    parts = urlsplit(origin)
    loopback = parts.hostname in ("localhost", "127.0.0.1")
    dev = os.environ.get("PACEMAKER_DEV_LOOPBACK") == "1"
    if dev and not (loopback and parts.scheme == "http"):
        raise SystemExit("PACEMAKER_DEV_LOOPBACK=1 nur mit http://localhost als Origin.")
    if not dev and parts.scheme != "https":
        raise SystemExit("PACEMAKER_PUBLIC_ORIGIN muss https:// sein (Mikrofon, Cookies).")
    if parts.path or parts.query or parts.fragment:
        raise SystemExit("PACEMAKER_PUBLIC_ORIGIN nur Schema, Host und Port.")
    max_duration = float(os.environ.get("PACEMAKER_MAX_DURATION_S", "600"))
    if not 0 < max_duration <= 600:
        raise SystemExit("PACEMAKER_MAX_DURATION_S muss zwischen 1 und 600 liegen.")
    try:
        live = LiveSettings(
            region=_require("OPENAI_LIVE_REGION"),
            api_key=_require("OPENAI_API_KEY"),
            backend_model=os.environ.get("OPENAI_LIVE_BACKEND_MODEL", "gpt-4.1-mini"),
            prompt=system_prompt(short_opener=False),
            hangup_tool=HANGUP_TOOL,
        )
    except ValueError as exc:
        raise SystemExit(f"{exc} (erlaubt: eu, referenz).") from exc
    return ServerConfig(
        live=live,
        users_file=Path(_require("PACEMAKER_USERS_FILE")).expanduser(),
        state_dir=Path(_require("PACEMAKER_STATE_DIR")).expanduser(),
        app=AppConfig(public_origin=origin, dev_loopback=dev),
        host=os.environ.get("PACEMAKER_HOST", "127.0.0.1"),
        port=int(os.environ.get("PACEMAKER_PORT", "8080")),
        max_parallel=int(os.environ.get("PACEMAKER_MAX_PARALLEL", "20")),
        max_duration_s=max_duration,
        budget_micro=round(float(os.environ.get("PACEMAKER_BUDGET_USD", "25")) * MICRO_USD),
    )


def build(cfg: ServerConfig) -> web.Application:
    journal = Journal(cfg.state_dir)  # Prozesssperre; beschädigt → Abbruch
    oplog = OpLog(cfg.state_dir / "betrieb.jsonl")
    configure_logging(oplog)
    budget = Budget(journal, limit_micro=cfg.budget_micro, oplog=oplog)
    auth = Auth(UserFile(cfg.users_file))
    holder: dict = {}

    def registry():
        return holder["registry"]

    class _Proxy:
        async def start(self, user_id, sdp, voice):
            return await registry().start(user_id, sdp, voice)

        async def end(self, user_id, session_ref, *, reason):
            return await registry().end(user_id, session_ref, reason=reason)

    app = create_app(
        auth=auth,
        registry=_Proxy(),
        budget_status=budget.status,
        ready=lambda: "registry" in holder and registry().ready,
        config=cfg.app,
        oplog=oplog,
    )

    async def startup(_app: web.Application) -> None:
        holder["http"] = aiohttp.ClientSession()
        holder["registry"] = SessionRegistry(
            budget,
            LiveStarter(cfg.live, holder["http"]),
            journal,
            oplog,
            max_parallel=cfg.max_parallel,
            max_duration_s=cfg.max_duration_s,
        )
        oplog.write("server_start")
        await registry().recover()

    async def cleanup(_app: web.Application) -> None:
        if "registry" in holder:
            await registry().shutdown()
        if "http" in holder:
            await holder["http"].close()
        oplog.write("server_ende")
        journal.close()
        oplog.close()

    app.on_startup.append(startup)
    app.on_cleanup.append(cleanup)
    return app


def serve() -> None:
    cfg = load_config()
    print(f"Pacemaker-Server: {cfg.app.public_origin} (Region {cfg.live.region})")
    web.run_app(build(cfg), host=cfg.host, port=cfg.port, access_log=None, print=None)
