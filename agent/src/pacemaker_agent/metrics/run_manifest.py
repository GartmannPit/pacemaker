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
import os
import platform
import socket
import subprocess
from dataclasses import asdict
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any
from uuid import uuid4

from ..config import TuningConfig
from .collector import _REPO_ROOT, RUNS_DIR

MANIFEST_DIR = RUNS_DIR / "manifests"
_FIXTURES = _REPO_ROOT / "agent" / "fixtures" / "audio"


def new_run_id(stack: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    return f"{stamp}-{os.getpid()}-{uuid4().hex}-{stack}"


def load_config() -> dict[str, int | None]:
    """Last-Metadaten validieren; normale Einzelmessungen behalten leere Felder."""
    names = ("PACEMAKER_LOAD_CONCURRENCY", "PACEMAKER_LOAD_CALLER")
    values = [os.environ.get(name) for name in names]
    if not any(values):
        return {"load_concurrency": None, "load_caller": None}
    try:
        concurrency, caller = (int(value or "") for value in values)
    except ValueError as exc:
        raise ValueError("Beide PACEMAKER_LOAD_* muessen positive Ganzzahlen sein") from exc
    if not 1 <= caller <= concurrency:
        raise ValueError("Last-Anrufer muss zwischen 1 und load_concurrency liegen")
    return {"load_concurrency": concurrency, "load_caller": caller}


def manifest_path(run_id: str) -> Path:
    return MANIFEST_DIR / f"{run_id}.json"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:12]


def _write_json(path: Path, value: dict) -> None:
    """Ein hart beendeter Anrufer darf kein halb geschriebenes Manifest hinterlassen."""
    temporary = None
    try:
        with NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False
        ) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, ensure_ascii=False, indent=2)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


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
        **load_config(),
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
    _write_json(path, manifest)
    return path


def update_manifest(run_id: str, **sections: Any) -> None:
    """Ergaenzt Abschnitte nach dem Lauf (z. B. Ergebnisbilanz, beobachteter Filtermodus)."""
    path = manifest_path(run_id)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest.update(sections)
    _write_json(path, manifest)


def load_manifest(run_id: str) -> dict[str, Any] | None:
    path = manifest_path(run_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
