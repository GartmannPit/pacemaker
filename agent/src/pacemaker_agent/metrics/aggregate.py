"""Wertet Messlaeufe aus: zuerst je Lauf, dann gepoolt nur ueber identische Konfigurationen.

uv run python -m pacemaker_agent.metrics.aggregate               # Default: RUNS_DIR
uv run python -m pacemaker_agent.metrics.aggregate <anderer-pfad>

Ein Lauf = experiments/runs/<run_id>.jsonl (Latenz je beantworteter Aeusserung), dazu --
falls vorhanden -- manifests/<run_id>.json (Konfiguration) und turns/<run_id>.jsonl
(Status und Zeitpunkte je angebotener Aeusserung). Laeufe ohne Manifest (vor 2026-10-07)
werden je Lauf gezeigt, aber nie gepoolt: ihre Konfiguration ist nicht belegt.

Latenzwerte (`e2e`) beziehen sich auf das erste Bot-Audio, Definition siehe collector.py.
`Hauptsatz` ist die Zeit bis zum Hoerbeginn des ersten Worts nach dem ersten Satzende
(Hilfsmetrik, siehe turn_ledger.py). Ausfaelle stehen als Fehlerquote daneben und fallen
nicht still aus den Quantilen.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .collector import RUNS_DIR

E2E_TARGET_P90_MS = 900  # Akzeptanzkriterium Phase 0 §2


def quantile(values: list[float], q: float) -> float | None:
    """Lineare Interpolation (wie pandas/numpy-Default)."""
    if not values:
        return None
    v = sorted(values)
    k = (len(v) - 1) * q
    lo = int(k)
    hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (k - lo)


@dataclass
class Run:
    run_id: str
    stack: str
    llm_model: str
    e2e: list[float]
    manifest: dict | None = None
    turns: list[dict] = field(default_factory=list)

    @property
    def config_hash(self) -> str:
        return self.manifest["config_hash"] if self.manifest else "unbekannt"

    def ledger_values(self, key: str) -> list[float]:
        return [t[key] for t in self.turns if t["status"] == "beantwortet" and t[key] is not None]


def _read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def load_runs(runs_dir: Path) -> list[Run]:
    runs = []
    for path in sorted(runs_dir.glob("*.jsonl")):
        rows = _read_jsonl(path)
        if not rows or "e2e_ms" not in rows[0]:
            print(f"Uebersprungen (keine Messdatei): {path.name}", file=sys.stderr)
            continue
        run_id = path.stem
        manifest_path = runs_dir / "manifests" / f"{run_id}.json"
        turns_path = runs_dir / "turns" / f"{run_id}.jsonl"
        runs.append(
            Run(
                run_id=run_id,
                stack=rows[0].get("stack", "unbekannt"),
                llm_model=rows[0].get("llm_model") or "unbekannt",
                e2e=[r["e2e_ms"] for r in rows],
                manifest=(
                    json.loads(manifest_path.read_text(encoding="utf-8"))
                    if manifest_path.exists()
                    else None
                ),
                turns=_read_jsonl(turns_path) if turns_path.exists() else [],
            )
        )
    return runs


def _fmt(value: float | None) -> str:
    return "–" if value is None else f"{value:.0f}"


def print_per_run(runs: list[Run]) -> None:
    print("Je Lauf (e2e = bis erstes Audio; Hauptsatz = bis Wort nach erstem Satzende)")
    header = (
        f"{'run_id':28s} {'Modell':22s} {'Konfig':12s} {'angeb.':>6s} {'Fehler':>6s} "
        f"{'e2e p50':>7s} {'p90':>5s} {'p95':>5s} {'max':>5s} {'1.Turn':>6s} "
        f"{'Hauptsatz p50':>13s} {'p90':>5s} {'LLM-Text':>9s}"
    )
    print(header)
    for r in runs:
        offered = len(r.turns) if r.turns else None
        failed = sum(t["status"] != "beantwortet" for t in r.turns) if r.turns else None
        delivery = (r.manifest or {}).get("result", {}).get("text_delivery", "–")
        main = r.ledger_values("main_sentence_ms")
        print(
            f"{r.run_id:28s} {r.llm_model[:22]:22s} {r.config_hash:12s} "
            f"{_fmt(offered):>6s} {_fmt(failed):>6s} "
            f"{_fmt(quantile(r.e2e, 0.5)):>7s} {_fmt(quantile(r.e2e, 0.9)):>5s} "
            f"{_fmt(quantile(r.e2e, 0.95)):>5s} {_fmt(max(r.e2e)):>5s} {_fmt(r.e2e[0]):>6s} "
            f"{_fmt(quantile(main, 0.5)):>13s} {_fmt(quantile(main, 0.9)):>5s} {delivery:>9s}"
        )


def print_pooled(runs: list[Run]) -> None:
    pools: dict[str, list[Run]] = {}
    for r in runs:
        if r.manifest:
            pools.setdefault(r.config_hash, []).append(r)
    if not pools:
        return
    print("\nGepoolt je identischer Konfiguration (nur Laeufe mit Manifest)")
    print(
        f"{'Konfig':12s} {'Modell':22s} {'Laeufe':>6s} {'Turns':>5s} {'Fehlerquote':>11s} "
        f"{'e2e p50':>7s} {'p90':>5s} {'p90 je Lauf':>20s}  Kriterium"
    )
    for config_hash, members in pools.items():
        e2e = [v for r in members for v in r.e2e]
        offered = sum(len(r.turns) for r in members)
        failed = sum(t["status"] != "beantwortet" for r in members for t in r.turns)
        per_run = ", ".join(_fmt(quantile(r.e2e, 0.9)) for r in members)
        p90 = quantile(e2e, 0.9)
        verdict = "OK" if p90 is not None and p90 < E2E_TARGET_P90_MS else "FAIL"
        rate = f"{failed / offered:.1%}" if offered else "–"
        print(
            f"{config_hash:12s} {members[0].llm_model[:22]:22s} {len(members):6d} {len(e2e):5d} "
            f"{rate:>11s} {_fmt(quantile(e2e, 0.5)):>7s} {_fmt(p90):>5s} {per_run:>20s}  "
            f"[{verdict}] p90 < {E2E_TARGET_P90_MS} ms"
        )
    print(
        "Hinweis: Gepoolte Quantile behandeln alle Turns als unabhaengig (wiederholte Clips,"
        " gemeinsame Sitzung) -- die Werte je Lauf zeigen die tatsaechliche Streuung."
    )


def main() -> None:
    runs_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else RUNS_DIR
    runs = load_runs(runs_dir)
    if not runs:
        raise SystemExit(f"Keine Messlaeufe in {runs_dir}.")
    print_per_run(runs)
    print_pooled(runs)
    if any(r.manifest is None for r in runs):
        print("\nLaeufe ohne Manifest: Konfiguration 'unbekannt', werden nicht gepoolt.")


if __name__ == "__main__":
    main()
