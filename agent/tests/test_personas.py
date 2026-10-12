"""Persona-Format, Prompt-Baukasten, Gespraechszustand und Protokollant (ohne Netz)."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from pacemaker_agent.personas import DEFAULT_PERSONA, PERSONAS, get_persona
from pacemaker_agent.personas import kaltakquise_head_of_ops as p0
from pacemaker_agent.personas.markus_brandt import MARKUS_BRANDT
from pacemaker_agent.personas.model import EventKind, Gate, Milestone
from pacemaker_agent.personas.protocol import Protocolist, counted_events, parse_events
from pacemaker_agent.personas.state import ConversationState, Event

PAIN = "wochenend-ausfaelle"


# -- Registry / Phase-0-Persona ---------------------------------------------------------------


def test_default_is_frozen_phase0_prompt() -> None:
    entry = get_persona(None)
    assert entry.id == DEFAULT_PERSONA
    for opener in (False, True):
        assert entry.system_prompt(short_opener=opener) == p0.system_prompt(short_opener=opener)
    assert entry.hangup_tool == p0.HANGUP_TOOL
    assert not entry.has_logic


def test_env_selects_persona(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PACEMAKER_PERSONA", "markus-brandt")
    assert get_persona(None).id == "markus-brandt"
    with pytest.raises(ValueError):
        get_persona("gibt-es-nicht")


def test_all_personas_build_prompt_and_tool() -> None:
    for entry in PERSONAS.values():
        prompt = entry.system_prompt(short_opener=False)
        assert "KI-Trainingsfigur" in prompt  # KI-Transparenz gilt fuer jede Persona
        assert entry.hangup_tool["name"] == "auflegen"


# -- Prompt-Baukasten -------------------------------------------------------------------------


def test_prompt_contains_persona_data() -> None:
    prompt = PERSONAS["markus-brandt"].system_prompt(short_opener=False)
    for pain in MARKUS_BRANDT.pains:
        assert pain.trigger in prompt and pain.impact in prompt
        assert pain.hint not in prompt  # Andeutungen erst ab Phase 2
    assert MARKUS_BRANDT.product.name not in prompt  # Produkt nur fuer Briefing/Protokollant
    assert "[Regie" in prompt
    assert "Beginne jeden Redebeitrag" not in prompt
    assert "Beginne jeden Redebeitrag" in PERSONAS["markus-brandt"].system_prompt(short_opener=True)


# -- Datenformat ------------------------------------------------------------------------------


def test_invalid_persona_data_rejected() -> None:
    with pytest.raises(ValueError, match="Tor verweist"):
        replace(
            MARKUS_BRANDT,
            milestones=(
                Milestone(
                    id="X", label="x", event=EventKind.MAIL_AGREED, gate=Gate(requires=("FEHLT",))
                ),
            ),
        )
    with pytest.raises(ValueError, match="genau eine Bedingung"):
        replace(MARKUS_BRANDT, milestones=(Milestone(id="X", label="x"),))


# -- Gespraechszustand ------------------------------------------------------------------------


def _state() -> ConversationState:
    return ConversationState.start(MARKUS_BRANDT)


def test_pain_stages_one_step_per_turn() -> None:
    s = _state()
    # Bestaetigen ohne vorheriges Aufdecken zaehlt nicht; im selben Turn nur eine Stufe
    s.apply([Event(EventKind.PAIN_CONFIRMED, PAIN)])
    assert s.pain_stages[PAIN] == 0
    s.apply([Event(EventKind.PAIN_UNCOVERED, PAIN), Event(EventKind.PAIN_CONFIRMED, PAIN)])
    assert s.pain_stages[PAIN] == 2
    s.apply([Event(EventKind.PAIN_CONFIRMED, PAIN)])
    assert s.pain_stages[PAIN] == 3
    assert {"M2", "M3"} <= set(s.milestones)


def test_unknown_refs_ignored() -> None:
    s = _state()
    accepted = s.apply([Event(EventKind.PAIN_UNCOVERED, "erfunden")])
    assert accepted == [] and s.openness == MARKUS_BRANDT.dynamics.openness_start


def test_openness_capped_and_patience_floor() -> None:
    s = _state()
    for _ in range(10):
        s.apply([Event(EventKind.GOOD_OPEN_QUESTION), Event(EventKind.OBJECTION_ADDRESSED)])
    assert s.openness == MARKUS_BRANDT.dynamics.openness_cap
    for _ in range(10):
        s.apply([Event(EventKind.MONOLOGUE)])
    assert s.patience == 0 and s.wants_to_end_call
    assert "auflegen" in s.director_line()


def test_no_hangup_demand_in_first_three_turns() -> None:
    s = _state()
    s.apply([Event(EventKind.MONOLOGUE), Event(EventKind.REPETITION), Event(EventKind.EVASION)])
    assert s.patience == 0 and s.persona_turns == 1
    assert not s.wants_to_end_call


def test_agreement_gate() -> None:
    weak = _state()
    assert not weak.request_agreement(EventKind.MEETING_AGREED, "Donnerstag 10 Uhr")
    weak.apply([])
    assert "M6" not in weak.milestones  # abgelehnt: kein Meilenstein, keine Tor-Verletzung
    assert weak.request_agreement(EventKind.MAIL_AGREED) is False  # Offenheit 3 < 4

    strong = _state()
    strong.apply([Event(EventKind.GOOD_OPEN_QUESTION), Event(EventKind.PAIN_UNCOVERED, PAIN)])
    strong.apply([Event(EventKind.PAIN_CONFIRMED, PAIN)])
    assert strong.openness >= 6 and "M3" in strong.milestones
    assert strong.request_agreement(EventKind.MEETING_AGREED, "Dienstag 14 Uhr")
    assert "M6" not in strong.milestones  # wirkt erst mit dem Turn
    strong.apply([])
    hit = strong.milestones["M6"]
    assert hit.evidence == "Dienstag 14 Uhr" and not hit.gate_violated


def test_director_line_has_no_gate_hints() -> None:
    assert "moeglich" not in _state().director_line()  # Tor entscheidet das Werkzeug


def test_agreement_tool_in_prompt_and_entry() -> None:
    entry = PERSONAS["markus-brandt"]
    names = [t["name"] for t in entry.tools]
    assert names == ["auflegen", "zusagen"]
    assert entry.tools[1]["properties"]["art"]["enum"] == ["mail", "termin"]
    assert '"zusagen"' in entry.system_prompt(short_opener=False)
    assert [t["name"] for t in PERSONAS[DEFAULT_PERSONA].tools] == ["auflegen"]


def test_history_is_json() -> None:
    s = _state()
    s.apply([Event(EventKind.PAIN_UNCOVERED, PAIN, "Samstag faellt jemand aus")])
    json.dumps(s.history)
    assert s.history[-1]["events"][0]["bezug"] == PAIN


# -- Protokollant -----------------------------------------------------------------------------


def test_parse_events_drops_unknown() -> None:
    raw = json.dumps(
        {
            "ereignisse": [
                {"art": "schmerz_aufgedeckt", "bezug": PAIN, "beleg": "Samstag"},
                {"art": "schmerz_aufgedeckt", "bezug": "erfunden"},
                {"art": "gibt_es_nicht"},
                {"art": "monolog"},  # nur deterministisch, nie vom LLM
                {"art": "einwand_behandelt", "bezug": "erfunden"},
            ]
        }
    )
    events = parse_events(raw, MARKUS_BRANDT)
    assert [(e.kind, e.ref) for e in events] == [
        (EventKind.PAIN_UNCOVERED, PAIN),
        (EventKind.OBJECTION_ADDRESSED, None),
    ]
    assert parse_events("kein json", MARKUS_BRANDT) == []


def test_parse_events_code_rules() -> None:
    raw = json.dumps(
        {
            "ereignisse": [
                {"art": "schmerz_aufgedeckt", "bezug": PAIN},
                {"art": "einwand_behandelt", "bezug": "haben-wir-schon"},
            ]
        }
    )
    # Pitch ohne Frage, erster Wechsel: Aufdecken wird zu "verraten", Einwand faellt weg
    events = parse_events(raw, MARKUS_BRANDT, user="PlanWerk besetzt Ausfaelle.", previous="")
    assert [(e.kind, e.ref) for e in events] == [(EventKind.PAIN_LEAKED, PAIN)]


def test_leaked_pain_gives_no_credit() -> None:
    s = _state()
    s.apply([Event(EventKind.PAIN_LEAKED, PAIN)])
    assert s.pain_stages[PAIN] == 2 and s.leaked == {PAIN}
    assert "M2" not in s.milestones and s.openness == MARKUS_BRANDT.dynamics.openness_start
    s.apply([Event(EventKind.PAIN_CONFIRMED, PAIN)])
    assert "M3" not in s.milestones


def test_counted_events() -> None:
    long = " ".join(["Wort"] * 70)
    assert EventKind.MONOLOGUE in {e.kind for e in counted_events(MARKUS_BRANDT, long, [])}
    line = "Wir haben eine Loesung fuer Ihre Schichtplanung am Wochenende"
    assert EventKind.REPETITION in {e.kind for e in counted_events(MARKUS_BRANDT, line, [line])}
    assert counted_events(MARKUS_BRANDT, "Kurze Frage?", []) == []


class _FakeClient:
    def __init__(self, answers: list[dict]) -> None:
        self._answers = answers
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **_kwargs):
        content = json.dumps(self._answers.pop(0))
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def test_protocolist_end_to_end() -> None:
    client = _FakeClient(
        [
            {"ereignisse": [{"art": "schmerz_aufgedeckt", "bezug": PAIN, "beleg": "WhatsApp"}]},
            {"ereignisse": [{"art": "schmerz_bestaetigt", "bezug": PAIN, "beleg": "genau"}]},
        ]
    )
    proto = Protocolist(MARKUS_BRANDT, client, "test")
    asyncio.run(proto.observe("Was passiert am Samstag bei Ausfaellen?", "WhatsApp-Gruppe."))
    asyncio.run(proto.observe("Also kostet Sie das Ihre Samstage?", "Ja, genau das."))
    assert proto.state.pain_stages[PAIN] == 3
    assert "Wochenend-Ausfaelle (bestaetigt)" in proto.state.director_line()
