"""LLM-Judge fuer Testablauf T1: F4 (Information) und F6 (Persona-Antwort) je Aeusserung.

    uv run python -m pacemaker_agent.tests.judge experiments/runs/t1-gespraech

Liest `utterances.jsonl` (metrics/conversation.py) und bewertet je Aeusserung die erste
Persona-Antwort nach dem hoerbaren Ende der Aeusserung gegen die vorab festgelegte
Mindestinfo (docs/phase-0-testablauf-gespraech.md, Tabelle T1). Judge: Azure OpenAI EU
(`AZURE_JUDGE_DEPLOYMENT`, Default gpt-4.1-mini), Temperatur 0. Jeder markierte Fall wird
zusaetzlich von Hand geprueft -- das Urteil ist ein Filter, kein Beweis.

Nicht parallel zu einem Messlauf auf demselben Azure-OpenAI-Konto starten (Ratenlimit).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI

from ..metrics.collector import _REPO_ROOT

# Vorab festgelegt (Testablauf T1, 2026-10-08). Nicht nachtraeglich aendern.
MINDESTINFO: dict[str, str] = {
    "R01": "Anrufer stellt sich vor und fragt, ob Herr Brandt zwei Minuten hat.",
    "R16": "Anrufer nennt seine Firma (OneTry Vertriebsentwicklung UG, Norddeutschland) und "
    "Referenzkunden (Müller Logistik, Hansa Spedition).",
    "R02": "Frage: Wie lange brauchen neue Vertriebsleute bei Ihnen, bis sie selbstständig "
    "telefonieren?",
    "R03": "Aussage: Es hängt bei uns davon ab, wer gerade Zeit fürs Coaching hat (ganzer Satz).",
    "R17": "Die Einarbeitung sinkt im Schnitt von 12 auf 7 Wochen, gut 40 %.",
    "R09": "Der Anrufer will heute ausdrücklich NICHTS verkaufen.",
    "R12": "Anrufer zeigt Verständnis UND fragt, wie die Leute heute üben (die Frage zählt).",
    "R19": "",
    "R13": "Zwei Fragen: Wer entscheidet das? Bis wann müsste das stehen? (beide)",
    "R05": "Preis: 15.000 € im Jahr für das ganze Team (die zuerst genannte 12 ist korrigiert).",
    "R10": "Das müssen Sie NICHT mit Ihrem Chef abstimmen, das liegt in Ihrem Budget.",
    "R18": "Login über SSO, DSGVO-konform, in Europa gehostet.",
    "R07": "Rückfrage zur Mitarbeiterzahl: 180 oder 200?",
    "R20": "",
    "R15": "Anrufer räumt einen Punkt ein, begründet aber, warum er trotzdem anruft.",
    "R06": "Start im April (nicht März) mit den ersten Kunden.",
    "R04": "Referenz: bei einem Logistiker mit ca. 200 Leuten umgesetzt.",
    "R08": "Gemeint ist das Operations-Team, nicht der Vertrieb.",
    "R11": "Anrufer ist unsicher, ob die Mail schon verschickt wurde, und prüft das.",
    "R21": "Rückfrage: Warum?",
    "R14": "Anrufer schickt Unterlagen und schlägt einen Termin am Donnerstag vor.",
}

PROMPT = """Du bewertest eine Antwort einer Rollenspiel-Persona (Markus Brandt, Head of \
Operations, wird kalt angerufen) auf eine Äußerung des Anrufers. Das Skript des Anrufers \
reagiert nicht auf die Persona; bewerte NICHT, ob das Gespräch insgesamt schlüssig ist.

Mindestinfo der Anruferäußerung: {mindestinfo}
Erkannter Anrufertext (Spracherkennung, ggf. in Teilen): {user}
Antwort der Persona: {reply}

Bewerte zwei Dinge und antworte NUR mit JSON:
{{"F4": "ok" | "verletzt" | "nicht_pruefbar",
  "F6": "ok" | "auffaellig",
  "begruendung": "<ein Satz>"}}

F4 = "verletzt", wenn die Antwort der Mindestinfo widerspricht oder sie erkennbar übergeht \
(z. B. falsche Zahl, Negation umgedreht, nur eine von zwei Fragen beachtet, gestellte Frage \
ignoriert). Die Persona muss nicht zustimmen und nichts wiederholen. "nicht_pruefbar", wenn \
keine Mindestinfo angegeben ist oder keine Antwort vorliegt.
F6 = "auffaellig" bei Rollenbruch, Assistenten-Floskel ("Wie kann ich helfen"), Behauptung, \
ein Mensch oder eine andere Firma zu sein, oder einer Antwort ohne Bezug zur Äußerung."""


async def judge_one(client: AsyncOpenAI, model: str, row: dict) -> dict:
    info = MINDESTINFO.get(row["clip"], "")
    msg = PROMPT.format(
        mindestinfo=info or "(keine)",
        user=" / ".join(row["user_texts"]) or "(nichts erkannt)",
        reply=row["reply"] or "(keine Antwort)",
    )
    for attempt in range(3):
        try:
            r = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": msg}],
                temperature=0,
                response_format={"type": "json_object"},
            )
            return json.loads(r.choices[0].message.content or "{}")
        except Exception as exc:  # noqa: BLE001 -- Ratenlimit/Netz: kurz warten, erneut
            if attempt == 2:
                return {"F4": "fehler", "F6": "fehler", "begruendung": str(exc)[:200]}
            await asyncio.sleep(5 * (attempt + 1))
    return {}


async def run(runs_dir: Path) -> None:
    load_dotenv(_REPO_ROOT / "agent" / ".env")
    model = os.environ.get("AZURE_JUDGE_DEPLOYMENT", "gpt-4.1-mini")
    client = AsyncOpenAI(
        base_url=os.environ["AZURE_OPENAI_ENDPOINT"], api_key=os.environ["AZURE_OPENAI_API_KEY"]
    )
    rows = [
        json.loads(x)
        for x in (runs_dir / "utterances.jsonl").read_text(encoding="utf-8").splitlines()
        if x.strip()
    ]
    out = []
    for row in rows:  # sequenziell: Ratenlimit
        verdict = await judge_one(client, model, row)
        out.append({**row, "judge": verdict, "judge_model": model})
    path = runs_dir / "utterances_judged.jsonl"
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in out) + "\n", "utf-8")
    f4 = [r for r in out if r["judge"].get("F4") == "verletzt"]
    f6 = [r for r in out if r["judge"].get("F6") == "auffaellig"]
    checked = [r for r in out if r["judge"].get("F4") in ("ok", "verletzt")]
    print(f"F4 verletzt: {len(f4)} von {len(checked)} pruefbaren Aeusserungen")
    for r in f4:
        print(f"  {r['clip']} {r['run_id']}: {r['reply'][:90]!r} -- {r['judge']['begruendung']}")
    print(f"F6 auffaellig: {len(f6)} von {len(out)}")
    for r in f6:
        print(f"  {r['clip']} {r['run_id']}: {r['reply'][:90]!r} -- {r['judge']['begruendung']}")
    print(f"Urteile: {path}")


def main() -> None:
    runs_dir = Path(sys.argv[1])
    if not runs_dir.is_absolute():
        runs_dir = _REPO_ROOT / runs_dir
    asyncio.run(run(runs_dir))


if __name__ == "__main__":
    main()
