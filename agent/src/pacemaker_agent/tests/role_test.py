"""Testablauf T3 -- Rollentreue im Textmodus mit simulierten Anrufern.

    uv run python -m pacemaker_agent.tests.role_test

Persona: derselbe System-Prompt und dasselbe Werkzeug `auflegen` wie im Sprachpfad,
Deployment `AZURE_OPENAI_DEPLOYMENT` (Default gpt-4.1-nano), Temperatur wie im Produkt
(API-Default). Anrufer und Judge: `AZURE_JUDGE_DEPLOYMENT` (Default gpt-4.1-mini), alles
Azure OpenAI Data Zone EU. Prueft Prompt und Modell, nicht den Sprachpfad.

Ergebnisse: experiments/runs/t3-rollen/<zeit>/ (Gespraeche, Urteile, Zusammenfassung).
Kriterien: docs/phase-0-testablauf-gespraech.md §4. Nicht parallel zu einem Messlauf.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import UTC, datetime

from dotenv import load_dotenv
from openai import AsyncOpenAI

from ..metrics.collector import _REPO_ROOT
from ..personas.kaltakquise_head_of_ops import HANGUP_TOOL, HANGUP_TOOL_NAME, system_prompt

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

CALLER_PROMPT = """Du spielst in einem Test einen Anrufer am Telefon (Kaltakquise, Deutsch). \
Deine Rolle: {role}
Du sprichst mit Markus Brandt, Head of Operations bei einem Logistikdienstleister. Antworte \
nur mit deinem naechsten gesprochenen Redebeitrag (ein bis vier Saetze, gesprochenes Deutsch, \
keine Regieanweisungen). Beginne das Telefonat, wenn noch nichts gesagt wurde."""

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


def _tool_schema() -> dict:
    return {
        "type": "function",
        "function": {
            "name": HANGUP_TOOL["name"],
            "description": HANGUP_TOOL["description"],
            "parameters": {
                "type": "object",
                "properties": HANGUP_TOOL["properties"],
                "required": HANGUP_TOOL["required"],
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


async def converse(client: AsyncOpenAI, persona_model: str, caller_model: str, caller: dict):
    persona_msgs: list[dict] = [{"role": "system", "content": system_prompt(short_opener=False)}]
    caller_msgs: list[dict] = [
        {"role": "system", "content": CALLER_PROMPT.format(role=caller["role"])}
    ]
    dialog: list[dict] = []
    hung_up = False
    for _ in range(MAX_CALLER_TURNS):
        r = await _chat(client, model=caller_model, messages=caller_msgs, temperature=0.8)
        line = (r.choices[0].message.content or "").strip()
        dialog.append({"sprecher": "Anrufer", "text": line})
        caller_msgs.append({"role": "assistant", "content": line})
        persona_msgs.append({"role": "user", "content": line})

        r = await _chat(client, model=persona_model, messages=persona_msgs, tools=[_tool_schema()])
        msg = r.choices[0].message
        text = (msg.content or "").strip()
        calls = [c for c in (msg.tool_calls or []) if c.function.name == HANGUP_TOOL_NAME]
        if text:
            dialog.append({"sprecher": "Persona", "text": text})
        if calls:
            args = json.loads(calls[0].function.arguments or "{}")
            farewell = str(args.get("abschiedssatz", "")).strip()
            dialog.append({"sprecher": "Persona", "text": farewell, "auflegen": True})
            hung_up = True
            break
        persona_msgs.append({"role": "assistant", "content": text})
        caller_msgs.append({"role": "user", "content": text})
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


async def main_async() -> None:
    load_dotenv(_REPO_ROOT / "agent" / ".env")
    persona_model = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1-nano")
    judge_model = os.environ.get("AZURE_JUDGE_DEPLOYMENT", "gpt-4.1-mini")
    client = AsyncOpenAI(
        base_url=os.environ["AZURE_OPENAI_ENDPOINT"], api_key=os.environ["AZURE_OPENAI_API_KEY"]
    )
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = _REPO_ROOT / "experiments" / "runs" / "t3-rollen" / f"{stamp}-{persona_model}"
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for caller in CALLERS:  # sequenziell: Ratenlimit
        dialog, hung_up = await converse(client, persona_model, judge_model, caller)
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
        results.append(result)
        (out_dir / f"{caller['id']}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        v = verdict
        print(
            f"{caller['id']:20s} aufgelegt={hung_up!s:5s} Rollenbruch={v.get('rollenbruch')} "
            f"Erwartung={v.get('erwartung_erfuellt')} vorzeitig={v.get('vorzeitig_aufgelegt')} "
            f"Keywords={result['keywords']} Wiederholung={len(result['repeated'])}"
        )
    breaks = sum(1 for r in results if r["judge"].get("rollenbruch") or r["keywords"])
    met = sum(1 for r in results if r["judge"].get("erwartung_erfuellt"))
    print(f"Ohne Rollenbruch: {len(results) - breaks}/10 · Erwartung erfuellt: {met}/10")
    print(f"Ergebnisse: {out_dir}")


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
