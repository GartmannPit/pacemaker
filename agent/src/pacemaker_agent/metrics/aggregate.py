"""Aggregiert experiments/runs/*.jsonl zu p50/p90/p95 je Stack und LLM-Modell.

uv run python -m pacemaker_agent.metrics.aggregate               # Default: RUNS_DIR
uv run python -m pacemaker_agent.metrics.aggregate <anderer-pfad>
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from .collector import RUNS_DIR

METRIC_COLS = ["e2e_ms", "turn_detection_ms", "llm_ttfb_ms", "tts_ttfb_ms"]
E2E_TARGET_P90_MS = 900  # Akzeptanzkriterium Phase 0 §2
GROUP_COLS = ["stack", "llm_model"]


def _grouped(df: pd.DataFrame):
    return df.groupby(GROUP_COLS)


def load(runs_dir: Path) -> pd.DataFrame:
    files = sorted(runs_dir.glob("*.jsonl"))
    if not files:
        raise SystemExit(f"Keine *.jsonl in {runs_dir}. Erst Messlaeufe erzeugen.")
    df = pd.concat((pd.read_json(f, lines=True) for f in files), ignore_index=True)
    # Aeltere Laeufe (vor 2026-10) haben kein llm_model-Feld.
    if "llm_model" not in df.columns:
        df["llm_model"] = None
    df["llm_model"] = df["llm_model"].fillna("unbekannt")
    return df


def summarize(df: pd.DataFrame) -> pd.DataFrame:
    grouped = _grouped(df)
    cols: dict[tuple[str, str], pd.Series] = {}
    for col in METRIC_COLS:
        if col not in df.columns:
            continue
        for q in (0.50, 0.90, 0.95):
            cols[(col, f"p{int(q * 100)}")] = grouped[col].quantile(q)
    out = pd.DataFrame(cols)
    out.columns = pd.MultiIndex.from_tuples(out.columns)
    out[("turns", "")] = grouped.size()
    return out.round(0)


def main() -> None:
    runs_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else RUNS_DIR
    df = load(runs_dir)

    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 160)
    print(summarize(df))

    print(f"\nAkzeptanzkriterium: E2E p90 < {E2E_TARGET_P90_MS} ms")
    for (stack, llm_model), value in _grouped(df)["e2e_ms"].quantile(0.90).items():
        mark = "OK  " if value < E2E_TARGET_P90_MS else "FAIL"
        print(f"  [{mark}] {stack} / {llm_model}: {value:.0f} ms")


if __name__ == "__main__":
    main()
