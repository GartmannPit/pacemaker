"""Erzeugt Test-Audio-Clips fuer den Synthetic Caller per Azure-TTS.

    uv run python -m pacemaker_agent.tests.generate_fixtures

Schreibt 16 kHz/16-bit/mono-WAVs nach fixtures/audio/ (gitignored, siehe
.gitignore -- jede Entwicklerin generiert sie lokal). Text: typische
SDR-Aeusserungen fuer das Kaltakquise-Szenario (Opener + Reaktionen auf
Markus Brandts Einwaende), damit der Synthetic Caller realistische
Turn-Inhalte gegen die Persona spielt statt Platzhaltertext.
"""

from __future__ import annotations

from pathlib import Path

import azure.cognitiveservices.speech as speechsdk
from loguru import logger

from ..config import load_azure_config
from .synthetic_transport import SAMPLE_RATE

FIXTURES_DIR = Path(__file__).resolve().parents[3] / "fixtures" / "audio"

# SDR-Aeusserungen im Kontext von Pacemaker selbst (siehe agent/src/pacemaker_agent/
# personas/kaltakquise_head_of_ops.py fuer die Gegenseite Markus Brandt).
UTTERANCES: dict[str, str] = {
    "01_opener": (
        "Guten Tag, hier ist Lena Fischer von der Pacemaker GmbH. Haben Sie kurz zwei Minuten?"
    ),
    "02_zeitdruck": (
        "Dreissig Sekunden: Neue Vertriebler brauchen im Schnitt drei Monate, bis sie "
        "eigenstaendig Kaltakquise koennen. Wie lange dauert das bei Ihnen aktuell?"
    ),
    "03_wettbewerb": (
        "Verstaendlich. Ging es bei den anderen beiden auch um Vertriebstraining, "
        "oder war das etwas anderes?"
    ),
    "04_mail_brushoff": (
        "Mache ich gern. Soll die Mail auf Kosten eingehen, auf den Umsetzungsaufwand, "
        "oder auf ein Beispielgespraech?"
    ),
    "05_bestandstool": (
        "Wie uebt Ihr Team aktuell Preisverhandlung oder den Umgang mit Widerstand?"
    ),
    "06_budget": "Voellig normal bei dem Betrag. Wer sitzt bei Ihnen sonst noch mit am Tisch?",
    "07_naechster_schritt": (
        "Was braeuchten Sie von mir, damit Sie das intern mit vorlegen koennen?"
    ),
    "08_dritte_nachfrage": (
        "Anders gefragt: Wer merkt bei Ihnen zuerst, wenn ein Verkaufsgespraech schiefgeht?"
    ),
    "09_zusammenfassung": "Kein Problem, dann fasse ich kurz zusammen und wir hoeren voneinander.",
    "10_abschluss": "Danke fuer die offenen Worte, das hilft mir sehr weiter.",
}


def _synthesize(text: str, out_path: Path, speech_config: speechsdk.SpeechConfig) -> None:
    audio_config = speechsdk.audio.AudioOutputConfig(filename=str(out_path))
    synthesizer = speechsdk.SpeechSynthesizer(
        speech_config=speech_config, audio_config=audio_config
    )
    result = synthesizer.speak_text_async(text).get()
    if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
        details = getattr(result, "cancellation_details", None)
        raise RuntimeError(f"TTS fehlgeschlagen fuer {out_path.name!r}: {details}")


def main() -> None:
    cfg = load_azure_config()

    speech_config = speechsdk.SpeechConfig(subscription=cfg.speech_key, region=cfg.speech_region)
    speech_config.speech_synthesis_voice_name = cfg.tts_voice
    assert SAMPLE_RATE == 16000, "SAMPLE_RATE geaendert -- Format-Konstante unten anpassen"
    speech_config.set_speech_synthesis_output_format(
        speechsdk.SpeechSynthesisOutputFormat.Riff16Khz16BitMonoPcm
    )

    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    for name, text in UTTERANCES.items():
        out_path = FIXTURES_DIR / f"{name}.wav"
        _synthesize(text, out_path, speech_config)
        logger.info(f"Erzeugt: {out_path.name}")

    logger.info(f"{len(UTTERANCES)} Clips in {FIXTURES_DIR}")


if __name__ == "__main__":
    main()
