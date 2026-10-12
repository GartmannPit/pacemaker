"""Persona-Auswahl per Name (`--persona`, `PACEMAKER_PERSONA`).

Default bleibt die eingefrorene Phase-0-Persona (`markus-brandt-p0`, Prompt-Durchgang 2), bis
alle Phase-0-Laeufe ausgewertet sind (Testablauf §0). Personas im Datenformat (`model.py`)
bringen Gespraechslogik mit (Zustand, Regie, Protokollant); die Phase-0-Persona nicht.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass

from . import kaltakquise_head_of_ops as _p0
from .markus_brandt import MARKUS_BRANDT
from .model import Persona
from .prompt import HANGUP_TOOL_NAME, hangup_tool, system_prompt

DEFAULT_PERSONA = "markus-brandt-p0"


@dataclass(frozen=True)
class PersonaEntry:
    id: str
    build_prompt: Callable[[bool], str]  # short_opener -> Systemprompt
    hangup_tool: dict
    persona: Persona | None = None  # None: ohne Gespraechslogik (Phase 0)

    def system_prompt(self, *, short_opener: bool) -> str:
        return self.build_prompt(short_opener)

    @property
    def has_logic(self) -> bool:
        return self.persona is not None


def _entry(persona: Persona) -> PersonaEntry:
    return PersonaEntry(
        id=persona.id,
        build_prompt=lambda short_opener: system_prompt(persona, short_opener=short_opener),
        hangup_tool=hangup_tool(persona),
        persona=persona,
    )


PERSONAS: dict[str, PersonaEntry] = {
    DEFAULT_PERSONA: PersonaEntry(
        id=DEFAULT_PERSONA,
        build_prompt=lambda short_opener: _p0.system_prompt(short_opener=short_opener),
        hangup_tool=_p0.HANGUP_TOOL,
    ),
    MARKUS_BRANDT.id: _entry(MARKUS_BRANDT),
}

assert _p0.HANGUP_TOOL_NAME == HANGUP_TOOL_NAME


def get_persona(name: str | None = None) -> PersonaEntry:
    key = name or os.environ.get("PACEMAKER_PERSONA") or DEFAULT_PERSONA
    if key not in PERSONAS:
        raise ValueError(f"Unbekannte Persona '{key}'. Verfuegbar: {', '.join(PERSONAS)}")
    return PERSONAS[key]
