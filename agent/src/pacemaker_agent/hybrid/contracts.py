"""Gemeinsame Verträge des Hybrid-Servers (docs/phase-1-schritt-1-server.md §4).

Teil A (budget, sessions, journal, oplog) und Teil B (live, auth, app, cli) bauen gegen diese
Typen. Änderungen hier nur abgestimmt und mit Review beider Seiten.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

EndReason = Literal[
    "nutzer",
    "auflegen",
    "zeitlimit",
    "inaktiv",
    "tab_geschlossen",
    "verbindung_verloren",
    "sideband_abbruch",
    "attach_fehler",
    "server_ende",
    "wiederanlauf",
]
SessionState = Literal[
    "startend",
    "laufend",
    "endend",
    "abschluss_ungeklaert",
    "erzeugung_ungeklaert",
    "beendet",
]

# Stimmen-Allowlist (Browsertest 2026-10-27); None = Vorgabe der API.
VOICES = ("vesper", "meridian", "stone", "ripple", "gleam", "willow", "quartz", "delta")

MICRO_USD = 1_000_000  # Geldbeträge als Ganzzahl in Mikro-Dollar


@dataclass(frozen=True)
class UsageSummary:
    """Verbrauch einer Sitzung; Live-Sekunden sind kumulativ, nie summieren."""

    live_seconds: int | None  # None = nicht gemeldet
    backend_tokens: dict[str, int] = field(default_factory=dict)  # input_tokens, output_tokens
    backend_complete: bool = True  # jede gesehene Backend-Response hatte Usage
    final: bool = False  # aus session.closed


@dataclass(frozen=True)
class CloseOutcome:
    confirmed: bool  # session.closed empfangen
    reason: EndReason


@dataclass(frozen=True)
class StartResult:
    session_ref: str  # zufällig, lokal; nie die Provider-ID
    answer_sdp: str


@dataclass(frozen=True)
class BudgetStatus:
    limit_micro: int
    spent_micro: int  # gebuchte Kosten im laufenden UTC-Monat
    bound_micro: int  # offene Reservierungen, monatsunabhängig
    warning: bool  # spent + bound >= Warnschwelle
    blocked: bool  # neue Starts gesperrt (Budget, Guthaben, Journalfehler)


# --- Fehler, die SessionRegistry.start() werfen darf -------------------------------------------


class StartRefused(Exception):
    """Basisklasse: Start abgewiesen, ohne Provider-Aufruf."""

    code = "start_abgewiesen"


class UserHasSession(StartRefused):
    code = "nutzer_hat_gespraech"


class CapacityExhausted(StartRefused):
    code = "kapazitaet_erschoepft"


class BudgetExhausted(StartRefused):
    code = "budget_erschoepft"


class StartsBlocked(StartRefused):
    """Starts gesperrt: Guthaben/Quota bei OpenAI, Journalfehler, Wiederanlauf läuft."""

    code = "starts_gesperrt"


class StartFailed(Exception):
    """Start nach Provider-Aufruf fehlgeschlagen; Aufräumen ist erfolgt oder eingeleitet."""

    code = "start_fehlgeschlagen"


class OfferRejected(StartFailed):
    """Provider lehnt das SDP-Angebot des Browsers ab (Client-Eingabefehler)."""

    code = "angebot_abgelehnt"


class ProviderConfig(StartFailed):
    """Authentisierung oder Konfiguration beim Provider fehlerhaft (unsere Seite)."""

    code = "provider_konfiguration"


class ProviderUnavailable(StartFailed):
    """Provider vorübergehend nicht erreichbar oder 5xx."""

    code = "provider_nicht_verfuegbar"


class ProviderBlocked(Exception):
    """Provider meldet Guthaben-/Quota-Ende; sperrt neue Starts (Starter wirft, Registry sperrt)."""

    code = "provider_gesperrt"


class CreateUnclear(Exception):
    """Erzeugung möglicherweise erfolgt (z. B. Zeitüberschreitung nach dem Senden)."""

    code = "erzeugung_ungeklaert"


# --- Protokolle ---------------------------------------------------------------------------------


class SidebandHandle(Protocol):
    async def close(self, *, reason: EndReason) -> CloseOutcome: ...

    async def wait_closed(self) -> tuple[CloseOutcome, UsageSummary]: ...

    def usage(self) -> UsageSummary: ...  # Zwischenstand

    def provider_blocked(self) -> bool: ...  # Guthaben-/Quota-Fehler während der Sitzung


class Starter(Protocol):
    """Provider-Seite (live.py); in Tests durch eine Attrappe ersetzt."""

    async def create(self, sdp: str, voice: str | None) -> tuple[str, str]:
        """Gibt (provider_id, answer_sdp). Wirft CreateUnclear, ProviderBlocked, StartFailed."""
        ...

    async def attach(
        self, provider_id: str, *, deadline_s: float, idle_timeout_s: float
    ) -> SidebandHandle:
        """deadline_s und idle_timeout_s sind verbleibende Sekunden ab jetzt."""
        ...

    async def force_close(self, provider_id: str) -> CloseOutcome: ...


class OpLog(Protocol):
    """Betriebslog mit Feld-Allowlist; unbekannte Felder werden verworfen, nicht geschrieben."""

    def write(self, event: str, **fields: Any) -> None: ...
