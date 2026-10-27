"""Lasttest nach docs/phase-1-lasttest.md, ohne Dienste oder neue Abhaengigkeiten.

Aufruf: python -m pacemaker_agent.metrics.load_aggregate <Reihenordner>
Ausgabe: JSON mit Grundgesamtheit, Ausschluessen und Urteil je Stufe.
--check-block <Blockordner> liefert die Abbruchbilanz fuer infra/lasttest.sh.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import mean

from .aggregate import quantile

LATENCY_STATUSES = {"beantwortet", "zerfallen", "abgebrochen"}


def _jsonl(path: Path) -> list[dict]:
    return (
        [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        if path.exists()
        else []
    )


def _json(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


def _stats(values: list[float]) -> dict:
    return {"n": len(values), "p50_ms": quantile(values, 0.5), "p90_ms": quantile(values, 0.9)}


def cpu_values(path: Path) -> list[float]:
    """vmstat: erste Datenzeile ist seit Boot gemittelt und zaehlt nicht zum Block."""
    columns = []
    values = []
    first = True
    if not path.exists():
        return values
    for line in path.read_text().splitlines():
        cells = line.split()
        if "us" in cells and "sy" in cells and "id" in cells:
            columns = cells
            continue
        if not columns or len(cells) != len(columns):
            continue
        try:
            row = dict(zip(columns, map(float, cells), strict=True))
        except ValueError:
            continue
        if first:
            first = False
            continue
        values.append(row["us"] + row["sy"] + row.get("st", 0))
    return values


def block_health(path: Path) -> dict:
    """Dienstfehler je Sitzung zaehlen; fehlende Protokolle bleiben unvollstaendig."""
    plan = _json(path / "block.json")
    paths = sorted((path / "manifests").glob("*.json"))
    manifests = [_json(p) for p in paths]
    errors = sum(
        bool(m.get("service_errors"))
        or any(t.get("errors") for t in _jsonl(path / "turns" / f"{m['run_id']}.jsonl"))
        for m in manifests
    )
    exits = _jsonl(path / "callers.jsonl")
    expected = plan.get("callers", 0)
    complete = (
        expected > 0
        and len(manifests) == expected
        and len(exits) == expected
        and all(e["exit_code"] == 0 for e in exits)
        and {e.get("caller") for e in exits} == set(range(1, expected + 1))
        and {m.get("config", {}).get("load_caller") for m in manifests}
        == set(range(1, expected + 1))
        and all(m.get("config", {}).get("load_concurrency") == expected for m in manifests)
        and all(p.stem == m.get("run_id") for p, m in zip(paths, manifests, strict=True))
        and all(
            (m.get("session_complete") or m.get("service_errors")) and not m.get("harness_error")
            for m in manifests
        )
        and all(
            m.get("finished")
            and (path / "turns" / f"{m['run_id']}.jsonl").exists()
            and (
                m.get("service_errors")
                or m.get("hung_up")
                or len(_jsonl(path / "turns" / f"{m['run_id']}.jsonl")) == plan.get("turns")
            )
            for m in manifests
        )
        and bool(cpu_values(path / "vmstat.log"))
    )
    return {"service_error_sessions": errors, "complete": complete, "sessions": len(manifests)}


def _server_latency(turn: dict, next_start: float, diag: list[dict]) -> float | None:
    end = turn.get("speech_end_clip")
    if end is None:
        return None
    arrival = next(
        (
            r["t"]
            for r in diag
            if r.get("art") == "audio" and not r.get("still", True) and end <= r["t"] < next_start
        ),
        None,
    )
    return (arrival - end) * 1000 if arrival is not None else None


def _usage(rows: list[dict]) -> dict:
    # Sekunden sind kumulativ, niemals aufsummieren. Tokens des Backends separat halten.
    seconds = [
        r["usage"]["seconds"]
        for r in rows
        if r.get("source") == "live"
        and isinstance(r.get("usage"), dict)
        and r["usage"].get("seconds") is not None
    ]
    backend = []
    seen = set()
    for index, row in enumerate(rows):
        if row.get("source") != "backend" or row.get("type") != "response.completed":
            continue
        key = row.get("response_id") or row.get("event_id") or index
        usage = row.get("usage") or {}
        if key not in seen and usage.get("total_tokens") is not None:
            seen.add(key)
            backend.append({"t": row["t"], "tokens": usage["total_tokens"]})
    return {
        "live_seconds": max(seconds) if seconds else None,
        "live_tokens": None,
        "live_tokens_per_conversation_minute": None,
        "backend_token_events": backend,
        "backend_tokens": sum(r["tokens"] for r in backend) if backend else None,
        "rate_limit_events": sum("rate_limit" in (r.get("type") or "") for r in rows),
    }


def _peak(events: list[dict]) -> int | None:
    if not events:
        return None
    return max(
        sum(e["tokens"] for e in events if end - 60 < e["t"] <= end)
        for end in (e["t"] for e in events)
    )


def aggregate(root: Path) -> dict:
    """Poolt die E-Bloecke derselben Reihe; Funktionstests bleiben ausgeschlossen."""
    plans = sorted(root.glob("*/block.json"))
    if (root / "block.json").exists():
        plans = [root / "block.json"]
    stages: dict[str, dict] = {}
    fingerprints = set()
    blocks = []
    for plan_path in plans:
        plan = _json(plan_path)
        if plan.get("mode") != "reihe":
            continue
        path = plan_path.parent
        stage = plan["stage"]
        data = stages.setdefault(
            stage,
            {
                "sessions": 0,
                "offered": 0,
                "status_counts": Counter(),
                "warm_status_counts": Counter(),
                "excluded_status": Counter(),
                "cold_status_counts": Counter(),
                "cold_agent": [],
                "cold_server": [],
                "agent": [],
                "server": [],
                "cpu": [],
                "blocks": [],
                "session_usage": [],
                "missing_latency": 0,
                "missing_server": 0,
                "service_error_sessions": 0,
            },
        )
        health = block_health(path)
        cpu = cpu_values(path / "vmstat.log")
        block = {
            "block": path.name,
            "stage": stage,
            **health,
            "cpu_mean_percent": mean(cpu) if cpu else None,
            "cpu_max_percent": max(cpu) if cpu else None,
        }
        blocks.append(block)
        data["blocks"].append(block)
        data["cpu"].extend(cpu)
        data["service_error_sessions"] += health["service_error_sessions"]
        for manifest_path in sorted((path / "manifests").glob("*.json")):
            manifest = _json(manifest_path)
            config = manifest["config"]
            # Last- und Sitzungsnummern unterscheiden sich absichtlich; Kernkonfiguration nicht.
            fingerprint = {
                k: v
                for k, v in config.items()
                if k not in {"load_concurrency", "load_caller", "repeat", "call", "clip_offset"}
            }
            fingerprints.add(
                json.dumps(
                    {
                        "config": fingerprint,
                        "git": manifest.get("git"),
                        "versions": manifest.get("versions"),
                        "device": manifest.get("device"),
                    },
                    sort_keys=True,
                )
            )
            run_id = manifest["run_id"]
            turns = _jsonl(path / "turns" / f"{run_id}.jsonl")
            diag = sorted(_jsonl(path / "live_diag" / f"{run_id}.jsonl"), key=lambda r: r["t"])
            data["sessions"] += 1
            for i, turn in enumerate(turns):
                status = turn["status"]
                data["offered"] += 1
                data["status_counts"][status] += 1
                next_start = (
                    turns[i + 1].get("window_start", float("inf"))
                    if i + 1 < len(turns)
                    else datetime.fromisoformat(manifest["finished"]).timestamp()
                    if manifest.get("finished")
                    else float("inf")
                )
                server = _server_latency(turn, next_start, diag)
                value = turn.get("first_audio_after_clip_ms")
                if turn["utterance_id"] == 1:
                    data["cold_status_counts"][status] += 1
                    if value is not None:
                        data["cold_agent"].append(value)
                    if server is not None:
                        data["cold_server"].append(server)
                    continue
                data["warm_status_counts"][status] += 1
                if status not in LATENCY_STATUSES:
                    data["excluded_status"][status] += 1
                    continue
                if value is not None:
                    data["agent"].append(value)
                else:
                    data["missing_latency"] += 1
                if server is not None:
                    data["server"].append(server)
                else:
                    data["missing_server"] += 1
            usage = _usage(_jsonl(path / "live_usage" / f"{run_id}.jsonl"))
            duration = (
                (
                    datetime.fromisoformat(manifest["finished"])
                    - datetime.fromisoformat(manifest["started"])
                ).total_seconds()
                if manifest.get("finished")
                else None
            )
            usage.update(
                run_id=run_id,
                session_seconds=duration,
                backend_tokens_per_conversation_minute=usage["backend_tokens"] / (duration / 60)
                if usage["backend_tokens"] is not None and duration
                else None,
            )
            data["session_usage"].append(usage)
    baseline = _stats(stages.get("E", {}).get("agent", []))
    server_baseline = _stats(stages.get("E", {}).get("server", []))
    comparable = len(fingerprints) == 1
    baseline_complete = len([b for b in blocks if b["stage"] == "E"]) >= 3 and all(
        b["complete"] and not b["service_error_sessions"] for b in blocks if b["stage"] == "E"
    )
    result = {}
    for stage, data in stages.items():
        agent, server = _stats(data["agent"]), _stats(data["server"])
        ratios = {
            q: agent[q] / baseline[q] if baseline[q] and agent[q] is not None else None
            for q in ("p50_ms", "p90_ms")
        }
        server_ratios = {
            q: server[q] / server_baseline[q]
            if server_baseline[q] and server[q] is not None
            else None
            for q in ("p50_ms", "p90_ms")
        }
        vm_limited = any(
            b["cpu_mean_percent"] is not None and b["cpu_mean_percent"] > 85 for b in data["blocks"]
        )
        complete = all(b["complete"] and b["cpu_mean_percent"] is not None for b in data["blocks"])
        ratio = ratios["p90_ms"]
        if stage == "E":
            verdict = "Referenz"
        elif vm_limited:
            verdict = "VM-begrenzt"
        elif data["service_error_sessions"]:
            verdict = "nicht bestanden"
        elif (
            not complete
            or not comparable
            or not baseline_complete
            or ratio is None
            or data["missing_latency"]
            or data["excluded_status"]
        ):
            verdict = "unklar"
        elif 1.1 <= ratio <= 1.3:
            verdict = "unklar"
        else:
            verdict = "bestanden" if ratio <= 1.2 else "nicht bestanden"
        events = [e for s in data["session_usage"] for e in s["backend_token_events"]]
        backend_sessions = [
            s
            for s in data["session_usage"]
            if s["backend_tokens"] is not None and s["session_seconds"]
        ]
        backend_minutes = sum(s["session_seconds"] for s in backend_sessions) / 60
        result[stage] = {
            "sessions": data["sessions"],
            "offered": data["offered"],
            "status_counts": dict(data["status_counts"]),
            "status_rates": {k: v / data["offered"] for k, v in data["status_counts"].items()},
            "warm_status_counts": dict(data["warm_status_counts"]),
            "excluded": {
                "cold_start": sum(data["cold_status_counts"].values()),
                "status": dict(data["excluded_status"]),
                "missing_latency": data["missing_latency"],
            },
            "cold_start": {
                "status_counts": dict(data["cold_status_counts"]),
                "agent": _stats(data["cold_agent"]),
                "server": _stats(data["cold_server"]),
            },
            "service_error_sessions": data["service_error_sessions"],
            "answered": data["status_counts"]["beantwortet"],
            "agent": agent,
            "server": server,
            "missing_server_audio": data["missing_server"],
            "ratio_to_E": ratios,
            "server_ratio_to_E": server_ratios,
            "cpu_mean_percent": mean(data["cpu"]) if data["cpu"] else None,
            "cpu_max_percent": max(data["cpu"]) if data["cpu"] else None,
            "vm_limited": vm_limited,
            "complete": complete,
            "criteria": {
                "no_service_errors": data["service_error_sessions"] == 0,
                "p90_within_20_percent": ratio <= 1.2 if ratio is not None else None,
            },
            "usage": data["session_usage"],
            "live_peak_tpm": None,
            "live_tokens_per_conversation_minute": None,
            "backend_usage_sessions": len(backend_sessions),
            "backend_tokens_per_conversation_minute": (
                sum(s["backend_tokens"] for s in backend_sessions) / backend_minutes
                if backend_minutes
                else None
            ),
            "backend_peak_tpm": _peak(events),
            "verdict": verdict,
        }
    return {
        "stages": result,
        "blocks": blocks,
        "comparable": comparable,
        "missing_stages": sorted({"E", "L5", "L10", "L20"} - set(stages)),
        "usage_note": (
            "Pipecat 1.12: Live-Usage in kumulativen Sekunden; keine Live-Tokens/TPM. "
            "Backend-Tokens separat. OpenAI-Konsole nach Funktionstest ablesen."
        ),
        "latency_note": (
            "Agent-Ausgabe, keine Browser-E2E. zerfallen/abgebrochen mit gueltigem Wert "
            "enthalten; erster Clip je Sitzung ausgeschlossen. "
            "Orientierende Quantile; 1,1–1,3 = unklar."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--check-block", action="store_true")
    args = parser.parse_args()
    report = block_health(args.root) if args.check_block else aggregate(args.root)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
