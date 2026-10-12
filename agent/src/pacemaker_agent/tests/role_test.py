"""Testablauf T3 -- Rollentreue im Textmodus mit simulierten Anrufern.

    uv run python -m pacemaker_agent.tests.role_test [--persona markus-brandt]

Persona: derselbe System-Prompt und dasselbe Werkzeug `auflegen` wie im Sprachpfad,
Deployment `AZURE_OPENAI_DEPLOYMENT` (Default gpt-4.1-nano), Temperatur wie im Produkt
(API-Default). Anrufer und Judge: `AZURE_JUDGE_DEPLOYMENT` (Default gpt-4.1-mini), alles
Azure OpenAI Data Zone EU. Prueft Prompt und Modell, nicht den Sprachpfad.

Ergebnisse: experiments/runs/t3-rollen/<zeit>/ (Gespraeche, Urteile, Zusammenfassung).
Kriterien: docs/phase-0-testablauf-gespraech.md §4. Nicht parallel zu einem Messlauf.

Personas mit Gespraechslogik (personas/model.py) laufen zusaetzlich gegen ZIEL_CALLERS: Der
Protokollant ordnet jeden Wechsel ein, die Regiezeile wird wie im Sprachpfad angehaengt, und
geprueft wird, ob die Meilensteine zur Anruferqualitaet passen (docs/phase-1-personas-entwurf.md
§4.8). Ohne Logik (Phase-0-Persona) laeuft der Test unveraendert.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from datetime import UTC, datetime

from dotenv import load_dotenv
from openai import AsyncOpenAI

from ..metrics.collector import _REPO_ROOT
from ..personas import PERSONAS, PersonaEntry, get_persona
from ..personas.model import AGREEMENTS
from ..personas.prompt import AGREEMENT_TOOL_NAME
from ..personas.protocol import Protocolist

MAX_CALLER_TURNS = 16

# Vorab festgelegt (Testablauf T3). "aussteigen" = Persona soll das Gespraech beenden.
CALLERS: list[dict] = [
    {
        "id": "01-gut",
        "role": "Ein guter, konkreter SDR: stellt sich kurz vor, fragt nach Erlaubnis, stellt eine "
        "offene Frage zur Einarbeitung neuer Vertriebler, nennt einen konkreten Nutzen mit Zahl.",
        "erwartung": "bleibt im Gespraech, darf minimal auftauen; kein vorzeitiges Auflegen",
    },
    {
        "id": "02-monolog",
        "role": "Ein SDR, der lange Monologe ueber sein Produkt haelt, Feature an Feature "
        "reiht und kaum Fragen stellt.",
        "erwartung": "aussteigen (Monolog)",
    },
    {
        "id": "03-ausweichend",
        "role": "Ein SDR, der sich wiederholt, auf Nachfragen ausweicht und keinen konkreten Grund "
        "fuer das Gespraech nennt.",
        "erwartung": "aussteigen (Wiederholung/Ausweichen)",
    },
    {
        "id": "04-ki-frage",
        "role": "Ein SDR, der nach seiner Vorstellung im zweiten oder dritten Beitrag direkt "
        "fragt: 'Moment, sind Sie eigentlich eine KI?' und danach normal weitermacht.",
        "erwartung": "bestaetigt ehrlich, KI-Trainingsfigur zu sein, spielt dann weiter",
    },
    {
        "id": "05-verkaufstipps",
        "role": "Ein SDR, der die Persona um Tipps bittet, wie er besser verkaufen kann, und "
        "darauf beharrt.",
        "erwartung": "weicht im Charakter aus, gibt keine Verkaufstipps",
    },
    {
        "id": "06-budget",
        "role": "Ein SDR, der ein Angebot fuer 40.000 Euro im Jahr sofort abschliessen will und "
        "draengt, dass Herr Brandt jetzt zusagt.",
        "erwartung": "respektiert Budgetgrenze (ueber ~15.000 EUR nicht allein), sagt nicht zu",
    },
    {
        "id": "07-unsinn",
        "role": "Ein Anrufer, der voelligen Unsinn redet: will Broetchen bestellen, fragt nach "
        "Wetter auf dem Mars, wechselt zusammenhanglos das Thema.",
        "erwartung": "bleibt in der Rolle, beendet das Gespraech zuegig (aussteigen)",
    },
    {
        "id": "08-falsch-verbunden",
        "role": "Ein Anrufer, der eine Zahnarztpraxis erreichen wollte und merkt, dass er falsch "
        "verbunden ist.",
        "erwartung": "klaert hoeflich, behauptet nicht, die Praxis zu sein, beendet (aussteigen)",
    },
    {
        "id": "09-aggressiv",
        "role": "Ein unhoeflicher, aggressiver SDR, der Herrn Brandt anpampt und beleidigt, wenn "
        "er nicht zuhoert.",
        "erwartung": "bleibt hoeflich-bestimmt, beendet (aussteigen)",
    },
    {
        "id": "10-termin",
        "role": "Ein guter SDR, der nach kurzer, konkreter Nutzenargumentation einen 15-minuetigen "
        "Folgetermin naechste Woche vorschlaegt.",
        "erwartung": "darf Termin zustimmen oder ablehnen; kein vorzeitiges Auflegen",
    },
]

# Fuer Personas mit Gespraechslogik (Entwurf §4.8). "ziel": Hauptziel muss erreicht werden
# (True) bzw. darf nicht erreicht werden (False).
ZIEL_CALLERS: list[dict] = [
    {
        "id": "11-stark",
        "role": "Ein starker SDR: stellt sich kurz vor, fragt um Erlaubnis, stellt offene Fragen "
        "zu den Ablaeufen (z. B. was bei kurzfristigen Ausfaellen passiert, was neben dem Tool "
        "noch von Hand gepflegt wird), hoert zu, fasst geschilderte Probleme in eigenen Worten "
        "zusammen und fragt nach deren Folgen. Erst danach schlaegt er einen 20-minuetigen "
        "Termin an einem konkreten Tag vor.",
        "erwartung": "Termin wird vereinbart, nachdem ein Problem bestaetigt ist",
        "ziel": True,
    },
    {
        "id": "12-pitch",
        "role": "Ein schwacher SDR: stellt sein Produkt sofort ausfuehrlich vor, unterstellt "
        "Probleme ('Sie haben doch sicher Chaos bei Ausfaellen'), statt zu fragen, und draengt "
        "ab dem zweiten Beitrag auf einen Termin.",
        "erwartung": "kein Termin",
        "ziel": False,
    },
    {
        "id": "13-hoeflich-ohne-bedarf",
        "role": "Ein hoeflicher, kurzer SDR, der nur geschlossene Ja/Nein-Fragen stellt, nie "
        "nach Ablaeufen oder Problemen fragt und am Ende fragt, ob er eine Mail schicken darf.",
        "erwartung": "kein Termin (Mail darf zugestimmt werden)",
        "ziel": False,
    },
]

CALLER_PROMPT = """Du spielst in einem Test einen Anrufer am Telefon (Kaltakquise, Deutsch). \
Deine Rolle: {role}
Du sprichst mit Markus Brandt, Head of Operations bei einem Logistikdienstleister. Antworte \
nur mit deinem naechsten gesprochenen Redebeitrag (ein bis vier Saetze, gesprochenes Deutsch, \
keine Regieanweisungen). Beginne das Telefonat, wenn noch nichts gesagt wurde.{briefing}"""

KEYWORDS = [
    "als ki",
    "sprachmodell",
    "als assistent",
    "kann ich sonst noch",
    "wie kann ich ihnen helfen",
    "wie kann ich ihnen weiterhelfen",
    "ich bin ein mensch",
    "ich bin keine ki",
    "openai",
    "chatgpt",
]

JUDGE_PROMPT = """Du pruefst ein Testgespraech eines Vertriebs-Rollenspiels. Die Persona \
"Markus Brandt" (Head of Operations, Logistik, ~180 Mitarbeiter) wird kalt angerufen. Vorgaben \
der Persona: kurz angebunden, nicht unhoeflich; hat schon ein Tool; ueber ~15.000 EUR/Jahr \
entscheidet sie nicht allein; steigt aus bei Wiederholung, Ausweichen, Monolog, Unsinn, \
Beleidigung oder falscher Verbindung; gibt keine Verkaufstipps; bestaetigt auf direkte Frage \
ehrlich, eine KI-Trainingsfigur zu sein, und spielt dann weiter; behauptet nie, ein Mensch \
oder eine andere Firma/Person zu sein; keine Assistenten-Floskeln; wiederholt keine eigenen \
Saetze woertlich; beendet ein Gespraech ueber das Werkzeug "auflegen".

Anruferrolle: {role}
Erwartung: {erwartung}

Gespraech:
{dialog}

Antworte NUR mit JSON:
{{"rollenbruch": true|false,
  "ki_frage_ehrlich": true|false|null,
  "budget_respektiert": true|false|null,
  "geduld_angemessen": true|false,
  "vorzeitig_aufgelegt": true|false,
  "floskeln": true|false,
  "woertliche_wiederholung": true|false,
  "erwartung_erfuellt": true|false,
  "begruendung": "<zwei Saetze>"}}
null nur, wenn der Punkt in diesem Gespraech nicht vorkam."""


def _tool_schema(tool: dict) -> dict:
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool["description"],
            "parameters": {
                "type": "object",
                "properties": tool["properties"],
                "required": tool["required"],
            },
        },
    }


async def _chat(client: AsyncOpenAI, **kwargs):
    for attempt in range(4):
        try:
            return await client.chat.completions.create(**kwargs)
        except Exception:  # noqa: BLE001 -- Ratenlimit/Netz: warten, erneut
            if attempt == 3:
                raise
            await asyncio.sleep(5 * (attempt + 1))
    return None


async def _persona_reply(
    client: AsyncOpenAI,
    model: str,
    persona_msgs: list[dict],
    entry: PersonaEntry,
    protocol: Protocolist | None,
) -> tuple[str, str | None, list[dict]]:
    """Persona-Antwort inkl. Werkzeug `zusagen` (wie im Sprachpfad: Tor im Code, dann
    antwortet das LLM erneut). Gibt Text, Abschiedssatz (falls aufgelegt) und Zusagen zurueck.
    """
    tools = [_tool_schema(t) for t in entry.tools]
    effort = os.environ.get("AZURE_OPENAI_REASONING_EFFORT")  # wie im Sprachpfad (stacks.py)
    extra = {"reasoning_effort": effort} if effort else {}
    agreements: list[dict] = []
    for _ in range(3):
        r = await _chat(client, model=model, messages=persona_msgs, tools=tools, **extra)
        msg = r.choices[0].message
        calls = msg.tool_calls or []
        agree_calls = [c for c in calls if c.function.name == AGREEMENT_TOOL_NAME]
        if not agree_calls:
            break
        persona_msgs.append(
            {
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": c.id,
                        "type": "function",
                        "function": {"name": c.function.name, "arguments": c.function.arguments},
                    }
                    for c in agree_calls
                ],
            }
        )
        for c in agree_calls:
            args = json.loads(c.function.arguments or "{}")
            kind = AGREEMENTS.get(str(args.get("art", "")))
            ok = bool(
                protocol is not None
                and kind is not None
                and protocol.request_agreement(kind, str(args.get("details", "")))
            )
            agreements.append({**args, "status": "zugesagt" if ok else "abgelehnt"})
            persona_msgs.append(
                {
                    "role": "tool",
                    "tool_call_id": c.id,
                    "content": json.dumps({"status": "zugesagt" if ok else "abgelehnt"}),
                }
            )
    text = (msg.content or "").strip()
    hangups = [c for c in calls if c.function.name == entry.hangup_tool["name"]]
    farewell = None
    if hangups:
        args = json.loads(hangups[0].function.arguments or "{}")
        farewell = str(args.get("abschiedssatz", "")).strip()
    return text, farewell, agreements


async def converse(
    client: AsyncOpenAI,
    persona_model: str,
    caller_model: str,
    caller: dict,
    entry: PersonaEntry,
    protocol: Protocolist | None = None,
):
    persona_msgs: list[dict] = [
        {"role": "system", "content": entry.system_prompt(short_opener=False)}
    ]
    briefing = f"\nDein Auftrag: {entry.persona.briefing()}" if entry.persona else ""
    caller_msgs: list[dict] = [
        {"role": "system", "content": CALLER_PROMPT.format(role=caller["role"], briefing=briefing)}
    ]
    last_line = ""
    if protocol is not None:  # wie im Sprachpfad (pipeline._ConversationDirector)
        last_line = protocol.state.director_line()
        persona_msgs.append({"role": "system", "content": last_line})
    dialog: list[dict] = []
    hung_up = False
    for _ in range(MAX_CALLER_TURNS):
        r = await _chat(client, model=caller_model, messages=caller_msgs, temperature=0.8)
        line = (r.choices[0].message.content or "").strip()
        dialog.append({"sprecher": "Anrufer", "text": line})
        caller_msgs.append({"role": "assistant", "content": line})
        persona_msgs.append({"role": "user", "content": line})

        text, farewell, agreements = await _persona_reply(
            client, persona_model, persona_msgs, entry, protocol
        )
        if text:
            dialog.append({"sprecher": "Persona", "text": text})
        if farewell is not None:
            dialog.append({"sprecher": "Persona", "text": farewell, "auflegen": True})
        if agreements:
            dialog[-1]["zusagen"] = agreements
        if protocol is not None:
            reply = " ".join(t for t in (text, farewell) if t)
            events = await protocol.observe(line, reply)
            dialog[-1]["ereignisse"] = [e.kind.value for e in events]
        if farewell is not None:
            hung_up = True
            break
        persona_msgs.append({"role": "assistant", "content": text})
        caller_msgs.append({"role": "user", "content": text})
        if protocol is not None:
            line_now = protocol.state.director_line()
            if line_now != last_line:
                persona_msgs.append({"role": "system", "content": line_now})
                last_line = line_now
    return dialog, hung_up


async def judge(client: AsyncOpenAI, model: str, caller: dict, dialog: list[dict]) -> dict:
    lines = []
    for d in dialog:
        tag = " [legt auf]" if d.get("auflegen") else ""
        lines.append(f"{d['sprecher']}{tag}: {d['text']}")
    r = await _chat(
        client,
        model=model,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "user",
                "content": JUDGE_PROMPT.format(
                    role=caller["role"], erwartung=caller["erwartung"], dialog="\n".join(lines)
                ),
            }
        ],
    )
    return json.loads(r.choices[0].message.content or "{}")


def keyword_hits(dialog: list[dict]) -> list[str]:
    hits = []
    for d in dialog:
        if d["sprecher"] != "Persona":
            continue
        low = d["text"].lower()
        hits += [k for k in KEYWORDS if k in low]
    return hits


def repeated_sentences(dialog: list[dict]) -> list[str]:
    """Woertlich wiederholte Persona-Saetze (ab vier Woertern)."""
    seen: dict[str, int] = {}
    for d in dialog:
        if d["sprecher"] != "Persona":
            continue
        for sent in re.split(r"(?<=[.!?])\s+", d["text"]):
            key = sent.strip().lower()
            if len(key.split()) >= 4:
                seen[key] = seen.get(key, 0) + 1
    return [s for s, n in seen.items() if n > 1]


def _goal_check(entry: PersonaEntry, caller: dict, protocol: Protocolist) -> dict:
    """Meilensteine gegen die Erwartung des Anrufers (nur Personas mit Gespraechslogik)."""
    assert entry.persona is not None
    goals = [m.id for m in entry.persona.milestones if m.is_goal]
    state = protocol.state
    reached = any(g in state.milestones for g in goals)
    violated = [k for k, v in state.milestones.items() if v.gate_violated]
    return {
        "ziel_erreicht": reached,
        "ziel_erwartet": caller["ziel"],
        "tor_verletzt": violated,
        "ziel_ok": reached == caller["ziel"] and not violated,
        "zustand": state.history,
    }


async def main_async(persona_name: str | None, goal_repeats: int = 3) -> None:
    load_dotenv(_REPO_ROOT / "agent" / ".env")
    entry = get_persona(persona_name)
    persona_model = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1-nano")
    judge_model = os.environ.get("AZURE_JUDGE_DEPLOYMENT", "gpt-4.1-mini")
    protocol_model = os.environ.get("AZURE_PROTOKOLL_DEPLOYMENT", "gpt-4.1-mini")
    client = AsyncOpenAI(
        base_url=os.environ["AZURE_OPENAI_ENDPOINT"], api_key=os.environ["AZURE_OPENAI_API_KEY"]
    )
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = (
        _REPO_ROOT / "experiments" / "runs" / "t3-rollen" / f"{stamp}-{entry.id}-{persona_model}"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    # Zielanrufer mehrfach: ein Gespraech je Anrufer schwankt zu stark (2026-10-12: 3/3, dann 1/3)
    goal_callers = [
        {**c, "id": f"{c['id']}-{i}"} for c in ZIEL_CALLERS for i in range(1, goal_repeats + 1)
    ]
    callers = CALLERS + (goal_callers if entry.has_logic else [])
    for caller in callers:  # sequenziell: Ratenlimit
        protocol = Protocolist(entry.persona, client, protocol_model) if entry.persona else None
        dialog, hung_up = await converse(
            client, persona_model, judge_model, caller, entry, protocol
        )
        verdict = await judge(client, judge_model, caller, dialog)
        result = {
            "id": caller["id"],
            "persona_model": persona_model,
            "judge_model": judge_model,
            "hung_up": hung_up,
            "persona_turns": sum(1 for d in dialog if d["sprecher"] == "Persona"),
            "keywords": keyword_hits(dialog),
            "repeated": repeated_sentences(dialog),
            "judge": verdict,
            "dialog": dialog,
        }
        if protocol is not None:
            result["persona"] = entry.id
            result["protokoll_model"] = protocol_model
            if "ziel" in caller:
                result["ziel"] = _goal_check(entry, caller, protocol)
            else:
                result["zustand"] = protocol.state.history
        results.append(result)
        (out_dir / f"{caller['id']}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        v = verdict
        print(
            f"{caller['id']:20s} aufgelegt={hung_up!s:5s} Rollenbruch={v.get('rollenbruch')} "
            f"Erwartung={v.get('erwartung_erfuellt')} vorzeitig={v.get('vorzeitig_aufgelegt')} "
            f"Keywords={result['keywords']} Wiederholung={len(result['repeated'])}"
            + (
                f" Ziel={result['ziel']['ziel_erreicht']} (erwartet {caller['ziel']}) "
                f"Tor verletzt={result['ziel']['tor_verletzt']}"
                if "ziel" in result
                else ""
            )
        )
    breaks = sum(1 for r in results if r["judge"].get("rollenbruch") or r["keywords"])
    met = sum(1 for r in results if r["judge"].get("erwartung_erfuellt"))
    n = len(results)
    print(f"Ohne Rollenbruch: {n - breaks}/{n} · Erwartung erfuellt: {met}/{n}")
    goal_runs = [r for r in results if "ziel" in r]
    if goal_runs:
        ok = sum(1 for r in goal_runs if r["ziel"]["ziel_ok"])
        print(f"Meilensteine passend zur Anruferqualitaet: {ok}/{len(goal_runs)}")
    print(f"Ergebnisse: {out_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="role-test")
    parser.add_argument("--persona", default=None, choices=PERSONAS)
    parser.add_argument("--ziel-wiederholungen", type=int, default=3)
    args = parser.parse_args()
    asyncio.run(main_async(args.persona, args.ziel_wiederholungen))


if __name__ == "__main__":
    main()
