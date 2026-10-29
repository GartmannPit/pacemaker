"""Öffentliches Briefing vor dem Gespräch (Plan Schritt 2 §10).

Enthält ausschließlich Angaben, die der Trainee kennen darf. Die Werte der Charakterkarte
(Budget, Entscheider, Zeitpunkt, Schmerzpunkte) gehören nicht hierher und erreichen den
Browser frühestens mit dem Abgleich nach dem Gespräch.
"""

from __future__ import annotations

from typing import Any

# Qualifizierungs-Framework; in Phase 1 fest, später je Team wählbar.
BANT: dict[str, Any] = {
    "id": "bant",
    "name": "BANT",
    "quelle": "vom Team vorgegeben",
    "kriterien": [
        {"key": "B", "label": "Budget", "leitfrage": "Gibt es Mittel, und bis zu welcher Höhe?"},
        {
            "key": "A",
            "label": "Entscheider",
            "leitfrage": "Wer entscheidet, wer muss mit ins Boot?",
        },
        {"key": "N", "label": "Bedarf", "leitfrage": "Welches Problem ist wirklich drängend?"},
        {"key": "T", "label": "Zeitpunkt", "leitfrage": "Bis wann muss sich etwas ändern?"},
    ],
}

# Öffentliche Seite der Persona Markus Brandt; Produkt aus Branch persona-extension.
BRANDT: dict[str, Any] = {
    "persona": {
        "name": "Markus Brandt",
        "rolle": "Head of Operations",
        "unternehmen": "Logistikdienstleister, rund 180 Mitarbeitende",
        "standorte": "Duisburg und Hamm, Schichtbetrieb",
        "hinweis": "Brandt ist beschäftigt und hat Sie nicht erwartet.",
    },
    "produkt": {
        "name": "PlanWerk",
        "nutzen": "Software für Schicht- und Einsatzplanung",
        "preis": "9.000–14.000 € pro Jahr",
    },
    "ziel": "Framework klären und einen Termin vereinbaren",
    "punkte": [
        "Gute Fragen und behandelte Einwände: kleine Punkte",
        "Jedes geklärte Framework-Feld: viele Punkte",
        "Termin vereinbart: volle Punktzahl",
    ],
}


# Auswahl auf der Startseite (Schritt 2b); weitere Frameworks werden verfügbar, sobald die
# Charakterkarte Werte dafür hat (Schritt 3).
FRAMEWORKS: list[dict[str, Any]] = [
    {"id": "bant", "name": "BANT", "verfuegbar": True},
    {"id": "meddic", "name": "MEDDIC", "verfuegbar": False},
    {"id": "spiced", "name": "SPICED", "verfuegbar": False},
]
VERFUEGBARE_FRAMEWORKS = frozenset(f["id"] for f in FRAMEWORKS if f["verfuegbar"])

# Wortlaut vorläufig (Vorschlag Claude, Freigabe Pit offen; Plan 2b §8).
AUFGABEN = [
    "Vereinbaren Sie einen Termin für ein Folgegespräch.",
    "Klären Sie die Kriterien des Frameworks.",
]


def briefing(max_duration_s: float) -> dict[str, Any]:
    """Briefing für das nächste Gespräch; nur öffentliche Angaben."""
    return {
        **BRANDT,
        "framework": BANT,
        "frameworks": FRAMEWORKS,
        "aufgaben": AUFGABEN,
        "max_dauer_s": int(max_duration_s),
    }
