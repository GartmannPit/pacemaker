"""Auswertung von Testablauf T1 (zusammenhaengendes Gespraech) und T2 (Barge-in/Hoersignale).

    uv run python -m pacemaker_agent.metrics.conversation experiments/runs/t1-gespraech
    uv run python -m pacemaker_agent.metrics.conversation experiments/runs/t2-bargein

Fehlerklassen und Kriterien: docs/phase-0-testablauf-gespraech.md. Grundlage sind nur
Zeitpunkte und Transkripttext (keine Stimm-, Emotions- oder Prosodieanalyse, CLAUDE.md):

- events/<run_id>.json   hoerbarer Bereich je eingespieltem Clip, Sprechintervalle der Persona
                         am Ausgabe-Transport (serverseitig, ohne Client-Puffer)
- turns/<run_id>.jsonl   Turn-Protokoll je Clip (Status, Turn-Enden, Latenzen)
- transcripts/<run_id>.jsonl, manifests/<run_id>.json

F4 (Information) und F6 (Persona-Antwort) bewertet `tests/judge.py`; hier werden dafuer je
Aeusserung die erkannten Nutzertexte und die anschliessende Persona-Antwort exportiert.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from .aggregate import quantile
from .collector import _REPO_ROOT

BARGE_IN_LIMIT_MS = 300.0


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def _speaking_intervals(events: list[list]) -> list[tuple[float, float | None]]:
    """Sprechintervalle der Persona aus ("start"|"stop", t)-Ereignissen."""
    intervals: list[tuple[float, float | None]] = []
    current: float | None = None
    for kind, t in events:
        if kind == "start" and current is None:
            current = t
        elif kind == "stop" and current is not None:
            intervals.append((current, t))
            current = None
    if current is not None:
        intervals.append((current, None))
    return intervals


def _ts(row: dict) -> float:
    return datetime.fromisoformat(row["ts"]).timestamp()


def load_runs(runs_dir: Path) -> list[dict]:
    runs = []
    for manifest_path in sorted((runs_dir / "manifests").glob("*.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        run_id = manifest["run_id"]
        events_path = runs_dir / "events" / f"{run_id}.json"
        if not events_path.exists():
            continue
        runs.append(
            {
                "run_id": run_id,
                "config": manifest["config"],
                "events": json.loads(events_path.read_text(encoding="utf-8")),
                "turns": _read_jsonl(runs_dir / "turns" / f"{run_id}.jsonl"),
                "transcript": _read_jsonl(runs_dir / "transcripts" / f"{run_id}.jsonl"),
            }
        )
    return runs


# --- T2 ------------------------------------------------------------------------------------


def barge_in_case(run: dict) -> dict:
    """Ein T2-Fall: Zwischenruf = letzter Clip der Sitzung."""
    ev = run["events"]
    clips = ev["clips"]
    intervals = _speaking_intervals(ev["bot_speaking"])
    case = {
        "run_id": run["run_id"],
        "vad_start_secs": run["config"].get("vad_start_secs"),
        "clip": clips[-1]["clip"] if clips else None,
        "triggered": False,
        "reason": None,
        "stop_ms": None,
        "late_audio": False,
        "interrupted": False,
    }
    if ev.get("ended_by_pipeline_after_clip") is not None and len(clips) < 3:
        case["reason"] = "aufgelegt vor dem Zwischenruf"
        return case
    if len(clips) < 2 or clips[-1]["voice_start"] is None:
        case["reason"] = "Zwischenruf nicht eingespielt"
        return case
    start, end = clips[-1]["voice_start"], clips[-1]["voice_end"]
    active = [(a, b) for a, b in intervals if a <= start and (b is None or b > start)]
    if not active:
        case["reason"] = "Persona sprach beim Zwischenruf nicht"
        return case
    case["triggered"] = True
    _, stop = active[0]
    # Unterbrochen = Persona verstummt waehrend des Zwischenrufs oder kurz danach (Turn-
    # Erkennung braucht ihre Zeit), nicht am natuerlichen Ende der Antwort weit danach.
    assistant_cut = any(
        r["role"] == "assistant" and r.get("interrupted") and _ts(r) >= start
        for r in run["transcript"]
    )
    if stop is not None and stop <= end + 1.0 and assistant_cut:
        case["interrupted"] = True
        case["stop_ms"] = round((stop - start) * 1000, 1)
        # F5: Persona-Audio setzt wieder ein, solange der Anrufer noch spricht
        case["late_audio"] = any(stop < a < end for a, _ in intervals)
    return case


def report_t2(runs: list[dict]) -> None:
    cases = [barge_in_case(r) for r in runs if r["config"].get("barge_in_secs")]
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for c in cases:
        groups[(c["clip"], c["vad_start_secs"])].append(c)
    print("T2 Barge-in / Hoersignal (serverseitig: hoerbarer Beginn Zwischenruf -> Persona still)")
    print(
        f"{'Clip':5s} {'VAD-Start':>9s} {'Faelle':>6s} {'ausloesbar':>10s} {'unterbrochen':>12s} "
        f"{'<=300 ms':>8s} {'Stopp ms (sortiert)':s}"
    )
    for (clip, vad), rows in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1] or 0)):
        trig = [r for r in rows if r["triggered"]]
        cut = [r for r in trig if r["interrupted"]]
        ok = [r for r in cut if r["stop_ms"] is not None and r["stop_ms"] <= BARGE_IN_LIMIT_MS]
        stops = sorted(r["stop_ms"] for r in cut if r["stop_ms"] is not None)
        print(
            f"{clip:5s} {vad!s:>9s} {len(rows):6d} {len(trig):10d} {len(cut):12d} "
            f"{len(ok):8d} {stops}"
        )
        for r in rows:
            if r["reason"]:
                print(f"      nicht ausloesbar: {r['run_id']} ({r['reason']})")
            if r["late_audio"]:
                print(f"      F5 Audio setzt waehrend des Zwischenrufs wieder ein: {r['run_id']}")
    for vad in sorted({c["vad_start_secs"] for c in cases}):
        rows = [c for c in cases if c["vad_start_secs"] == vad and c["clip"] in ("R23", "R24")]
        trig = [r for r in rows if r["triggered"]]
        ok = [r for r in trig if r["interrupted"] and r["stop_ms"] <= BARGE_IN_LIMIT_MS]
        stops = [r["stop_ms"] for r in trig if r["interrupted"]]
        p50, p90 = quantile(stops, 0.5), quantile(stops, 0.9)
        print(
            f"VAD-Start {vad}: R23+R24 <= 300 ms in {len(ok)} von {len(trig)} ausloesbaren; "
            f"Stopp p50 {p50 if p50 is None else round(p50)} / p90 "
            f"{p90 if p90 is None else round(p90)} ms"
        )


# --- T1 ------------------------------------------------------------------------------------


def utterances(run: dict) -> list[dict]:
    """Je eingespieltem Clip: F1-F3, Latenz und Texte fuer den Judge."""
    ev = run["events"]
    intervals = _speaking_intervals(ev["bot_speaking"])
    turns = {t["utterance_id"]: t for t in run["turns"]}
    rows = []
    transcript = run["transcript"]
    clips = ev["clips"]
    for k, c in enumerate(clips):
        turn = turns.get(c["uid"], {})
        start, end = c["voice_start"], c["voice_end"]
        nxt = clips[k + 1]["voice_start"] if k + 1 < len(clips) else float("inf")
        f1 = turn.get("status") == "keine_turn_erkennung" or (
            turn.get("first_audio_ms") is None and turn.get("first_audio_from_clip_ms") is not None
        )
        f2 = turn.get("n_turn_ends", 0) > 1
        f3 = any(start < a < end for a, _ in intervals) if start and end else False
        # Texte im Fenster dieses Clips (bis zum naechsten Clip)
        window = [r for r in transcript if start - 0.5 <= _ts(r) < nxt]
        user_texts = [r["text"] for r in window if r["role"] == "user"]
        replies = [
            r for r in window if r["role"] == "assistant" and _ts(r) > end and r["text"].strip()
        ]
        rows.append(
            {
                "run_id": run["run_id"],
                "call": run["config"].get("call", 1),
                "repeat": run["config"].get("repeat", 1),
                "clip": c["clip"],
                "status": turn.get("status"),
                "F1": f1,
                "F2": f2,
                "F3": f3,
                "first_audio_ms": turn.get("first_audio_ms"),
                "user_texts": user_texts,
                "reply": replies[0]["text"] if replies else "",
                "reply_interrupted": bool(replies and replies[0].get("interrupted")),
                "hangup": any(r["role"] == "event" and r["text"] == "aufgelegt" for r in window),
            }
        )
    return rows


def report_t1(runs: list[dict], export: Path | None) -> None:
    rows = [u for r in runs if not r["config"].get("barge_in_secs") for u in utterances(r)]
    if not rows:
        return
    n = len(rows)
    print(f"T1 Gespraech: {n} angebotene Aeusserungen in {len(runs)} Sitzungen")
    for key, label in (
        ("F1", "verpasster Sprechbeginn"),
        ("F2", "vorzeitige Turn-Grenze"),
        ("F3", "vorzeitige Audioausgabe"),
    ):
        hits = [r for r in rows if r[key]]
        clips = sorted({r["clip"] for r in hits})
        print(f"  {key} {label:25s} {len(hits):3d} / {n}   {', '.join(clips)}")
    clean = [r["first_audio_ms"] for r in rows if not (r["F1"] or r["F2"]) and r["first_audio_ms"]]
    p50, p90 = quantile(clean, 0.5), quantile(clean, 0.9)
    print(
        f"  Latenz ohne F1/F2 (n={len(clean)}): erstes Audio p50 "
        f"{p50 if p50 is None else round(p50)} / p90 {p90 if p90 is None else round(p90)} ms"
    )
    hangups = [r for r in rows if r["hangup"]]
    print(f"  Persona legt auf: {len(hangups)}x nach {', '.join(r['clip'] for r in hangups)}")
    calls = defaultdict(set)
    for r in rows:
        calls[r["repeat"]].add(r["call"])
    print(
        "  Sitzungen je Durchgang: " + ", ".join(f"{k}: {len(v)}" for k, v in sorted(calls.items()))
    )
    if export is not None:
        export.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8"
        )
        print(f"  Export fuer Judge: {export}")


def main() -> None:
    runs_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else _REPO_ROOT / "experiments" / "runs"
    if not runs_dir.is_absolute():
        runs_dir = _REPO_ROOT / runs_dir
    runs = load_runs(runs_dir)
    if not runs:
        raise SystemExit(f"Keine Laeufe mit Ereignisprotokoll in {runs_dir}.")
    report_t2(runs)
    report_t1(runs, runs_dir / "utterances.jsonl")


if __name__ == "__main__":
    main()
