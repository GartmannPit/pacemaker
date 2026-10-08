"""Exportiert ein Lauf-Transkript als lesbare Datei (Markdown) und Tabelle (CSV).

    uv run python -m pacemaker_agent.metrics.transcript_export <run_id | Pfad zur .jsonl>
    uv run python -m pacemaker_agent.metrics.transcript_export --latest

Zeiten relativ zum ersten Eintrag (mm:ss,s), Beginn und Ende je Redebeitrag. Ausgabe neben
dem Transkript: <run_id>.md und <run_id>.csv.
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import datetime
from pathlib import Path

from .collector import RUNS_DIR

SPEAKER = {"user": "Anrufer", "assistant": "Persona", "event": "—"}


def _t(iso: str | None) -> float | None:
    return datetime.fromisoformat(iso).timestamp() if iso else None


def _fmt(secs: float | None) -> str:
    if secs is None:
        return ""
    m, s = divmod(max(secs, 0.0), 60)
    return f"{int(m):02d}:{s:04.1f}".replace(".", ",")


def export(path: Path) -> tuple[Path, Path]:
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    if not rows:
        raise SystemExit(f"Leeres Transkript: {path}")
    t0 = min(t for r in rows for t in (_t(r.get("started_at")), _t(r["ts"])) if t is not None)
    md = [
        f"# Transkript {path.stem}",
        "",
        f"Stack `{rows[0]['stack']}`, Modell `{rows[0]['llm_model']}`. Zeiten ab Gesprächsbeginn; "
        "Beginn = Sprechbeginn (Anrufer laut VAD, Persona erstes Audio), Ende = Abschluss des "
        "Redebeitrags.",
        "",
        "| Beginn | Ende | Sprecher | Text |",
        "|---|---|---|---|",
    ]
    table = []
    for r in rows:
        start = _t(r.get("started_at"))
        end = _t(r["ts"])
        text = r["text"] + (" *(unterbrochen)*" if r.get("interrupted") else "")
        if r["role"] == "event":
            text = f"*[{r['text']}]*"
        md.append(
            f"| {_fmt(start - t0 if start else None)} | {_fmt(end - t0)} | "
            f"{SPEAKER.get(r['role'], r['role'])} | {text.replace('|', '/')} |"
        )
        table.append(
            {
                "beginn_s": round(start - t0, 2) if start else "",
                "ende_s": round(end - t0, 2),
                "sprecher": SPEAKER.get(r["role"], r["role"]),
                "text": r["text"],
                "unterbrochen": bool(r.get("interrupted")),
            }
        )
    md_path, csv_path = path.with_suffix(".md"), path.with_suffix(".csv")
    md_path.write_text("\n".join(md) + "\n", encoding="utf-8")
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(table[0]), delimiter=";")
        writer.writeheader()
        writer.writerows(table)
    return md_path, csv_path


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    arg = sys.argv[1]
    if arg == "--latest":
        candidates = sorted(
            (RUNS_DIR / "transcripts").glob("*.jsonl"), key=lambda p: p.stat().st_mtime
        )
        if not candidates:
            raise SystemExit(f"Keine Transkripte in {RUNS_DIR / 'transcripts'}")
        path = candidates[-1]
    else:
        path = Path(arg)
        if not path.exists():
            path = RUNS_DIR / "transcripts" / f"{arg}.jsonl"
    md_path, csv_path = export(path)
    print(f"{md_path}\n{csv_path}")


if __name__ == "__main__":
    main()
