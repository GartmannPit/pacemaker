"""Simulation: Was braechte es, Audio nach dem Turn-Ende zurueckzuhalten (Codex-Vorschlag)?

    uv run python -m pacemaker_agent.metrics.hold_simulation

Idee (Prototyp-Kandidat, docs/phase-0-ergebnisse.md): Nach Smart Turns "fertig" laufen LLM
und TTS wie heute, das Audio wird aber erst freigegeben, wenn seit dem Turn-Ende H Sekunden
vergangen sind und der Nutzer nicht weitergesprochen hat; sonst wird der Kandidat verworfen.

Grundlage sind die Robustheitsreihen mit Referenzkonfiguration (Segmentierung 100 ms,
VAD-Stopp 0,2 s, VAD-Start 0,2 s, Mindestlautstaerke 0,6) -- keine neuen Messungen:
- vorzeitiges Turn-Ende und erstes Audio je Sitzung aus dem Turn-Protokoll (relativ zum
  hoerbaren Clip-Ende),
- Beginn der Fortsetzung aus der Aufnahme: erster hoerbarer 10-ms-Frame nach dem Turn-Ende
  (Energie wie im Testtreiber; keine Stimm- oder Prosodieauswertung),
- Erkennungszeit einer Fortsetzung: hoerbarer Beginn -> Unterbrechung, gemessen in T2 (§19).

Je Wartefrist H:
- zerfallene Sitzungen: Audio vor Fortsetzung, wenn die Freigabe max(erstes Audio,
  Turn-Ende + H) vor der Erkennung der Fortsetzung liegt (sonst wird verworfen),
- nicht zerfallene Sitzungen: neues erstes Audio = max(erstes Audio, Turn-Ende + H).
Variante "Textregel": Wartefrist nur, wenn der erkannte Text auf ein offenes Wort endet.

Vereinfachungen: nur die erste vorzeitige Grenze je Sitzung; Folgegrenzen (R12, S01) nicht
simuliert. Die Fortsetzung wird als erkannt angenommen, sobald die VAD sie bestaetigt.
"""

from __future__ import annotations

import json
import re
import wave

from ..tests.synthetic_transport import SAMPLE_RATE, _voiced_frames, last_voiced_sample
from .aggregate import quantile
from .collector import _REPO_ROOT

RUNS = _REPO_ROOT / "experiments" / "runs"
FIXTURES = _REPO_ROOT / "agent" / "fixtures" / "robust"
REFERENCE = {"stt_segmentation_ms": 100, "vad_stop_secs": 0.2}
HOLDS = [0.0, 0.3, 0.5, 0.8, 1.0, 1.5, 2.0]
# Hoerbarer Beginn -> Unterbrechung bei VAD-Start 0,2 s (T2, R23+R24, p50 469 ms; §19)
DETECT_SECS = 0.47

# Schmale Textregel: Fragment endet auf ein Wort, nach dem ein deutscher Satz fast nie endet
OPEN_WORDS = {
    "und",
    "aber",
    "oder",
    "also",
    "dann",
    "dass",
    "weil",
    "wenn",
    "ob",
    "wie",
    "auf",
    "mit",
    "von",
    "zu",
    "für",
    "in",
    "an",
    "bei",
    "über",
    "der",
    "die",
    "das",
    "den",
    "dem",
    "des",
    "ein",
    "eine",
    "einen",
    "einem",
    "ihr",
    "ihre",
    "ihren",
    "sein",
    "seine",
    "äh",
    "ähm",
    "eben",
    "ja",
    "sondern",
    "nicht",
    "sowie",
    "damit",
    "bevor",
    "nachdem",
    "als",
}


def _ends_open(text: str) -> bool:
    words = re.findall(r"[a-zäöüß]+", text.lower())
    return bool(words) and words[-1] in OPEN_WORDS


def _voiced_after(clip: str, t_file: float) -> float | None:
    """Erster hoerbarer Zeitpunkt (s, Dateizeit) nach t_file."""
    with wave.open(str(FIXTURES / f"{clip}.wav"), "rb") as w:
        pcm = w.readframes(w.getnframes())
    voiced, step = _voiced_frames(pcm, 10)
    for i in voiced:
        if i * step / SAMPLE_RATE > t_file + 0.05:  # Halbe Wortenden nicht als Fortsetzung
            return i * step / SAMPLE_RATE
    return None


def _clip_end(clip: str) -> float:
    with wave.open(str(FIXTURES / f"{clip}.wav"), "rb") as w:
        pcm = w.readframes(w.getnframes())
    return last_voiced_sample(pcm) / SAMPLE_RATE


def _sessions() -> list[dict]:
    out = []
    for series in ("robust", "robust-vad", "robust-vadstart"):
        d = RUNS / series
        for m in sorted((d / "manifests").glob("*.json")):
            man = json.loads(m.read_text(encoding="utf-8"))
            cfg = man["config"]
            if cfg.get("clip") is None or any(cfg.get(k) != v for k, v in REFERENCE.items()):
                continue
            if cfg.get("vad_start_secs", 0.2) != 0.2 or cfg.get("vad_min_volume", 0.6) != 0.6:
                continue
            tp = d / "turns" / f"{man['run_id']}.jsonl"
            tr = d / "transcripts" / f"{man['run_id']}.jsonl"
            if not tp.exists():
                continue
            turn = json.loads(tp.read_text(encoding="utf-8").splitlines()[0])
            users = []
            if tr.exists():
                users = [
                    json.loads(x)["text"]
                    for x in tr.read_text(encoding="utf-8").splitlines()
                    if x.strip() and json.loads(x)["role"] == "user"
                ]
            out.append({"clip": cfg["clip"], "turn": turn, "first_text": users[0] if users else ""})
    return out


def main() -> None:
    sessions = _sessions()
    split, whole = [], []
    for s in sessions:
        t = s["turn"]
        if t["turn_end_ms"] is None or t["first_audio_ms"] is None:
            continue  # ohne VAD-Basis (R19) bzw. ohne Audio: nicht simulierbar
        if t["status"] == "zerfallen":
            if t.get("first_audio_from_clip_ms") is None:
                continue
            clip_end = _clip_end(s["clip"])
            fa_file = clip_end + t["first_audio_from_clip_ms"] / 1000
            te_file = fa_file - (t["first_audio_ms"] - t["turn_end_ms"]) / 1000
            onset = _voiced_after(s["clip"], te_file)
            if onset is None:
                continue
            split.append(
                {
                    "clip": s["clip"],
                    "te": te_file,
                    "fa": fa_file,
                    "detect": onset + DETECT_SECS,
                    "gap": onset - te_file,
                    "open": _ends_open(s["first_text"]),
                }
            )
        else:
            whole.append(
                {
                    "te": t["turn_end_ms"] / 1000,
                    "fa": t["first_audio_ms"] / 1000,
                    "open": _ends_open(s["first_text"]),
                }
            )

    gaps = sorted(round(x["gap"], 2) for x in split)
    print(
        f"Referenzkonfiguration: {len(sessions)} Sitzungen, simulierbar {len(split)} zerfallen "
        f"+ {len(whole)} nicht zerfallen"
    )
    print(
        f"Abstand vorzeitiges Turn-Ende -> Beginn Fortsetzung (s): p10 {quantile(gaps, 0.1):.2f} "
        f"· p50 {quantile(gaps, 0.5):.2f} · p90 {quantile(gaps, 0.9):.2f}"
    )
    open_split = sum(x["open"] for x in split)
    open_whole = sum(x["open"] for x in whole)
    print(
        f"Textregel 'endet offen': {open_split}/{len(split)} zerfallene, "
        f"{open_whole}/{len(whole)} nicht zerfallene Sitzungen\n"
    )
    print(f"{'H (s)':>5s} | {'immer zurueckhalten':^40s} | {'nur bei offenem Text':^40s}")
    print(
        f"{'':>5s} | {'Audio vor Forts.':>16s} {'erstes Audio p50/p90':>22s} | "
        f"{'Audio vor Forts.':>16s} {'erstes Audio p50/p90':>22s}"
    )
    for h in HOLDS:
        cols = []
        for text_rule in (False, True):
            holds = [h if (not text_rule or x["open"]) else 0.0 for x in split]
            early = sum(
                max(x["fa"], x["te"] + d) < x["detect"] for x, d in zip(split, holds, strict=True)
            )
            lat = sorted(
                max(x["fa"], x["te"] + (h if (not text_rule or x["open"]) else 0.0)) * 1000
                for x in whole
            )
            p50, p90 = quantile(lat, 0.5), quantile(lat, 0.9)
            cols.append(f"{early:>7d} / {len(split):<6d} {p50:>10.0f} / {p90:<9.0f}")
        print(f"{h:>5.1f} | {cols[0]:>40s} | {cols[1]:>40s}")


if __name__ == "__main__":
    main()
