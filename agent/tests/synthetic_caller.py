"""Synthetic Caller: spielt vordefinierte deutsche Audio-Clips durch die Pipeline
und misst die E2E-Antwortzeit pro Turn -- reproduzierbare Latenzverteilung statt
Handstoppen.

STATUS: Geruest. Umsetzung in Woche 2 (Phase-0-Plan §3, Schritt 8).

Geplantes Vorgehen:
  1. fixtures/audio/*.wav der Reihe nach in transport.input() einspeisen
  2. Zeit messen: "VAD erkennt Clip-Ende" -> "erster ausgehender TTS-Audioframe"
  3. pro Turn MetricsCollector.record_turn(e2e_ms=..., stt_final_ms=..., ...)
  4. --turns wiederholt die Clip-Sequenz fuer eine belastbare Verteilung
  5. am Ende den Pfad der JSONL ausgeben -> metrics/aggregate.py
"""

from __future__ import annotations

import argparse
from pathlib import Path

from pacemaker_agent.stacks import STACKS

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "audio"


def main() -> None:
    parser = argparse.ArgumentParser(prog="synthetic-caller")
    parser.add_argument("--stack", default="azure-eu", choices=STACKS)
    parser.add_argument("--turns", type=int, default=30)
    parser.parse_args()

    clips = sorted(FIXTURES.glob("*.wav"))
    if not clips:
        raise SystemExit(
            f"Keine WAV-Clips in {FIXTURES}. 8-12 kurze deutsche Kaltakquise-"
            f"Aeusserungen ablegen (z.B. per Azure TTS erzeugt), dann erneut starten."
        )
    raise SystemExit("Synthetic Caller noch nicht implementiert -- siehe Modul-Docstring.")


if __name__ == "__main__":
    main()
