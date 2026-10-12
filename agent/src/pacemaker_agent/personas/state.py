"""Gespraechszustand einer Persona (docs/phase-1-personas-entwurf.md §4).

Der Protokollant (`protocol.py`) liefert je Turn Ereignisse; dieser Code rechnet daraus
Schmerzpunkt-Stufen, Geduld, Offenheit und Meilensteine. Die Zustandsaenderung ist bewusst
deterministisch und ohne LLM -- nachvollziehbar und testbar. Eingabe sind nur Ereignisse aus
dem Transkripttext, keine Stimm- oder Emotionsmerkmale (CLAUDE.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .model import (
    OBJECTION_EVENTS,
    PAIN_EVENTS,
    STAGE_CONFIRMED,
    STAGE_HIDDEN,
    STAGE_UNCOVERED,
    EventKind,
    Milestone,
    Persona,
    openness_band,
)

# Unter dieser Zahl Persona-Beitraege fordert die Regie kein Auflegen (Prompt: in den ersten
# drei Redebeitraegen nicht auflegen, Prompt-Durchgang 2).
MIN_TURNS_BEFORE_HANGUP = 3
LOW_PATIENCE = 2
_STAGE_LABEL = {STAGE_UNCOVERED: "aufgedeckt", STAGE_CONFIRMED: "bestaetigt"}


@dataclass(frozen=True)
class Event:
    kind: EventKind
    ref: str | None = None  # Schmerzpunkt- bzw. Einwand-ID
    evidence: str = ""  # Transkriptstelle, auf die sich das Ereignis stuetzt


@dataclass
class MilestoneHit:
    id: str
    turn: int
    evidence: str
    gate_violated: bool = False  # Persona stimmte zu, obwohl das Tor zu war


@dataclass
class ConversationState:
    persona: Persona
    patience: int = 0
    openness: int = 0
    persona_turns: int = 0
    pain_stages: dict[str, int] = field(default_factory=dict)
    # Schmerzpunkte, die die Persona von sich aus verraten hat (zaehlen nicht fuer Meilensteine)
    leaked: set[str] = field(default_factory=set)
    # Zusagen ueber das Werkzeug, gewertet beim naechsten apply()
    pending: list[Event] = field(default_factory=list)
    milestones: dict[str, MilestoneHit] = field(default_factory=dict)
    history: list[dict] = field(default_factory=list)

    @classmethod
    def start(cls, persona: Persona) -> ConversationState:
        d = persona.dynamics
        return cls(
            persona=persona,
            patience=d.patience_start,
            openness=d.openness_start,
            pain_stages={p.id: STAGE_HIDDEN for p in persona.pains},
        )

    # -- Abfragen -------------------------------------------------------------------------

    @property
    def attitude(self) -> str:
        return openness_band(self.openness)

    @property
    def wants_to_end_call(self) -> bool:
        return self.patience <= 0 and self.persona_turns >= MIN_TURNS_BEFORE_HANGUP

    def gate_open(self, milestone: Milestone) -> bool:
        gate = milestone.gate
        if gate is None:
            return True
        return self.openness >= gate.min_openness and all(
            r in self.milestones for r in gate.requires
        )

    # -- Zusagen (Werkzeug `zusagen`) -----------------------------------------------------

    def request_agreement(self, kind: EventKind, detail: str = "") -> bool:
        """Die Persona will zusagen. Der Code entscheidet nach dem Tor, nicht das LLM.

        Erlaubt: Ereignis wird fuer den laufenden Turn vorgemerkt (Meilenstein beim naechsten
        apply()). Abgelehnt: nichts passiert, die Persona muss ausweichen.
        """
        milestone = next((m for m in self.persona.milestones if m.event is kind), None)
        if milestone is None:
            return False
        if milestone.id in self.milestones or self.gate_open(milestone):
            self.pending.append(Event(kind, evidence=detail or "Zusage per Werkzeug"))
            return True
        return False

    # -- Fortschreiben --------------------------------------------------------------------

    def apply(self, events: list[Event], *, persona_spoke: bool = True) -> list[Event]:
        """Wendet die Ereignisse eines Turns an. Gibt die tatsaechlich gewerteten zurueck.

        Reihenfolge: Tore werden gegen den Stand **vor** diesem Turn geprueft (die Persona
        hat nach der Regie des vorigen Turns geantwortet), danach Stufen und Stimmung.
        """
        if persona_spoke:
            self.persona_turns += 1
        turn = self.persona_turns
        accepted = self._filter([*self.pending, *events])
        self.pending.clear()

        gates_before = {m.id: self.gate_open(m) for m in self.persona.milestones}
        for event in accepted:
            if event.kind in PAIN_EVENTS and event.ref is not None:
                self._advance_pain(event)
            dp, do = self.persona.dynamics.weights.get(event.kind, (0, 0))
            self.patience = _clamp(self.patience + dp, 0, 10)
            self.openness = _clamp(self.openness + do, 0, self.persona.dynamics.openness_cap)

        self._derive_milestones(accepted, turn, gates_before)
        self.history.append(
            {
                "turn": turn,
                "events": [
                    {"art": e.kind.value, "bezug": e.ref, "beleg": e.evidence} for e in accepted
                ],
                **self.snapshot(),
            }
        )
        return accepted

    def _filter(self, events: list[Event]) -> list[Event]:
        """Verwirft unbekannte Bezuege und mehr als eine Stufe je Schmerzpunkt und Turn."""
        accepted: list[Event] = []
        moved: set[str] = set()
        seen: set[tuple[EventKind, str | None]] = set()
        for e in events:
            if (e.kind, e.ref) in seen:
                continue
            if e.kind in PAIN_EVENTS:
                if e.ref is None or self.persona.pain(e.ref) is None or e.ref in moved:
                    continue
                stage = self.pain_stages[e.ref]
                if (
                    e.kind in (EventKind.PAIN_UNCOVERED, EventKind.PAIN_LEAKED)
                    and stage >= STAGE_UNCOVERED
                ):
                    continue
                if e.kind is EventKind.PAIN_CONFIRMED and stage != STAGE_UNCOVERED:
                    continue  # bestaetigen setzt aufgedeckt voraus, nie zwei Stufen auf einmal
                moved.add(e.ref)
            if e.kind in OBJECTION_EVENTS and (
                e.ref is not None and self.persona.objection(e.ref) is None
            ):
                continue
            seen.add((e.kind, e.ref))
            accepted.append(e)
        return accepted

    def _advance_pain(self, event: Event) -> None:
        assert event.ref is not None
        if event.kind is EventKind.PAIN_LEAKED:
            self.leaked.add(event.ref)
        target = STAGE_CONFIRMED if event.kind is EventKind.PAIN_CONFIRMED else STAGE_UNCOVERED
        self.pain_stages[event.ref] = max(self.pain_stages[event.ref], target)

    def _derive_milestones(
        self, events: list[Event], turn: int, gates_before: dict[str, bool]
    ) -> None:
        by_kind = {e.kind: e for e in events}
        for m in self.persona.milestones:
            if m.id in self.milestones:
                continue
            evidence: str | None = None
            if m.min_persona_turns is not None and self.persona_turns >= m.min_persona_turns:
                evidence = f"{self.persona_turns} Beitraege ohne Auflegen"
            elif m.pain_stage is not None:
                reached = [
                    p
                    for p, s in self.pain_stages.items()
                    if s >= m.pain_stage and p not in self.leaked
                ]
                if reached:
                    hit = next(
                        (e for e in events if e.kind in PAIN_EVENTS and e.ref in reached), None
                    )
                    evidence = hit.evidence if hit else ", ".join(reached)
            elif m.event is not None and m.event in by_kind:
                evidence = by_kind[m.event].evidence
            if evidence is None:
                continue
            self.milestones[m.id] = MilestoneHit(
                id=m.id,
                turn=turn,
                evidence=evidence,
                gate_violated=m.gate is not None and not gates_before[m.id],
            )

    # -- Ausgabe --------------------------------------------------------------------------

    def snapshot(self) -> dict:
        return {
            "geduld": self.patience,
            "offenheit": self.openness,
            "haltung": self.attitude,
            "schmerzpunkte": dict(self.pain_stages),
            "verraten": sorted(self.leaked),
            "meilensteine": {
                k: {"turn": v.turn, "beleg": v.evidence, "tor_verletzt": v.gate_violated}
                for k, v in self.milestones.items()
            },
        }

    def director_line(self) -> str:
        """Regiezeile fuer den naechsten Persona-Turn (Entwurf §4.6)."""
        p = self.persona
        lines = [
            f"[Regie -- nie aussprechen] Haltung: {self.attitude}. Geduld: {self.patience}/10."
        ]
        uncovered = [
            f"{pp.title} ({_STAGE_LABEL[self.pain_stages[pp.id]]})"
            for pp in p.pains
            if self.pain_stages[pp.id] >= STAGE_UNCOVERED
        ]
        hidden = [pp.title for pp in p.pains if self.pain_stages[pp.id] < STAGE_UNCOVERED]
        lines.append(
            f"Aufgedeckt: {', '.join(uncovered) or 'nichts'}. "
            f"Noch verborgen: {', '.join(hidden) or 'nichts'}."
        )
        if self.wants_to_end_call:
            lines.append(
                "Deine Geduld ist aufgebraucht: Beende das Gespraech jetzt hoeflich ueber "
                "das Werkzeug auflegen."
            )
        elif self.patience <= LOW_PATIENCE:
            lines.append("Deine Geduld ist fast aufgebraucht: sehr knapp antworten.")
        return "\n".join(lines)


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))
