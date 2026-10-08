"""Run-Manifest: haelt fest, mit welcher Konfiguration ein Messlauf entstanden ist.

Grund (2026-10-07): Die Auswertung konnte Laeufe nur nach Stack und Modell trennen;
Filtermodus, Segmentierung, Prompt-Version, Aufwaermen usw. wurden per Hand sortiert.
Ein Manifest je Lauf macht Laeufe vergleichbar und verhindert, dass unterschiedliche
Konfigurationen zusammen ausgewertet werden.

Ablage: experiments/runs/manifests/<run_id>.json (Unterordner, damit aggregate.py sie
nicht als Messdatei liest). `config_hash` fasst alle Einstellungen zusammen, die das
Ergebnis beeinflussen koennen; nur Laeufe mit gleichem Hash werden gepoolt.
"""

from __future__ import annotations

import hashlib
import json
import platform
import socket
import subprocess
from dataclasses import asdict
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from ..config import TuningConfig
from .collector import _REPO_ROOT, RUNS_DIR

MANIFEST_DIR = RUNS_DIR / "manifests"
_FIXTURES = _REPO_ROOT / "agent" / "fixtures" / "audio"


def new_run_id(stack: str) -> str:
    return f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{stack}"


def manifest_path(run_id: str) -> Path:
    return MANIFEST_DIR / f"{run_id}.json"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:12]


def _git_revision() -> dict[str, Any]:
    try:
        rev = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        return {"revision": rev, "dirty": bool(dirty)}
    except (OSError, subprocess.CalledProcessError):
        return {"revision": "unbekannt", "dirty": None}


def _package_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return "unbekannt"


def _fixtures_hash() -> str:
    clips = sorted(_FIXTURES.glob("*.wav"))
    if not clips:
        return "keine"
    h = hashlib.sha256()
    for clip in clips:
        h.update(clip.name.encode())
        h.update(clip.read_bytes())
    return h.hexdigest()[:12]


def write_manifest(
    run_id: str,
    *,
    stack: str,
    llm_model: str,
    tuning: TuningConfig,
    system_prompt: str,
    extra: dict[str, Any] | None = None,
) -> Path:
    """Schreibt das Manifest beim Aufbau der Pipeline (vor dem ersten Turn)."""
    config = {
        "stack": stack,
        "llm_model": llm_model,
        **asdict(tuning),
        "prompt_sha": _sha(system_prompt.encode()),
        "fixtures_sha": _fixtures_hash(),
        **(extra or {}),
    }
    manifest = {
        "run_id": run_id,
        "started": datetime.now(UTC).isoformat(),
        "device": socket.gethostname(),
        "git": _git_revision(),
        "versions": {
            "pipecat": _package_version("pipecat-ai"),
            "python": platform.python_version(),
        },
        "config": config,
        "config_hash": _sha(json.dumps(config, sort_keys=True).encode()),
    }
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    path = manifest_path(run_id)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def update_manifest(run_id: str, **sections: Any) -> None:
    """Ergaenzt Abschnitte nach dem Lauf (z. B. Ergebnisbilanz, beobachteter Filtermodus)."""
    path = manifest_path(run_id)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest.update(sections)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def load_manifest(run_id: str) -> dict[str, Any] | None:
    path = manifest_path(run_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
