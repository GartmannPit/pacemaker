"""Schaetzt die Kosten pro Gespraechsminute aus einem Gespraechslauf (Muss-Kriterium Kosten).

    uv run python -m pacemaker_agent.metrics.costs experiments/runs/t1-gespraech

Verbrauch aus dem Pipecat-Log des Laufs (*.log im Ordner: STT-Audiosekunden, LLM-Tokens,
TTS-Zeichen), Gespraechsdauer aus events/*.json. Preise: Azure-Listenpreise (Retail Prices
API, Pay-as-you-go, USD, abgerufen 2026-10-08), Stack A aus Drittquellen (nicht verifiziert).

Grenzen: Gecachte Tokens stehen nicht im Log -> LLM ohne Cache-Rabatt (Obergrenze). Azure-STT
rechnet gestreamtes Audio ab; die Pipeline streamt das Mikrofon das ganze Gespraech lang ->
STT nach Gespraechsdauer (Obergrenze) und nach gemessener Sprachdauer (Untergrenze).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from .collector import _REPO_ROOT

# USD. Quelle Azure: prices.azure.com, germanywestcentral (Speech) / swedencentral (OpenAI).
PRICES = {
    "azure_stt_per_hour": 1.00,  # S1 Speech To Text
    "azure_tts_per_1m_chars": 15.00,  # S1 Neural Text To Speech
    "gpt-4.1-nano": {"in": 0.11, "out": 0.44},  # Data Zone, je 1M Tokens
    "gpt-4.1-mini": {"in": 0.44, "out": 1.76},  # Data Zone, je 1M Tokens
    # Stack A (US-Referenz, nie Produkt): Drittquellen, Stand 2026-10
    "deepgram_nova3_per_min": 0.0077,
    "openai_gpt41mini": {"in": 0.40, "out": 1.60},
    "elevenlabs_flash_per_1k_chars": 0.05,
}

_STT = re.compile(r"STTService#\d+ usage audio seconds: ([\d.]+)")
_LLM = re.compile(r"LLMService#\d+ prompt tokens: (\d+), completion tokens: (\d+)")
_TTS = re.compile(r"TTSService#\d+ usage characters: (\d+)")


def usage(runs_dir: Path) -> dict:
    stt = prompt = completion = chars = 0.0
    for log in runs_dir.glob("*.log"):
        text = log.read_text(encoding="utf-8", errors="replace")
        stt += sum(float(x) for x in _STT.findall(text))
        for p, c in _LLM.findall(text):
            prompt += int(p)
            completion += int(c)
        chars += sum(int(x) for x in _TTS.findall(text))
    minutes = 0.0
    for ev_path in (runs_dir / "events").glob("*.json"):
        ev = json.loads(ev_path.read_text(encoding="utf-8"))
        starts = [c["voice_start"] for c in ev["clips"] if c["voice_start"]]
        ends = [c["voice_end"] for c in ev["clips"] if c["voice_end"]]
        ends += [t for kind, t in ev["bot_speaking"] if kind == "stop"]
        if starts and ends:
            minutes += (max(ends) - min(starts) + 1.0) / 60  # +1 s Vorlauf
    return {
        "minutes": minutes,
        "stt_speech_secs": stt,
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "tts_chars": chars,
    }


def per_minute(u: dict, model: str) -> dict:
    m = u["minutes"]
    llm = PRICES[model]
    stt_upper = PRICES["azure_stt_per_hour"] / 60
    stt_lower = u["stt_speech_secs"] / 3600 * PRICES["azure_stt_per_hour"] / m
    llm_cost = (u["prompt_tokens"] * llm["in"] + u["completion_tokens"] * llm["out"]) / 1e6 / m
    tts = u["tts_chars"] * PRICES["azure_tts_per_1m_chars"] / 1e6 / m
    stack_a = {
        "stt": PRICES["deepgram_nova3_per_min"],
        "llm": (
            u["prompt_tokens"] * PRICES["openai_gpt41mini"]["in"]
            + u["completion_tokens"] * PRICES["openai_gpt41mini"]["out"]
        )
        / 1e6
        / m,
        "tts": u["tts_chars"] / 1000 * PRICES["elevenlabs_flash_per_1k_chars"] / m,
    }
    return {
        "stt_lower": stt_lower,
        "stt_upper": stt_upper,
        "llm": llm_cost,
        "tts": tts,
        "total_upper": stt_upper + llm_cost + tts,
        "stack_a": stack_a,
        "stack_a_total": sum(stack_a.values()),
    }


def main() -> None:
    runs_dir = Path(sys.argv[1])
    if not runs_dir.is_absolute():
        runs_dir = _REPO_ROOT / runs_dir
    model = sys.argv[2] if len(sys.argv) > 2 else "gpt-4.1-nano"
    u = usage(runs_dir)
    if not u["minutes"]:
        raise SystemExit(f"Keine Gespraechsdauer aus {runs_dir}/events ermittelbar.")
    print(
        f"Verbrauch: {u['minutes']:.1f} Gespraechsminuten, "
        f"STT-Sprache {u['stt_speech_secs']:.0f} s, "
        f"{u['prompt_tokens']:.0f} Prompt-/{u['completion_tokens']:.0f} Completion-Tokens, "
        f"{u['tts_chars']:.0f} TTS-Zeichen"
    )
    print(
        f"je Minute: {u['prompt_tokens'] / u['minutes']:.0f} Prompt-Tokens, "
        f"{u['completion_tokens'] / u['minutes']:.0f} Completion-Tokens, "
        f"{u['tts_chars'] / u['minutes']:.0f} TTS-Zeichen"
    )
    for mdl in (model, "gpt-4.1-mini") if model != "gpt-4.1-mini" else (model,):
        c = per_minute(u, mdl)
        print(
            f"azure-eu/{mdl}: STT {c['stt_lower']:.4f}-{c['stt_upper']:.4f} $ · "
            f"LLM {c['llm']:.4f} $ · TTS {c['tts']:.4f} $ · "
            f"gesamt bis {c['total_upper']:.4f} $/Min."
        )
    a = per_minute(u, model)
    print(
        f"Stack A (Referenz, gleicher Verbrauch): STT {a['stack_a']['stt']:.4f} $ · LLM "
        f"{a['stack_a']['llm']:.4f} $ · TTS {a['stack_a']['tts']:.4f} $ · gesamt "
        f"{a['stack_a_total']:.4f} $/Min."
    )


if __name__ == "__main__":
    main()
