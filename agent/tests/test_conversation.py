"""Tests fuer die Auswertung von Gespraech, Barge-in, Kosten und Transkript-Export
(Testablauf T1-T3, docs/phase-0-testablauf-gespraech.md)."""

from __future__ import annotations

from datetime import UTC, datetime

from pacemaker_agent.metrics.conversation import _speaking_intervals, barge_in_case, utterances
from pacemaker_agent.metrics.costs import per_minute
from pacemaker_agent.metrics.transcript_export import _fmt
from pacemaker_agent.tests.role_test import keyword_hits, repeated_sentences


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).isoformat()


def _run(clips, speaking, transcript=(), turns=(), config=None, ended=None) -> dict:
    return {
        "run_id": "r",
        "config": config or {"barge_in_secs": 1.0, "vad_start_secs": 0.1},
        "events": {
            "clips": list(clips),
            "bot_speaking": list(speaking),
            "ended_by_pipeline_after_clip": ended,
        },
        "turns": list(turns),
        "transcript": list(transcript),
    }


def test_speaking_intervals_pairs_start_and_stop() -> None:
    ev = [["start", 1.0], ["stop", 2.0], ["start", 3.0]]
    assert _speaking_intervals(ev) == [(1.0, 2.0), (3.0, None)]


def test_barge_in_measures_stop_after_interjection_onset() -> None:
    clips = [
        {"uid": 1, "clip": "R01", "voice_start": 0.0, "voice_end": 5.0},
        {"uid": 2, "clip": "R02", "voice_start": 10.0, "voice_end": 15.0},
        {"uid": 3, "clip": "R23", "voice_start": 17.0, "voice_end": 19.0},
    ]
    speaking = [["start", 16.0], ["stop", 17.3]]
    transcript = [{"role": "assistant", "text": "Also", "interrupted": True, "ts": _iso(17.31)}]
    case = barge_in_case(_run(clips, speaking, transcript))
    assert case["triggered"] and case["interrupted"]
    assert case["stop_ms"] == 300.0
    assert not case["late_audio"]


def test_barge_in_not_triggerable_when_persona_silent() -> None:
    clips = [
        {"uid": 1, "clip": "R01", "voice_start": 0.0, "voice_end": 5.0},
        {"uid": 2, "clip": "R02", "voice_start": 10.0, "voice_end": 15.0},
        {"uid": 3, "clip": "R23", "voice_start": 20.0, "voice_end": 22.0},
    ]
    case = barge_in_case(_run(clips, [["start", 16.0], ["stop", 18.0]]))
    assert not case["triggered"]
    assert case["reason"] == "Persona sprach beim Zwischenruf nicht"


def test_backchannel_without_interruption_is_not_counted_as_cut() -> None:
    clips = [
        {"uid": 1, "clip": "R01", "voice_start": 0.0, "voice_end": 5.0},
        {"uid": 2, "clip": "R02", "voice_start": 10.0, "voice_end": 15.0},
        {"uid": 3, "clip": "R22", "voice_start": 17.0, "voice_end": 17.5},
    ]
    case = barge_in_case(_run(clips, [["start", 16.0], ["stop", 21.0]]))
    assert case["triggered"] and not case["interrupted"]


def test_utterance_flags_premature_audio() -> None:
    clips = [{"uid": 1, "clip": "R03", "voice_start": 0.0, "voice_end": 5.0}]
    turns = [{"utterance_id": 1, "status": "zerfallen", "n_turn_ends": 2, "first_audio_ms": 900}]
    rows = utterances(_run(clips, [["start", 2.0], ["stop", 2.5]], turns=turns, config={}))
    assert rows[0]["F2"] and rows[0]["F3"] and not rows[0]["F1"]


def test_cost_per_minute_scales_with_usage() -> None:
    u = {
        "minutes": 2.0,
        "stt_speech_secs": 60.0,
        "prompt_tokens": 2_000_000,
        "completion_tokens": 0,
        "tts_chars": 0,
    }
    c = per_minute(u, "gpt-4.1-nano")
    assert abs(c["llm"] - 0.11) < 1e-9  # 2M Tokens * 0,11 $/1M / 2 Min.
    assert abs(c["stt_upper"] - 1.0 / 60) < 1e-9


def test_transcript_time_format() -> None:
    assert _fmt(75.25) == "01:15,2"
    assert _fmt(None) == ""


def test_role_test_detects_repetition_and_keywords() -> None:
    dialog = [
        {"sprecher": "Persona", "text": "Ich habe dafür keine Zeit heute. Worum geht es?"},
        {"sprecher": "Anrufer", "text": "Wie kann ich Ihnen helfen?"},
        {
            "sprecher": "Persona",
            "text": "Ich habe dafür keine Zeit heute. Kann ich sonst noch was?",
        },
    ]
    assert repeated_sentences(dialog) == ["ich habe dafür keine zeit heute."]
    assert keyword_hits(dialog) == ["kann ich sonst noch"]  # Anruferzeilen zaehlen nicht
