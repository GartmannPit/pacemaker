"""Gespraechsprotokollant (docs/phase-1-personas-entwurf.md §4.2).

Ordnet nach jedem Turn den Beitrag des Anrufers und die Antwort der Persona in feste
Ereignisse ein und schreibt den Gespraechszustand fort. Laeuft asynchron und ausserhalb des
Latenzpfads; sein Ergebnis wirkt ab dem naechsten Turn (Regiezeile).

Zaehlbares (Monolog, Wiederholung) erkennt der Code, Inhaltliches ein kleiner LLM-Aufruf
(Azure OpenAI EU, `AZURE_PROTOKOLL_DEPLOYMENT`, Default gpt-4.1-mini, Temperatur 0). Grundlage
ist ausschliesslich Transkripttext -- keine Stimm-, Emotions- oder Prosodiemerkmale.
"""

from __future__ import annotations

import json
import re
from typing import Any

from loguru import logger

from .model import OBJECTION_EVENTS, PAIN_EVENTS, EventKind, Persona
from .state import ConversationState, Event

# Vom LLM zu erkennende Ereignisse mit Definition (Code-erkannte fehlen hier bewusst)
LLM_EVENTS: dict[EventKind, str] = {
    EventKind.GOOD_OPEN_QUESTION: "Anrufer stellt eine offene Frage zur Lage des Angerufenen "
    "(keine Ja/Nein-Frage, kein Pitch in Frageform).",
    EventKind.CONCRETE_REFERENCE: "Anrufer bezieht sich konkret auf etwas, das der Angerufene "
    "gesagt hat (Zahl, Begriff, Problem).",
    EventKind.PAIN_UNCOVERED: "Anrufer hat gezielt nach dem Ausloeser eines Problems gefragt "
    "UND die Persona hat dieses Problem in ihrer Antwort konkret geschildert. bezug = Problem-ID.",
    EventKind.PAIN_CONFIRMED: "Anrufer fasst ein bereits geschildertes Problem zutreffend "
    "zusammen oder fragt nach dessen Folgen, UND die Persona bestaetigt es. bezug = Problem-ID.",
    EventKind.CLAIM_INSTEAD_OF_QUESTION: "Anrufer unterstellt ein Problem, statt danach zu "
    "fragen ('Sie haben doch sicher ...').",
    EventKind.OBJECTION_ADDRESSED: "Persona hatte im vorigen Beitrag einen Einwand gebracht; "
    "Anrufer geht mit Rueckfrage oder konkretem Unterschied darauf ein. bezug = Einwand-ID.",
    EventKind.OBJECTION_IGNORED: "Persona hatte im vorigen Beitrag einen Einwand gebracht; "
    "Anrufer uebergeht ihn oder antwortet mit Gegenmonolog. bezug = Einwand-ID.",
    EventKind.EARLY_CLOSING: "Anrufer draengt auf Abschluss oder Termin, bevor ein Problem "
    "der Persona besprochen wurde.",
    EventKind.EVASION: "Anrufer weicht einer direkten Frage der Persona aus.",
    EventKind.MAIL_AGREED: "Persona stimmt in ihrer Antwort zu, dass der Anrufer ihr eine Mail "
    "schickt.",
    EventKind.MEETING_AGREED: "Persona stimmt in ihrer Antwort einem konkreten Folgetermin zu "
    "(Tag und Uhrzeit oder fester Zeitraum).",
}

PROMPT = """Du protokollierst ein Vertriebs-Rollenspiel. Ein Anrufer (SDR) spricht mit der \
Persona {name} ({role}). Ordne den LETZTEN Wechsel in feste Ereignisse ein. Bewerte nur, was \
im Text steht -- nicht Tonfall, nicht Stimmung des Anrufers.

Probleme der Persona (ID: Titel -- Ausloeser):
{pains}

Einwaende der Persona (ID: Einwand):
{objections}

Erlaubte Ereignisse:
{events}

Vorheriger Beitrag der Persona: {previous}
Anrufer: {user}
Antwort der Persona: {reply}

Antworte NUR mit JSON:
{{"ereignisse": [{{"art": "<Ereignis>", "bezug": "<ID oder null>", "beleg": "<kurzes Zitat>"}}]}}
Leere Liste, wenn nichts zutrifft. Im Zweifel ein Ereignis weglassen."""


def build_prompt(persona: Persona, *, previous: str, user: str, reply: str) -> str:
    return PROMPT.format(
        name=persona.name,
        role=persona.role,
        pains="\n".join(f"- {p.id}: {p.title} -- {p.trigger}" for p in persona.pains),
        objections="\n".join(f"- {o.id}: {o.text}" for o in persona.objections),
        events="\n".join(f"- {k.value}: {v}" for k, v in LLM_EVENTS.items()),
        previous=previous or "(keiner)",
        user=user or "(nichts erkannt)",
        reply=reply or "(keine Antwort)",
    )


def parse_events(raw: str, persona: Persona) -> list[Event]:
    """Liest die LLM-Antwort; Unbekanntes wird verworfen statt geraten."""
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError:
        logger.warning(f"Protokollant: kein JSON: {raw[:120]!r}")
        return []
    items = data.get("ereignisse", []) if isinstance(data, dict) else []
    events: list[Event] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        try:
            kind = EventKind(str(item.get("art", "")))
        except ValueError:
            continue
        if kind not in LLM_EVENTS:
            continue
        ref = item.get("bezug")
        ref = str(ref) if ref not in (None, "", "null") else None
        if kind in PAIN_EVENTS and (ref is None or persona.pain(ref) is None):
            continue
        if kind in OBJECTION_EVENTS and ref is not None and persona.objection(ref) is None:
            ref = None
        events.append(Event(kind=kind, ref=ref, evidence=str(item.get("beleg", ""))[:200]))
    return events


def counted_events(persona: Persona, user: str, earlier_user: list[str]) -> list[Event]:
    """Deterministisch: Monolog (Wortzahl) und Wiederholung (Wortueberlappung)."""
    events: list[Event] = []
    words = _words(user)
    if len(words) >= persona.dynamics.monologue_words:
        events.append(Event(EventKind.MONOLOGUE, evidence=f"{len(words)} Woerter am Stueck"))
    current = set(words)
    if len(current) >= 6:
        for earlier in earlier_user:
            previous = set(_words(earlier))
            if previous and len(current & previous) / len(current | previous) >= 0.6:
                events.append(Event(EventKind.REPETITION, evidence=earlier[:120]))
                break
    return events


def _words(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


class Protocolist:
    """Fuehrt Zustand und Verlauf eines Gespraechs. Ein Objekt je Gespraech."""

    def __init__(self, persona: Persona, client: Any, model: str) -> None:
        self.persona = persona
        self.state = ConversationState.start(persona)
        self._client = client
        self._model = model
        self._earlier_user: list[str] = []
        self._previous_reply = ""

    async def observe(self, user: str, reply: str) -> list[Event]:
        """Ein Wechsel Anrufer -> Persona. Gibt die gewerteten Ereignisse zurueck."""
        events = counted_events(self.persona, user, self._earlier_user)
        if user.strip():
            events += await self._classify(user, reply)
        accepted = self.state.apply(events, persona_spoke=bool(reply.strip()))
        if user.strip():
            self._earlier_user.append(user)
        self._previous_reply = reply
        return accepted

    async def _classify(self, user: str, reply: str) -> list[Event]:
        prompt = build_prompt(self.persona, previous=self._previous_reply, user=user, reply=reply)
        try:
            r = await self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                response_format={"type": "json_object"},
            )
        except Exception as exc:  # noqa: BLE001 -- Ausfall darf das Gespraech nicht stoeren
            logger.warning(f"Protokollant: Aufruf fehlgeschlagen ({exc!s:.120})")
            return []
        return parse_events(r.choices[0].message.content or "", self.persona)
