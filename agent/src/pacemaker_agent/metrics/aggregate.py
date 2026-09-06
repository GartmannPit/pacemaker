"""Aggregiert experiments/runs/*.jsonl zu p50/p90/p95 je Stack.

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


def load(runs_dir: Path) -> pd.DataFrame:
    files = sorted(runs_dir.glob("*.jsonl"))
    if not files:
        raise SystemExit(f"Keine *.jsonl in {runs_dir}. Erst Messlaeufe erzeugen.")
    return pd.concat((pd.read_json(f, lines=True) for f in files), ignore_index=True)


def summarize(df: pd.DataFrame) -> pd.DataFrame:
    grouped = df.groupby("stack")
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
    for stack, value in df.groupby("stack")["e2e_ms"].quantile(0.90).items():
        mark = "OK  " if value < E2E_TARGET_P90_MS else "FAIL"
        print(f"  [{mark}] {stack}: {value:.0f} ms")


if __name__ == "__main__":
    main()
