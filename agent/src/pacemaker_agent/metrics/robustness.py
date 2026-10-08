"""Wertet die Robustheitsprobe aus (echte Aufnahmen, je eine Sitzung pro Aufnahme).

uv run python -m pacemaker_agent.metrics.robustness [experiments/runs/robust]

Frage: Endet der Turn dort, wo die Aufnahme als zusammenhaengende Aeusserung gedacht war --
oder antwortet die Persona schon an einer Denkpause? Bewertet wird nur, was an Text ankommt
und wann (keine Stimm- oder Emotionsanalyse, CLAUDE.md).

Varianten werden nach (STT-Segmentierung, VAD-Stopp, VAD-Start, VAD-Mindestlautstaerke)
gruppiert; aeltere Manifeste ohne Start/Lautstaerke zaehlen mit den Defaults 0.2/0.6. Je Variante:
- zerfallen:        mehr als ein Turn-Ende fuer die Aufnahme (Turn-Protokoll). Strukturelle
                    Abweichung von der Sollgrenze; sagt nichts ueber den Inhalt.
- Ausgabe vor Fortsetzung (Naeherung): unterbrochene Persona-Antwort **mit** Transkripttext --
                    Hinweis, dass simulierte Ausgabe schon lief. Kein Hoernachweis (kein
                    Client-Mitschnitt).
- Latenz:           nur nicht zerfallene Sitzungen mit VAD-Zeitbasis (bei zerfallenen mischt
                    das erste Audio Teilantworten). Sitzungen ohne VAD-Anker (z. B. sehr kurze
                    Aeusserungen ueber den Transkript-Fallback) werden separat mit der
                    Clip-relativen Zeit ausgewiesen statt still zu fehlen.
- gleiche Clips:    Latenz nur ueber Clips, die in allen Varianten nicht zerfallen und eine
                    VAD-Zeitbasis haben -- fairer Vergleich der Geschwindigkeit.
- Wortabdeckung:    grober lexikalischer Anteil der Referenzwoerter im ersten Fragment. Kein
                    Verstaendnismass: ein fehlendes "nicht" wiegt nicht mehr als jedes andere Wort.

Pruefung und Begruendung der Definitionen: docs/2026-10-08-pruefung-robustheitsprobe.md.
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
    """Grobe Wortabdeckung: Anteil der Referenzwoerter, die im empfangenen Text vorkommen."""
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
                "run_id": run_id,
                "clip": clip,
                "variant": (
                    config["stt_segmentation_ms"],
                    config.get("vad_stop_secs"),
                    config.get("vad_start_secs", 0.2),
                    config.get("vad_min_volume", 0.6),
                ),
                "split": turn["status"] == "zerfallen",
                "status": turn["status"],
                "n_turn_ends": turn["n_turn_ends"],
                "output_before_continuation": any(
                    a["interrupted"] and a["text"].strip() for a in assistants
                ),
                "coverage": completeness(references.get(clip, ""), users[0] if users else ""),
                "turn_end_ms": turn["turn_end_ms"],
                "first_audio_ms": turn["first_audio_ms"],
                "first_audio_from_clip_ms": turn.get("first_audio_from_clip_ms"),
            }
        )
    return sessions


def _fmt(v: float | None) -> str:
    return "–" if v is None else f"{v:.0f}"


def report(sessions: list[dict]) -> None:
    by_var: dict[tuple, list[dict]] = defaultdict(list)
    for s in sessions:
        by_var[s["variant"]].append(s)
    variants = sorted(by_var, key=lambda v: tuple(x or 0 for x in v))

    def label(v: tuple) -> str:
        return f"seg {v[0]} / VAD {v[1]}/{v[2]}/{v[3]}"

    print("Je Variante (Segmentierung ms / VAD Stopp s/Start s/Min.-Lautst.), alle Sitzungen")
    print(
        f"{'Variante':28s} {'Sitz.':>5s} {'zerfallen':>13s} {'Ausgabe vor Forts.':>19s} "
        f"{'n Lat.':>6s} {'1. Audio p50/p90':>17s} {'Turn-Ende p50/p90':>18s} "
        f"{'ohne VAD-Basis':>15s} {'Wortabd.':>8s}"
    )
    for v in variants:
        rows = by_var[v]
        split = [r for r in rows if r["split"]]
        out_before = sum(r["output_before_continuation"] for r in split)
        ok = [r for r in rows if not r["split"]]
        timed = [r for r in ok if r["first_audio_ms"] is not None]
        untimed = [r for r in ok if r["first_audio_ms"] is None]
        fa = [r["first_audio_ms"] for r in timed]
        te = [r["turn_end_ms"] for r in timed if r["turn_end_ms"] is not None]
        cov = [r["coverage"] for r in rows if r["coverage"] is not None]
        print(
            f"{label(v):28s} {len(rows):5d} {len(split):4d} ({len(split) / len(rows):4.0%}) "
            f"{out_before:6d} von {len(split):3d}      {len(timed):6d} "
            f"{_fmt(quantile(fa, 0.5)):>8s} / {_fmt(quantile(fa, 0.9)):>6s} "
            f"{_fmt(quantile(te, 0.5)):>8s} / {_fmt(quantile(te, 0.9)):>6s} "
            f"{len(untimed):15d} {sum(cov) / len(cov):8.0%}"
        )

    untimed_all = [s for s in sessions if not s["split"] and s["first_audio_ms"] is None]
    if untimed_all:
        print(
            "\nOhne VAD-Zeitbasis (Turn-Ende ueber Transkript-Fallback), erstes Audio ab Clip-Ende:"
        )
        for s in sorted(untimed_all, key=lambda s: (s["clip"], s["variant"])):
            from_clip = _fmt(s["first_audio_from_clip_ms"])
            print(f"  {s['clip']:5s} {label(s['variant']):28s} {from_clip} ms")

    # Fairer Geschwindigkeitsvergleich: dieselben Clips in allen Varianten
    clean_clips = {
        c
        for c in {s["clip"] for s in sessions}
        if all(
            not s["split"] and s["first_audio_ms"] is not None for s in sessions if s["clip"] == c
        )
    }
    if clean_clips:
        names = ", ".join(sorted(clean_clips))
        print(f"\nGleiche Clips ({len(clean_clips)}: {names}), erstes Audio p50/p90:")
        for v in variants:
            fa = [r["first_audio_ms"] for r in by_var[v] if r["clip"] in clean_clips]
            p50, p90 = _fmt(quantile(fa, 0.5)), _fmt(quantile(fa, 0.9))
            print(f"  {label(v):28s} n={len(fa):3d}  {p50} / {p90}")

    print("\nZerfall je Clip (Sitzungen zerfallen / gesamt)")
    clips = sorted({s["clip"] for s in sessions})
    print(f"{'Clip':5s} " + " ".join(f"{label(v):>28s}" for v in variants))
    for clip in clips:
        cells = []
        for v in variants:
            rows = [r for r in by_var[v] if r["clip"] == clip]
            cells.append(f"{sum(r['split'] for r in rows)}/{len(rows)}")
        if any(not c.startswith("0/") for c in cells):
            print(f"{clip:5s} " + " ".join(f"{c:>28s}" for c in cells))


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
