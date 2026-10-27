"""Hybrid-Protokolle lokal als Markdown auswerten, ohne Transkripttexte auszugeben.

Aufruf aus agent/: uv run python tools/gptlive_browser/auswertung.py <ordner>
Importiert weder Server noch Sideband und liest ausschließlich JSONL im angegebenen Ordner.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

TOKEN_FIELDS = ("input_tokens", "output_tokens", "total_tokens")
ROLES = (("user", "nutzer"), ("assistant", "persona"))


def read_rows(path: Path) -> tuple[list[dict[str, Any]], int]:
    """Fehlende Dateien und defekte Zeilen ohne Ausgabe ihrer Inhalte behandeln."""
    rows = []
    invalid = 0
    try:
        with path.open(encoding="utf-8", errors="replace") as stream:
            for line in stream:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    invalid += 1
                    continue
                if isinstance(row, dict):
                    rows.append(row)
                else:
                    invalid += 1
    except OSError:
        invalid += 1
    return rows, invalid


def timestamp(value: Any) -> float | None:
    """Nur absolute ISO-Zeitstempel mit Zeitzone für Reihenfolge und Abstand nutzen."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.timestamp() if parsed.tzinfo is not None else None
    except (ValueError, OverflowError, OSError):
        return None


def number(value: Any) -> float | None:
    if type(value) not in (int, float):
        return None
    try:
        return float(value) if math.isfinite(value) and value >= 0 else None
    except OverflowError:
        return None


def cell(value: Any) -> str:
    """Nur skalare Metadaten ausgeben; Markdown-Zeilen und Tabellen schützen."""
    if value is None:
        return "unbekannt"
    if isinstance(value, bool):
        return str(value).lower()
    if not isinstance(value, (str, int, float)):
        return "unbekannt"
    return (
        str(value).replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ").replace("\r", " ")
    )


def compare(sideband: str, browser: str) -> str:
    """Mehr = zusätzliche Zeichen bei erhaltener Reihenfolge der anderen Quelle."""
    if sideband == browser:
        return "gleich"

    def subsequence(short: str, long: str) -> bool:
        remaining = iter(long)
        return all(any(c == candidate for candidate in remaining) for c in short)

    if len(sideband) > len(browser) and subsequence(browser, sideband):
        return "Sideband hat mehr"
    if len(browser) > len(sideband) and subsequence(sideband, browser):
        return "Browser hat mehr"
    return "abweichend"


def browser_texts(rows: list[dict[str, Any]]) -> dict[str, str]:
    """Überlappende Chunks nach seq deduplizieren, dann nach seq zusammensetzen."""
    unique: dict[int, dict[str, Any]] = {}
    for row in rows:
        deltas = row.get("deltas")
        if not isinstance(deltas, list):
            continue
        for delta in deltas:
            if (
                isinstance(delta, dict)
                and type(delta.get("seq")) is int
                and delta["seq"] >= 0
                and delta.get("rolle") in ("nutzer", "persona")
                and isinstance(delta.get("text"), str)
            ):
                unique.setdefault(delta["seq"], delta)
    return {
        role: "".join(d["text"] for _, d in sorted(unique.items()) if d["rolle"] == role)
        for _, role in ROLES
    }


def session_report(
    session_id: str,
    side: list[dict[str, Any]],
    browser: list[dict[str, Any]],
    server: list[dict[str, Any]],
    *,
    side_present: bool,
    browser_present: bool,
) -> tuple[list[str], float | None, dict[str, int]]:
    """Eine Sitzung auswerten; Abschlusswerte vor kumulativen Zwischenständen verwenden."""
    ended = [r for r in side if r.get("type") == "status" and r.get("status") == "beendet"]
    results = [r["result"] for r in server if isinstance(r.get("result"), dict)]
    sources = [r for r in side if r.get("type") == "usage"] + ended + results
    seconds = None
    tokens: dict[str, int] = {}
    for source in sources:
        value = number(source.get("usage_seconds"))
        if value is not None:
            seconds = value
        counts = source.get("backend_tokens")
        if isinstance(counts, dict):
            for key in TOKEN_FIELDS:
                if type(counts.get(key)) is int and counts[key] >= 0:
                    tokens[key] = counts[key]
    final = {}
    for source in ended + results:
        final.update({k: v for k, v in source.items() if v is not None})
    aborted = [r["start_abgebrochen"] for r in server if r.get("start_abgebrochen")]
    failures = [r["fehler"] for r in server if r.get("fehler")]
    reason = final.get("reason", "start_abgebrochen" if aborted else None)
    transcript_times = [
        t
        for r in side
        if r.get("type") == "transcript" and (t := timestamp(r.get("timestamp"))) is not None
    ]
    end_time = timestamp(ended[-1].get("timestamp")) if ended else None
    gap = end_time - max(transcript_times) if end_time is not None and transcript_times else None
    actions = [cell(r["debug"]) for r in server if "debug" in r]
    emergency = [cell(r["notschluss_extern"]) for r in server if "notschluss_extern" in r]
    diagnostics = final.get("diagnostics")
    diagnoses = [cell(d) for d in diagnostics] if isinstance(diagnostics, list) else []
    diagnoses += [cell(v) for v in aborted + failures]
    lines = [
        f"## Sitzung {cell(session_id)}",
        "",
        f"- Ende-Grund: {cell(reason)}; complete: {cell(final.get('complete'))}",
        f"- Dauer (usage_seconds): {seconds:.3f} s"
        if seconds is not None
        else "- Dauer (usage_seconds): unbekannt",
        f"- Abstand letztes Transkript → Ende (Sideband-Empfang): {gap:.3f} s"
        if gap is not None
        else "- Abstand letztes Transkript → Ende (Sideband-Empfang): unbekannt",
        f"- Debug-Aktionen: {', '.join(actions) or 'keine protokolliert'}",
        f"- notschluss_extern: {', '.join(emergency) or 'nicht protokolliert'}",
        f"- Diagnosen: {', '.join(diagnoses) or 'keine protokolliert'}",
        "",
        "| K1 Rolle | Vergleich | Zeichen Sideband | Zeichen Browser |",
        "|---|---|---:|---:|",
    ]
    texts = browser_texts(browser)
    for role, browser_role in ROLES:
        side_text = "".join(
            r["text"]
            for r in side
            if r.get("type") == "transcript"
            and r.get("role") == role
            and isinstance(r.get("text"), str)
        )
        browser_text = texts[browser_role]
        verdict = (
            compare(side_text, browser_text)
            if side_present and browser_present
            else "nicht prüfbar (Quelle fehlt)"
        )
        lines.append(f"| {role} | {verdict} | {len(side_text)} | {len(browser_text)} |")
    lines += [
        "",
        "Steuerereignisse:",
        "",
        "| Typ | eigen | Code | error_type | param |",
        "|---|---|---|---|---|",
    ]
    controls = [r for r in side if r.get("type") == "steuerereignis"]
    for row in controls:
        lines.append(
            "| "
            + " | ".join(
                cell(row.get(k)) for k in ("event", "eigen", "code", "error_type", "param")
            )
            + " |"
        )
    if not controls:
        lines.append("| keine protokolliert | – | – | – | – |")
    return lines, seconds, tokens


def report(folder: Path) -> str:
    """Sitzungen anhand absoluter Sideband-Zeitstempel chronologisch ausgeben."""
    server_rows, invalid = read_rows(folder / "sitzungen.jsonl")
    server: dict[str, list[dict[str, Any]]] = {}
    for row in server_rows:
        if isinstance(row.get("session_id"), str):
            server.setdefault(row["session_id"], []).append(row)
    side = {}
    browser = {}
    for path in sorted(folder.glob("*.jsonl")):
        if path.name == "sitzungen.jsonl":
            continue
        rows, errors = read_rows(path)
        invalid += errors
        target = browser if path.stem.endswith("-browser") else side
        session_id = path.stem.removesuffix("-browser") if target is browser else path.stem
        target[session_id] = rows
    ids = set(side) | set(browser) | set(server)

    def order(session_id: str) -> tuple[float, str]:
        times = [
            t for r in side.get(session_id, []) if (t := timestamp(r.get("timestamp"))) is not None
        ]
        return min(times, default=math.inf), session_id

    lines = [
        "# Hybrid-Auswertung",
        "",
        "Chronologisch nach erstem Sideband-Zeitstempel; "
        "ohne Zeitstempel zuletzt nach Sitzungs-ID.",
        "K1 vergleicht Zeichenfolgen je Rolle in Reihenfolge (ohne Normalisierung). "
        "Mehr = zusätzliche Zeichen bei erhaltener Teilfolge; keine Aussage zur "
        "Transkriptionsrichtigkeit oder rollenübergreifenden Reihenfolge.",
        "Fehlende Quellen sind nicht prüfbar; leere vorhandene Quellen zählen als 0 Zeichen.",
        f"Nicht lesbare Dateien / ungültige Zeilen: {invalid}",
        "",
    ]
    seconds_total = 0.0
    known_seconds = 0
    tokens_total: dict[str, int] = {}
    for session_id in sorted(ids, key=order):
        section, seconds, tokens = session_report(
            session_id,
            side.get(session_id, []),
            browser.get(session_id, []),
            server.get(session_id, []),
            side_present=session_id in side,
            browser_present=session_id in browser,
        )
        lines += section + [""]
        if seconds is not None:
            seconds_total += seconds
            known_seconds += 1
        for key, value in tokens.items():
            tokens_total[key] = tokens_total.get(key, 0) + value
    lines += [
        "## Summen",
        "",
        f"- Sitzungen: {len(ids)}",
        f"- Live-Sekunden (bekannt): {seconds_total:.3f}; "
        f"ohne Verbrauchsangabe: {len(ids) - known_seconds}",
        f"- Kosten bei 0,05 $/Min. (bekannter Live-Verbrauch): {seconds_total / 60 * 0.05:.6f} $",
        "- Backend-Tokens (bekannt, separat; keine Backend-Kosten berechnet): "
        + (", ".join(f"{key}={value}" for key, value in tokens_total.items()) or "unbekannt"),
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ordner", type=Path)
    args = parser.parse_args()
    print(report(args.ordner), end="")


if __name__ == "__main__":
    main()
