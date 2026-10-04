"""Erzeugt Test-Audio-Clips fuer den Synthetic Caller per Azure-TTS.

    uv run python -m pacemaker_agent.tests.generate_fixtures

Schreibt 16 kHz/16-bit/mono-WAVs nach fixtures/audio/ (gitignored, siehe
.gitignore -- jede Entwicklerin generiert sie lokal). Text: typische
SDR-Aeusserungen fuer das Kaltakquise-Szenario (Opener + Reaktionen auf
Markus Brandts Einwaende), damit der Synthetic Caller realistische
Turn-Inhalte gegen die Persona spielt statt Platzhaltertext.
"""

from __future__ import annotations

import math
import wave
from array import array
from pathlib import Path

import azure.cognitiveservices.speech as speechsdk
from loguru import logger
from pipecat.audio.vad.vad_analyzer import VAD_STOP_SECS

from ..config import load_azure_config
from .synthetic_transport import SAMPLE_RATE

FIXTURES_DIR = Path(__file__).resolve().parents[3] / "fixtures" / "audio"

# SDR-Aeusserungen im Kontext von Pacemaker selbst (siehe agent/src/pacemaker_agent/
# personas/kaltakquise_head_of_ops.py fuer die Gegenseite Markus Brandt).
#
# Jeder Clip ist genau EINE Aeusserung: ein Satz, kein Komma nach einem in sich
# vollstaendigen Satzteil. Grund (2026-10-03): Zwei-Satz-Clips wurden an der Satzpause in
# zwei User-Turns zerlegt (Pause > VAD_STOP_SECS, Smart Turn wertet den ersten Satz zu Recht
# als vollstaendig). Folge: abgebrochene Bot-Antworten, Turns ohne Messwert (bei s2s bis
# 22 %), und die Messung bevorzugte schnelle Antworten. main() prueft die Pausen nach.
UTTERANCES: dict[str, str] = {
    "01_opener": (
        "Guten Tag Herr Brandt hier spricht Lena Fischer von der Pacemaker GmbH "
        "und ich hätte gern zwei Minuten Ihrer Zeit."
    ),
    "02_zeitdruck": (
        "Wie lange brauchen neue Vertriebler bei Ihnen aktuell bis sie eigenständig "
        "Kaltakquise machen können?"
    ),
    "03_wettbewerb": (
        "Ging es bei den anderen beiden Anrufen auch um Vertriebstraining oder um etwas anderes?"
    ),
    "04_mail_brushoff": (
        "Soll ich in der Mail eher auf die Kosten oder auf den Umsetzungsaufwand eingehen?"
    ),
    "05_bestandstool": (
        "Wie übt Ihr Team aktuell Preisverhandlung oder den Umgang mit Widerstand?"
    ),
    "06_budget": (
        "Wer sitzt bei Ihnen bei einer Investition in dieser Größenordnung sonst noch mit am Tisch?"
    ),
    "07_naechster_schritt": "Welche Unterlagen bräuchten Sie von mir für eine interne Vorlage?",
    "08_dritte_nachfrage": (
        "Wer bekommt bei Ihnen schief laufende Verkaufsgespräche eigentlich als Erstes mit?"
    ),
    "09_zusammenfassung": (
        "Dann fasse ich das kurz per Mail zusammen und wir hören nächste Woche voneinander."
    ),
    "10_abschluss": "Vielen Dank für die offenen Worte und Ihre Zeit heute.",
}

# Laengste zulaessige Pause innerhalb eines Clips. Ab VAD_STOP_SECS meldet Silero ein
# Sprechende, und Smart Turn entscheidet ueber einen Turn-Wechsel -- darunter bleibt der
# Clip sicher ein Turn.
MAX_INTERNAL_PAUSE_MS = int(VAD_STOP_SECS * 1000)
_FRAME_MS = 10
_SILENCE_RATIO = 0.05  # Frame gilt als still unter 5 % des lautesten Frames (RMS)


def longest_internal_pause_ms(wav_path: Path) -> int:
    """Laengste Stille zwischen erstem und letztem hoerbaren Frame, in ms."""
    with wave.open(str(wav_path), "rb") as wav_file:
        rate = wav_file.getframerate()
        samples = array("h", wav_file.readframes(wav_file.getnframes()))
    step = rate * _FRAME_MS // 1000
    rms = [
        math.sqrt(sum(x * x for x in samples[i : i + step]) / step)
        for i in range(0, len(samples) - step + 1, step)
    ]
    threshold = max(rms) * _SILENCE_RATIO
    voiced = [i for i, value in enumerate(rms) if value >= threshold]
    longest = run = 0
    for value in rms[voiced[0] : voiced[-1] + 1]:
        run = run + 1 if value < threshold else 0
        longest = max(longest, run)
    return longest * _FRAME_MS


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
    for stale in FIXTURES_DIR.glob("*.wav"):
        stale.unlink()  # alte Clips nicht versehentlich mit abspielen

    too_long: list[str] = []
    for name, text in UTTERANCES.items():
        out_path = FIXTURES_DIR / f"{name}.wav"
        _synthesize(text, out_path, speech_config)
        pause_ms = longest_internal_pause_ms(out_path)
        logger.info(f"Erzeugt: {out_path.name} (laengste interne Pause {pause_ms} ms)")
        if pause_ms >= MAX_INTERNAL_PAUSE_MS:
            too_long.append(f"{name} ({pause_ms} ms)")

    logger.info(f"{len(UTTERANCES)} Clips in {FIXTURES_DIR}")
    if too_long:
        raise SystemExit(
            f"Pause >= {MAX_INTERNAL_PAUSE_MS} ms (VAD-Stopp) in: {', '.join(too_long)} -- "
            "Clip wuerde in mehrere Turns zerfallen, Text umformulieren."
        )


if __name__ == "__main__":
    main()
