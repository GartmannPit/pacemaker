"""Wertet die Robustheitsprobe aus (echte Aufnahmen, je eine Sitzung pro Aufnahme).

uv run python -m pacemaker_agent.metrics.robustness [experiments/runs/robust]

Frage: Kommt eine echte Aeusserung -- mit Denkpausen, Korrekturen, mehreren Saetzen -- als
*eine* vollstaendige Nachricht bei der Persona an, bevor sie antwortet? Bewertet wird nur,
was an Text ankommt und wann (keine Stimm- oder Emotionsanalyse, CLAUDE.md).

Je Sitzung (Manifest: clip, stt_segmentation_ms):
- zerfallen:      mehr als ein Turn-Ende fuer die Aufnahme (Turn-Protokoll)
- abgebrochen:    Persona-Antworten, die von der Fortsetzung unterbrochen wurden (Transkript)
- vollstaendig:   Anteil der Referenzwoerter (robust_index.json, `stt_check`) in der ersten
                  Nutzernachricht, auf die die Persona antwortet
- Turn-Ende / erstes Audio: ms ab VAD-Sprechende (wie die Latenzmetrik)
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from .aggregate import quantile
from .collector import _REPO_ROOT

DEFAULT_DIR = _REPO_ROOT / "experiments" / "runs" / "robust"
INDEX = _REPO_ROOT / "agent" / "fixtures" / "robust" / "robust_index.json"


def _words(text: str) -> list[str]:
    return re.findall(r"[a-zäöüß0-9]+", text.lower())


def completeness(reference: str, received: str) -> float | None:
    ref = _words(reference)
    if not ref:
        return None
    got = set(_words(received))
    return sum(w in got for w in ref) / len(ref)


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def load_sessions(runs_dir: Path, references: dict[str, str]) -> list[dict]:
    sessions = []
    for manifest_path in sorted((runs_dir / "manifests").glob("*.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        config = manifest["config"]
        clip = config.get("clip")
        if clip is None:
            continue
        run_id = manifest["run_id"]
        turns = _read_jsonl(runs_dir / "turns" / f"{run_id}.jsonl")
        transcript = _read_jsonl(runs_dir / "transcripts" / f"{run_id}.jsonl")
        if not turns:
            continue
        turn = turns[0]
        users = [r["text"] for r in transcript if r["role"] == "user"]
        assistants = [r for r in transcript if r["role"] == "assistant"]
        sessions.append(
            {
                "clip": clip,
                "seg": config["stt_segmentation_ms"],
                "status": turn["status"],
                "n_turn_ends": turn["n_turn_ends"],
                "interrupted": sum(bool(a["interrupted"]) for a in assistants),
                "complete": completeness(references.get(clip, ""), users[0] if users else ""),
                "turn_end_ms": turn["turn_end_ms"],
                "first_audio_ms": turn["first_audio_ms"],
                "first_user_msg": users[0] if users else "",
            }
        )
    return sessions


def report(sessions: list[dict]) -> None:
    by_seg: dict[int, list[dict]] = defaultdict(list)
    for s in sessions:
        by_seg[s["seg"]].append(s)

    print("Je Segmentierungswert (alle Sitzungen beider Durchgaenge)")
    print(
        f"{'Segm.':>6s} {'Sitz.':>5s} {'zerfallen':>10s} {'mit Abbruch':>11s} "
        f"{'vollst. 1. Nachricht':>20s} {'Turn-Ende p50/p90':>18s} {'1. Audio p50/p90':>17s}"
    )
    for seg in sorted(by_seg):
        rows = by_seg[seg]
        split = sum(r["status"] == "zerfallen" for r in rows)
        interrupted = sum(r["interrupted"] > 0 for r in rows)
        comp = [r["complete"] for r in rows if r["complete"] is not None]
        te = [r["turn_end_ms"] for r in rows if r["turn_end_ms"] is not None]
        fa = [r["first_audio_ms"] for r in rows if r["first_audio_ms"] is not None]
        print(
            f"{seg:6d} {len(rows):5d} {split:5d} ({split / len(rows):4.0%}) "
            f"{interrupted:5d} ({interrupted / len(rows):4.0%}) "
            f"{sum(comp) / len(comp):19.0%} "
            f"{quantile(te, .5):8.0f} / {quantile(te, .9):6.0f} "
            f"{quantile(fa, .5):8.0f} / {quantile(fa, .9):6.0f}"
        )

    print("\nAufnahmen mit Zerfall oder unvollstaendiger erster Nachricht (< 90 %)")
    clips = sorted({s["clip"] for s in sessions})
    segs = sorted(by_seg)
    print(f"{'Clip':5s} " + " ".join(f"{'seg ' + str(s):>16s}" for s in segs))
    for clip in clips:
        cells = []
        flagged = False
        for seg in segs:
            rows = [r for r in by_seg[seg] if r["clip"] == clip]
            split = sum(r["status"] == "zerfallen" for r in rows)
            comp = min((r["complete"] for r in rows if r["complete"] is not None), default=None)
            flagged |= split > 0 or (comp is not None and comp < 0.9)
            comp_txt = "–" if comp is None else f"{comp:.0%}"
            cells.append(f"{split}/{len(rows)} zerf., {comp_txt:>4s}")
        if flagged:
            print(f"{clip:5s} " + " ".join(f"{c:>16s}" for c in cells))


def main() -> None:
    runs_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DIR
    if not runs_dir.is_absolute():
        runs_dir = _REPO_ROOT / runs_dir
    index = json.loads(INDEX.read_text(encoding="utf-8")) if INDEX.exists() else []
    references = {e["id"]: e["stt_check"] for e in index}
    sessions = load_sessions(runs_dir, references)
    if not sessions:
        raise SystemExit(f"Keine Sitzungen mit Clip-Angabe in {runs_dir}/manifests.")
    report(sessions)


if __name__ == "__main__":
    main()
