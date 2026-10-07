"""Tests fuer Turn-Protokoll, Clip-Sprechende und Auswertung (Messkette, Schritt A)."""

from __future__ import annotations

from array import array

from pacemaker_agent.metrics.aggregate import quantile
from pacemaker_agent.metrics.turn_ledger import (
    UtteranceEvents,
    classify,
    main_sentence_start,
    summarize,
    text_delivery,
)
from pacemaker_agent.tests.synthetic_transport import SAMPLE_RATE, last_voiced_sample


def _utterance(**kwargs) -> UtteranceEvents:
    return UtteranceEvents(utterance_id=1, clip="01.wav", window_start=0.0, **kwargs)


def test_classify_answered() -> None:
    assert classify(_utterance(turn_ends=[10.0], first_audio=11.0)) == "beantwortet"


def test_classify_no_turn_detected() -> None:
    assert classify(_utterance()) == "keine_turn_erkennung"


def test_classify_split_turn() -> None:
    assert classify(_utterance(turn_ends=[10.0, 12.0], first_audio=11.0)) == "zerfallen"


def test_classify_silent_persona_with_error() -> None:
    u = _utterance(turn_ends=[10.0], errors=["TTS context completed with no audio"])
    assert classify(u) == "audiofehler"


def test_classify_silent_persona_without_error() -> None:
    assert classify(_utterance(turn_ends=[10.0])) == "keine_antwort"


def test_classify_interrupted() -> None:
    u = _utterance(turn_ends=[10.0], first_audio=11.0, interrupted=True)
    assert classify(u) == "abgebrochen"


def test_main_sentence_after_short_opener() -> None:
    words = [(1.0, "Hm,"), (1.2, "nee."), (1.5, "Wir"), (1.7, "haben")]
    ts, first_sentence = main_sentence_start(words)
    assert ts == 1.5
    assert first_sentence == "Hm, nee."


def test_main_sentence_missing_for_single_sentence() -> None:
    ts, _ = main_sentence_start([(1.0, "Moment"), (1.2, "mal.")])
    assert ts is None


def test_summarize_measures_from_vad_speech_end() -> None:
    u = _utterance(
        speech_end_clip=9.95,
        speech_end_vad=[10.0],
        turn_ends=[10.4],
        text_deltas=[10.8, 10.81],
        first_audio=11.0,
        words=[(11.0, "Ach"), (11.2, "so."), (11.6, "Und?")],
    )
    row = summarize(u)
    assert row["status"] == "beantwortet"
    assert row["turn_end_ms"] == 400.0
    assert row["first_text_ms"] == 800.0
    assert row["first_audio_ms"] == 1000.0
    assert row["main_sentence_ms"] == 1600.0
    assert row["first_audio_from_clip_ms"] == 1050.0


def test_text_delivery_detects_buffering() -> None:
    buffered = [_utterance(text_deltas=[1.0, 1.0001, 1.0002, 1.0003])]
    streaming = [_utterance(text_deltas=[1.0, 1.003, 1.006, 1.009])]
    assert text_delivery(buffered)["text_delivery"] == "gepuffert"
    assert text_delivery(streaming)["text_delivery"] == "streamend"


def test_last_voiced_sample_ignores_trailing_silence() -> None:
    voiced = [3000] * (SAMPLE_RATE // 2)  # 0,5 s Ton
    silence = [0] * (SAMPLE_RATE // 2)  # 0,5 s Stille
    pcm = array("h", voiced + silence).tobytes()
    assert last_voiced_sample(pcm) == SAMPLE_RATE // 2


def test_quantile_interpolates_like_pandas() -> None:
    assert quantile([1.0, 2.0, 3.0, 4.0], 0.5) == 2.5
    assert quantile([], 0.9) is None
