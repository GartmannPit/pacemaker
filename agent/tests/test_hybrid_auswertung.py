"""Hybrid-Auswertung ausschließlich mit synthetischen Protokollen in tmp_path."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def module(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "tools"))
    return importlib.import_module("gptlive_browser.auswertung")


def write_rows(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def test_overlapping_browser_chunks_are_deduplicated_and_ordered(module, tmp_path) -> None:
    user = {"seq": 0, "rolle": "nutzer", "text": "SYNTHETISCH_A"}
    persona = {"seq": 1, "rolle": "persona", "text": "SYNTHETISCH_B"}
    tail = {"seq": 2, "rolle": "nutzer", "text": "_C"}
    write_rows(
        tmp_path / "sess-browser.jsonl",
        [{"deltas": [persona, tail]}, {"deltas": [user, persona, tail]}],
    )
    write_rows(
        tmp_path / "sess.jsonl",
        [
            {"type": "transcript", "role": "user", "text": user["text"] + tail["text"]},
            {"type": "transcript", "role": "assistant", "text": persona["text"]},
        ],
    )
    output = module.report(tmp_path)
    assert "| user | gleich | 15 | 15 |" in output
    assert "| assistant | gleich | 13 | 13 |" in output
    assert "SYNTHETISCH" not in output


@pytest.mark.parametrize(
    "side,browser,expected",
    [
        ("abc", "abc", "gleich"),
        ("", "", "gleich"),
        ("abc", "ac", "Sideband hat mehr"),
        ("ac", "abc", "Browser hat mehr"),
        ("abc", "abd", "abweichend"),
        ("abcd", "acx", "abweichend"),
        ("ab", "ba", "abweichend"),
        ("", "a", "Browser hat mehr"),
        ("a", "", "Sideband hat mehr"),
    ],
)
def test_k1_classes_per_role(module, tmp_path, side, browser, expected) -> None:
    write_rows(
        tmp_path / "s.jsonl",
        [{"type": "transcript", "role": role, "text": side} for role in ("user", "assistant")],
    )
    write_rows(
        tmp_path / "s-browser.jsonl",
        [
            {
                "deltas": [
                    {"seq": i, "rolle": role, "text": browser}
                    for i, role in enumerate(("nutzer", "persona"))
                ]
            }
        ],
    )
    output = module.report(tmp_path)
    for role in ("user", "assistant"):
        assert f"| {role} | {expected} | {len(side)} | {len(browser)} |" in output


def test_metadata_chronology_gap_and_cumulative_costs(module, tmp_path) -> None:
    result = {
        "reason": "nutzer",
        "complete": True,
        "usage_seconds": 60,
        "backend_tokens": {"input_tokens": 7, "output_tokens": 3, "total_tokens": 10},
        "diagnostics": ["unbekannte_bestaetigungs_id"],
    }
    write_rows(
        tmp_path / "zuerst.jsonl",
        [
            {"type": "status", "status": "angehaengt", "timestamp": "2026-10-27T12:00:00Z"},
            {"type": "usage", "usage_seconds": 15},
            {"type": "usage", "usage_seconds": 60},
            {"type": "usage", "backend_tokens": {"total_tokens": 5}},
            {
                "type": "transcript",
                "role": "user",
                "text": "NICHT_AUSGEBEN_Ä",
                "start_ms": 0,
                "end_ms": 1000,
                "timestamp": "2026-10-27T12:00:40Z",
            },
            {
                "type": "steuerereignis",
                "event": "error",
                "eigen": False,
                "code": "invalid_request",
                "error_type": "invalid_request_error",
                "param": "session",
            },
            {"type": "status", "status": "beendet", "timestamp": "2026-10-27T12:01:00Z", **result},
        ],
    )
    write_rows(
        tmp_path / "aaa_spaeter.jsonl",
        [
            {
                "type": "status",
                "status": "beendet",
                "timestamp": "2026-10-27T12:02:00Z",
                "usage_seconds": 30,
                "complete": False,
                "reason": "unvollstaendig",
                "backend_tokens": {"input_tokens": 2, "output_tokens": 1, "total_tokens": 3},
            }
        ],
    )
    write_rows(
        tmp_path / "sitzungen.jsonl",
        [
            {"session_id": "zuerst", "debug": "positivkontrolle"},
            {"session_id": "zuerst", "result": result},
            {"session_id": "aaa_spaeter", "notschluss_extern": "gesendet"},
        ],
    )
    output = module.report(tmp_path)
    assert output.index("## Sitzung zuerst") < output.index("## Sitzung aaa_spaeter")
    for expected in (
        "Ende-Grund: nutzer; complete: true",
        "Dauer (usage_seconds): 60.000 s",
        "Sideband-Empfang): 20.000 s",
        "Debug-Aktionen: positivkontrolle",
        "notschluss_extern: gesendet",
        "Diagnosen: unbekannte_bestaetigungs_id",
        "| error | false | invalid_request | invalid_request_error | session |",
        "Sitzungen: 2",
        "Live-Sekunden (bekannt): 90.000",
        "0.075000 $",
        "input_tokens=9",
        "output_tokens=4",
        "total_tokens=13",
        "complete: false",
    ):
        assert expected in output
    assert "NICHT_AUSGEBEN" not in output


def test_missing_sources_aborted_start_and_unknown_consumption(module, tmp_path) -> None:
    write_rows(
        tmp_path / "sitzungen.jsonl",
        [
            {
                "session_id": "abbruch",
                "start_abgebrochen": "TimeoutError",
                "notschluss_extern": "gesendet",
            },
            {
                "session_id": "nur_server",
                "result": {"reason": "zeitlimit", "complete": True, "usage_seconds": 12},
            },
        ],
    )
    write_rows(tmp_path / "nur_browser-browser.jsonl", [{"deltas": []}])
    (tmp_path / "nur_sideband.jsonl").write_text("", encoding="utf-8")
    output = module.report(tmp_path)
    assert "Sitzungen: 4" in output
    assert "ohne Verbrauchsangabe: 3" in output
    assert "Live-Sekunden (bekannt): 12.000" in output
    assert "nicht prüfbar (Quelle fehlt)" in output
    assert "Ende-Grund: start_abgebrochen; complete: unbekannt" in output
    assert "Diagnosen: TimeoutError" in output
    assert "Backend-Tokens (bekannt, separat; keine Backend-Kosten berechnet): unbekannt" in output


def test_missing_folder_and_empty_folder(module, tmp_path) -> None:
    for folder in (tmp_path, tmp_path / "fehlt"):
        output = module.report(folder)
        assert "Sitzungen: 0" in output
        assert "0.000000 $" in output


def test_malformed_lines_and_fields_do_not_leak_contents(module, tmp_path) -> None:
    (tmp_path / "s.jsonl").write_text(
        "VERTRAULICHER_PARSEFEHLER\n[]\nnull\n"
        '{"type":"transcript","role":"user","text":{"inhalt":"NICHT_ZEIGEN"}}\n'
        '{"type":"usage","usage_seconds":NaN,"backend_tokens":[]}\n'
        '{"type":"usage","usage_seconds":true}\n'
        '{"type":"status","status":"beendet","timestamp":"ungueltig"}\n',
        encoding="utf-8",
    )
    write_rows(
        tmp_path / "s-browser.jsonl",
        [
            {"deltas": None},
            {"deltas": [None, {}, {"seq": [], "text": "NICHT_ZEIGEN"}]},
        ],
    )
    output = module.report(tmp_path)
    assert "ungültige Zeilen: 4" in output  # einschließlich fehlendem Serverprotokoll
    assert "Dauer (usage_seconds): unbekannt" in output
    assert "VERTRAULICHER_PARSEFEHLER" not in output
    assert "NICHT_ZEIGEN" not in output


def test_cli_writes_only_report(module, tmp_path, monkeypatch, capsys) -> None:
    write_rows(
        tmp_path / "s.jsonl", [{"type": "transcript", "role": "assistant", "text": "GEHEIM"}]
    )
    monkeypatch.setattr("sys.argv", ["auswertung.py", str(tmp_path)])
    module.main()
    captured = capsys.readouterr()
    assert captured.out == module.report(tmp_path)
    assert "GEHEIM" not in captured.out
    assert captured.err == ""
