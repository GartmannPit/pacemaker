"""Datenformat fuer Personas (docs/phase-1-personas-entwurf.md §2, §4).

Eine Persona ist reine Daten: Rolle, Uebungsprodukt, harte Fakten, verdeckte Schmerzpunkte,
Einwaende, Stimmungsparameter und Meilensteine mit Toren. Den Systemprompt erzeugt
`prompt.py`, den Gespraechszustand fuehrt `state.py`. Verhaltensregeln (KI-Transparenz, kurze
Antworten, Auflegen) stehen nicht hier, sondern zentral in `prompt.py` -- auch kuenftige
Kunden-Personas koennen sie nicht wegkonfigurieren.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class EventKind(StrEnum):
    """Ereignisse, die der Protokollant je Turn erkennt -- nur aus Transkripttext."""

    # Vom Protokollanten (LLM) erkannt
    GOOD_OPEN_QUESTION = "gute_offene_frage"
    CONCRETE_REFERENCE = "konkreter_bezug"
    PAIN_UNCOVERED = "schmerz_aufgedeckt"
    PAIN_CONFIRMED = "schmerz_bestaetigt"
    CLAIM_INSTEAD_OF_QUESTION = "behauptung_statt_frage"
    OBJECTION_ADDRESSED = "einwand_behandelt"
    OBJECTION_IGNORED = "einwand_uebergangen"
    EARLY_CLOSING = "druck_zu_frueh"
    EVASION = "ausweichen"
    # Ueber das Werkzeug `zusagen` (Tor im Code geprueft)
    MAIL_AGREED = "mail_zugestimmt"
    MEETING_AGREED = "termin_zugestimmt"
    # Persona erzaehlt ein Problem, ohne dass danach gefragt wurde (Fehler der Persona, kein
    # Verdienst des SDR): Problem liegt auf dem Tisch, zaehlt aber nicht fuer Meilensteine.
    PAIN_LEAKED = "schmerz_verraten"
    # Deterministisch im Code erkannt (protocol.py)
    MONOLOGUE = "monolog"
    REPETITION = "wiederholung"


# Ereignisse mit Bezug auf einen Schmerzpunkt bzw. Einwand (Feld `ref`)
# Zusagen der Persona: entstehen nur ueber das Werkzeug `zusagen` (prompt.py), das der Code
# gegen das Tor prueft -- nie aus dem Urteil des Protokollanten.
AGREEMENTS: dict[str, EventKind] = {
    "mail": EventKind.MAIL_AGREED,
    "termin": EventKind.MEETING_AGREED,
}

PAIN_EVENTS = {EventKind.PAIN_UNCOVERED, EventKind.PAIN_CONFIRMED, EventKind.PAIN_LEAKED}
OBJECTION_EVENTS = {EventKind.OBJECTION_ADDRESSED, EventKind.OBJECTION_IGNORED}


@dataclass(frozen=True)
class Product:
    """Uebungsprodukt: was der SDR in diesem Szenario verkauft."""

    name: str
    benefit: str  # ein Satz Nutzen
    price_range: str


@dataclass(frozen=True)
class PainPoint:
    id: str
    title: str  # kurz, fuer Regiezeile und Auswertung
    situation: str  # was die Persona erzaehlt, wenn er aufgedeckt ist
    trigger: str  # wonach der SDR fragen muss
    example_questions: tuple[str, ...]
    impact: str  # nennt die Persona beim Bestaetigen
    # Phase 2 (Schwierigkeit "leicht"): vager Hinweis auf Stufe 1. In Phase 1 ungenutzt.
    hint: str = ""


@dataclass(frozen=True)
class Objection:
    id: str
    text: str  # sinngemaess, nie als fester Satz
    convinced_by: str
    lost_by: str


@dataclass(frozen=True)
class Gate:
    """Voraussetzung, damit die Persona einem Meilenstein zustimmt."""

    min_openness: int = 0
    requires: tuple[str, ...] = ()  # Meilenstein-IDs


@dataclass(frozen=True)
class Milestone:
    """Meilenstein mit Bedingung (genau eine der Bedingungsarten ist gesetzt).

    - `min_persona_turns`: so viele Persona-Beitraege ohne Auflegen
    - `pain_stage`: irgendein Schmerzpunkt hat mindestens diese Stufe (2 aufgedeckt,
      3 bestaetigt)
    - `event`: Ereignis kam vor (z. B. Einwand behandelt, Termin zugestimmt)
    """

    id: str
    label: str
    min_persona_turns: int | None = None
    pain_stage: int | None = None
    event: EventKind | None = None
    gate: Gate | None = None
    is_goal: bool = False  # Hauptziel (sonst Teilziel)


# Stufen der Schmerzpunkte (Entwurf §4.3)
STAGE_HIDDEN, STAGE_HINTED, STAGE_UNCOVERED, STAGE_CONFIRMED = 0, 1, 2, 3


DEFAULT_WEIGHTS: dict[EventKind, tuple[int, int]] = {
    # Ereignis: (Geduld, Offenheit)
    EventKind.PAIN_UNCOVERED: (1, 2),
    EventKind.PAIN_CONFIRMED: (1, 2),
    EventKind.GOOD_OPEN_QUESTION: (0, 1),
    EventKind.OBJECTION_ADDRESSED: (0, 1),
    EventKind.CONCRETE_REFERENCE: (1, 0),
    EventKind.OBJECTION_IGNORED: (-1, -1),
    EventKind.EARLY_CLOSING: (-1, -2),
    EventKind.CLAIM_INSTEAD_OF_QUESTION: (0, -1),
    EventKind.MONOLOGUE: (-2, 0),
    EventKind.REPETITION: (-2, 0),
    EventKind.EVASION: (-2, 0),
}


@dataclass(frozen=True)
class Dynamics:
    """Stimmung auf zwei Achsen (Entwurf §4.4), Werte 0-10."""

    patience_start: int = 6
    openness_start: int = 3
    openness_cap: int = 10
    weights: dict[EventKind, tuple[int, int]] = field(default_factory=lambda: DEFAULT_WEIGHTS)
    monologue_words: int = 60  # SDR-Beitrag ab so vielen Woertern = Monolog


# Offenheit -> Haltung, die der Prompt kennt (untere Grenze, Bezeichnung)
OPENNESS_BANDS: tuple[tuple[int, str], ...] = (
    (8, "interessiert"),
    (6, "aufgeschlossen"),
    (3, "skeptisch"),
    (0, "abweisend"),
)


def openness_band(openness: int) -> str:
    for lower, label in OPENNESS_BANDS:
        if openness >= lower:
            return label
    return OPENNESS_BANDS[-1][1]


@dataclass(frozen=True)
class Persona:
    id: str
    name: str
    role: str
    company: str
    situation: str
    attitude: str
    product: Product
    facts: tuple[str, ...]
    pains: tuple[PainPoint, ...]
    objections: tuple[Objection, ...]
    milestones: tuple[Milestone, ...]
    dynamics: Dynamics = field(default_factory=Dynamics)
    voice: str = "de-DE-ConradNeural"  # Azure-Stimme (Germany West Central)
    scenario: str = "Kaltakquise"

    def __post_init__(self) -> None:
        _validate(self)

    def pain(self, pain_id: str) -> PainPoint | None:
        return next((p for p in self.pains if p.id == pain_id), None)

    def objection(self, objection_id: str) -> Objection | None:
        return next((o for o in self.objections if o.id == objection_id), None)

    def briefing(self) -> str:
        """Kurzbriefing fuer den SDR vor dem Gespraech (spaeter UI)."""
        return (
            f"Szenario: {self.scenario}. Sie rufen {self.name} an, {self.role} bei "
            f"{self.company}. Sie verkaufen {self.product.name}: {self.product.benefit} "
            f"Preisrahmen: {self.product.price_range}."
        )


def _validate(persona: Persona) -> None:
    """Fehler im Datenformat frueh melden statt im Gespraech."""
    for kind, items in (
        ("Schmerzpunkt", persona.pains),
        ("Einwand", persona.objections),
        ("Meilenstein", persona.milestones),
    ):
        ids = [i.id for i in items]
        if len(ids) != len(set(ids)):
            raise ValueError(f"{persona.id}: doppelte {kind}-IDs {ids}")
    milestone_ids = {m.id for m in persona.milestones}
    for m in persona.milestones:
        conditions = [m.min_persona_turns, m.pain_stage, m.event]
        if sum(c is not None for c in conditions) != 1:
            raise ValueError(f"{persona.id}/{m.id}: genau eine Bedingung setzen")
        if m.gate is not None:
            unknown = set(m.gate.requires) - milestone_ids
            if unknown:
                raise ValueError(f"{persona.id}/{m.id}: Tor verweist auf {sorted(unknown)}")
    d = persona.dynamics
    if not (0 <= d.patience_start <= 10 and 0 <= d.openness_start <= d.openness_cap <= 10):
        raise ValueError(f"{persona.id}: Stimmungswerte ausserhalb 0-10")
