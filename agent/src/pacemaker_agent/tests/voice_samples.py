"""Erzeugt das Blind-A/B-Paket fuer das Muss-Kriterium Sprachqualitaet.

    uv run python -m pacemaker_agent.tests.voice_samples

Gleiche Persona-Saetze mit mehreren maennlichen deutschen Azure-Stimmen (Germany West Central),
Dateinamen nur mit Codebuchstaben; die Zuordnung steht getrennt in `_schluessel.json`.
Ausgabe: experiments/runs/stimmen/ (gitignored). Bewertungsbogen: `bewertung.md` dort.
Bewerten: beide Gruender unabhaengig, 1-5, ohne vorher den Schluessel zu oeffnen.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import azure.cognitiveservices.speech as speechsdk
from dotenv import load_dotenv

from ..config import load_azure_config
from ..metrics.collector import _REPO_ROOT

# Maennliche Persona; aktueller Produkt-Default zuerst. HD-Stimme nur, wenn in der Region
# verfuegbar (sonst meldet das Skript den Fehler und laesst sie aus).
VOICES = [
    "de-DE-ConradNeural",
    "de-DE-FlorianMultilingualNeural",
    "de-DE-KillianNeural",
    "de-DE-Florian:DragonHDLatestNeural",
]

LINES = [
    "Ja, Brandt hier. Hm, ich hab gerade nicht viel Zeit. Worum geht's denn?",
    "Naja, wir haben dafür schon ein Tool im Einsatz. Das läuft eigentlich ganz ordentlich.",
    "Moment mal. Zwölf auf sieben Wochen? Wie messen Sie das denn konkret?",
    "Über fünfzehntausend Euro im Jahr entscheide ich nicht allein, das muss ich mit der "
    "Geschäftsführung abstimmen.",
    "Okay, schicken Sie mir das per Mail. Ich schau's mir an, aber versprechen kann ich nichts.",
]

SSML = (
    "<speak version='1.0' xml:lang='de-DE' xmlns:mstts='http://www.w3.org/2001/mstts'>"
    "<voice name='{voice}'><mstts:silence type='Leading-exact' value='0ms' />"
    "<mstts:silence type='Tailing-exact' value='0ms' />{text}</voice></speak>"
)


def main() -> None:
    load_dotenv(_REPO_ROOT / "agent" / ".env")
    cfg = load_azure_config()
    out = _REPO_ROOT / "experiments" / "runs" / "stimmen"
    out.mkdir(parents=True, exist_ok=True)
    speech_config = speechsdk.SpeechConfig(subscription=cfg.speech_key, region=cfg.speech_region)
    speech_config.set_speech_synthesis_output_format(
        speechsdk.SpeechSynthesisOutputFormat.Riff24Khz16BitMonoPcm
    )
    codes = list("ABCDEFG")[: len(VOICES)]
    rng = random.Random()  # bewusst ohne festen Seed: Zuordnung nicht aus dem Code ablesbar
    shuffled = VOICES[:]
    rng.shuffle(shuffled)
    key = {}
    for code, voice in zip(codes, shuffled, strict=True):
        ok = True
        for n, text in enumerate(LINES, 1):
            path = out / f"stimme_{code}_satz{n}.wav"
            synth = speechsdk.SpeechSynthesizer(
                speech_config=speech_config,
                audio_config=speechsdk.audio.AudioOutputConfig(filename=str(path)),
            )
            result = synth.speak_ssml_async(SSML.format(voice=voice, text=text)).get()
            if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
                print(f"Stimme {code}: Synthese fehlgeschlagen ({result.cancellation_details})")
                path.unlink(missing_ok=True)
                ok = False
                break
        if ok:
            key[code] = voice
    (out / "_schluessel.json").write_text(json.dumps(key, indent=2), encoding="utf-8")
    sheet = [
        "# Blind-Bewertung der Persona-Stimme",
        "",
        "Bitte **unabhängig** bewerten und `_schluessel.json` erst danach öffnen.",
        "Alle Dateien `stimme_<Code>_satz<n>.wav` anhören (Kopfhörer). Frage je Stimme:",
        "**„Für ein Rollenspiel ausreichend natürlich?"** 1 = gar nicht · 3 = geht so · "
        "5 = wie ein echter Gesprächspartner.",
        "",
        "| Stimme | Bewertung 1–5 | Bemerkung |",
        "|---|---|---|",
        *[f"| {c} |  |  |" for c in key],
        "",
        "Name: ____________  Datum: ____________",
        "",
        "Kriterium Phase 0: Mittel beider Gründer ≥ 3,5 für die empfohlene Stimme.",
    ]
    (out / "bewertung.md").write_text("\n".join(sheet) + "\n", encoding="utf-8")
    print(f"{len(key)} Stimmen, {len(LINES)} Sätze je Stimme -> {out}")


if __name__ == "__main__":
    main()
