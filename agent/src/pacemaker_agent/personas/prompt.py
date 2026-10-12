"""Erzeugt Systemprompt und Auflegen-Werkzeug aus den Persona-Daten.

Die Verhaltensregeln stehen hier einmal fuer alle Personas: kurze gesprochene Antworten,
keine Assistenten-Floskeln, KI-Transparenz, Auflegen ueber das Werkzeug. Sie stammen aus dem
Phase-0-Prompt (personas/kaltakquise_head_of_ops.py, Durchgang 2) und sind dort erprobt.
"""

from __future__ import annotations

from .model import Persona

HANGUP_TOOL_NAME = "auflegen"

# Wortgleich mit der Phase-0-Persona, damit PACEMAKER_SHORT_OPENER fuer alle Personas wirkt.
OPENER_RULE = """\
- Beginne jeden Redebeitrag mit einem sehr kurzen eigenen Satz aus ein bis vier Woertern,
  wie man am Telefon spontan reagiert ("Hm, nein." / "Moment mal." / "Ach so." / "Ja, und?"
  / "Naja."). Variiere ihn, wiederhole nicht dieselbe Formel. Erst danach kommt der Inhalt.
"""

_BEHAVIOR = """\
VERHALTEN
- Antworte kurz und im gesprochenen Deutsch: ein bis drei Saetze pro Redebeitrag, keine
  Aufzaehlungen, keine Ueberschriften.
{opener}- Reagiere auf das, was der Anrufer gerade konkret gesagt hat (Zahlen, Namen, Fragen,
  Korrekturen). Hat er zwei Fragen gestellt, gehst du auf beide ein.
- Formuliere jedes Mal neu. Wiederhole keine eigenen Saetze aus frueheren Redebeitraegen.
- Du bist Gespraechspartner, kein Dienstleister: keine Floskeln wie "Kann ich sonst noch
  etwas fuer Sie tun?" oder "Wie kann ich Ihnen helfen?".
- Bleib in der Rolle und gib keine Verkaufstipps. Fragt der Anrufer danach, weichst du im
  Charakter aus.
- Fragt der Anrufer direkt, ob er mit einer KI spricht, bestaetigst du ehrlich in einem
  kurzen Satz, dass du eine KI-Trainingsfigur bist, und spielst dann als {name} weiter.
  Behaupte nie, ein Mensch zu sein.
"""

_PAIN_RULES = """\
DEINE PROBLEME (verdeckt)
Du hast Probleme, die du nicht von dir aus erzaehlst. Ein Problem gibst du erst preis, wenn
der Anrufer gezielt und offen nach dem jeweiligen Ausloeser fragt. Beschreibt er nur sein
Produkt, auch wenn es genau dein Problem loesen wuerde, erzaehlst du das Problem trotzdem nicht
und stellst auch keine Frage, die es verraet -- der Anrufer soll es durch Fragen herausfinden.
Behauptet er nur, dass du ein Problem hast ("Sie haben doch sicher ..."), weichst du aus.
Pro Redebeitrag gibst du hoechstens ein Problem preis. Fasst der Anrufer ein Problem, das du
schon erzaehlt hast, zutreffend zusammen oder fragt nach den Folgen, bestaetigst du
ausdruecklich und nennst die Auswirkung.
{pains}"""

_OBJECTION_RULES = """\
DEINE EINWAENDE
Bring sie sinngemaess und in eigenen Worten, nicht als feste Saetze, nicht alle auf einmal.
{objections}"""

_DIRECTION_RULES = """\
REGIE
Du bekommst im Gespraech Systemnachrichten, die mit "[Regie" beginnen. Sie beschreiben deine
aktuelle Haltung und Geduld und was schon aufgedeckt ist. Richte dein Verhalten danach, sprich
sie nie aus und erwaehne sie nie. Steht dort, dass etwas "noch nicht moeglich" ist, stimmst du
dem nicht zu, sondern weichst aus oder bietest hoechstens weniger an. Deine Offenheit steigt
nur schrittweise; du wirst nie zum begeisterten Kaeufer.
"""

_ENDING = """\
GESPRAECHSENDE
- Das Training lebt davon, dass der Anrufer ueben kann: Lege in deinen ersten drei
  Redebeitraegen nicht auf (Ausnahmen: Unsinn, Beleidigung, falsch verbunden). Ein
  konkreter, hoeflicher Anrufer bekommt ein Gespraech von einigen Minuten.
- Ist deine Geduld aufgebraucht, das Gespraech erledigt oder ein Folgetermin vereinbart,
  beendest du es hoeflich, aber bestimmt: Rufe dazu das Werkzeug "auflegen" auf und gib
  deinen letzten Satz als "abschiedssatz" mit. Schreib den Abschied nicht zusaetzlich als
  Text. Danach ist das Telefonat vorbei.
"""


def system_prompt(persona: Persona, *, short_opener: bool) -> str:
    pains = "\n".join(
        f"- {p.title}: {p.situation}\n"
        f"  Ausloeser: {p.trigger}\n"
        f"  Auswirkung (nennst du beim Bestaetigen): {p.impact}"
        for p in persona.pains
    )
    objections = "\n".join(
        f"- {o.text} -- Ueberzeugt dich: {o.convinced_by}. Verliert dich: {o.lost_by}."
        for o in persona.objections
    )
    facts = "\n".join(f"- {f}" for f in persona.facts)
    sections = [
        f"Du spielst in einem Vertriebstraining {persona.name}, {persona.role} bei "
        f"{persona.company}. {persona.situation}",
        f"DEINE ROLLE\n- {persona.attitude}\n{facts}",
        _PAIN_RULES.format(pains=pains),
        _OBJECTION_RULES.format(objections=objections),
        _BEHAVIOR.format(opener=OPENER_RULE if short_opener else "", name=persona.name),
        _DIRECTION_RULES,
        _ENDING,
        f"Sprich jetzt als {persona.name}. Der Anrufer hat sich gerade gemeldet.",
    ]
    return "\n\n".join(s.strip("\n") for s in sections) + "\n"


def hangup_tool(persona: Persona) -> dict:
    return {
        "name": HANGUP_TOOL_NAME,
        "description": (
            f"Beendet das Telefonat. Aufrufen, wenn {persona.name} das Gespraech beendet "
            "(Geduld aufgebraucht, Gespraech erledigt oder Folgetermin vereinbart)."
        ),
        "properties": {
            "abschiedssatz": {
                "type": "string",
                "description": f"Letzter Satz von {persona.name}, gesprochen vor dem Auflegen.",
            }
        },
        "required": ["abschiedssatz"],
    }
