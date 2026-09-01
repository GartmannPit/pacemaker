"""Rollenbruch-Check auf Keyword-Ebene.

Der LLM-Judge (robustere Erkennung) folgt in Woche 2, Phase-0-Plan §3 Schritt 10.
"""

from __future__ import annotations

import re

BREAKOUT_PATTERNS = [
    r"\bals (KI|AI|sprachmodell|assistent)\b",
    r"\bich bin (eine|ein) (KI|AI|sprachmodell|assistent|chatbot)\b",
    r"\blanguage model\b",
    r"\bwie kann ich (dir|Ihnen) (heute )?helfen\b",
    r"\bich habe keinen zugriff auf\b",
    r"\bals dein.{0,20}assistent\b",
]


def find_breakouts(transcript: str) -> list[str]:
    hits: list[str] = []
    for pattern in BREAKOUT_PATTERNS:
        hits.extend(m.group(0) for m in re.finditer(pattern, transcript, flags=re.IGNORECASE))
    return hits


def test_in_character_line_is_clean() -> None:
    line = "Ich hab ehrlich gesagt keine drei Minuten. Worum geht's?"
    assert find_breakouts(line) == []


def test_detects_ki_breakout() -> None:
    line = "Als KI-Sprachmodell kann ich Ihnen gerne ein paar Verkaufstipps geben."
    assert find_breakouts(line)


def test_detects_assistant_greeting() -> None:
    assert find_breakouts("Hallo! Wie kann ich Ihnen heute helfen?")
