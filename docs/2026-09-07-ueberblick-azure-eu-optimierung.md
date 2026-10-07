# Überblick: Azure-EU-Stack — Inbetriebnahme, Messkette, Latenz-Optimierung

**Zeitraum:** 2026-09-06 bis 2026-09-07
**Stack:** `azure-eu` (Azure AI Speech STT/TTS + Azure OpenAI `gpt-4.1-mini`), per Pipecat 1.8.1
**Zweck dieses Dokuments:** Orientierung über alles, was bisher an diesem Stack gemacht wurde —
mit Verweisen auf die Detail-Docs, nicht als deren Ersatz. Reihenfolge entspricht dem tatsächlichen
Ablauf, nicht einer thematischen Sortierung.

---

## 1. Stack lauffähig gemacht

Ausgangspunkt war ein Azure-OpenAI-Kontingent-Problem beim Anlegen des `gpt-4.1-mini`-Deployments.
Von dort bis zu einem stabil durchlaufenden Gespräch waren neun Probleme zu lösen, u. a.:

- Free-Trial-Subscription hat 0 Kontingent für neue Modelle → Upgrade auf Pay-As-You-Go
- Azure-AI-Foundry-"New Project"-Ressourcen sprechen nur die neue **v1-API** (`/openai/v1`), nicht
  die klassische datierte `api-version`-Route → `404`, bis der Endpoint umgestellt war
- Pipecat-API-Drift ggü. älterer Doku: `OpenAILLMContext` → `LLMContext`,
  `llm.create_context_aggregator()` → `LLMContextAggregatorPair(context)`
- **VAD-Wiring-Bug:** `vad_analyzer` am Transport wird von Pydantic in Pipecat ≥1.8 stillschweigend
  verworfen — gehört auf `LLMUserAggregatorParams`, nicht auf `TransportParams`. Symptom: viele
  User-Turns wurden ohne Bot-Antwort "überholt". Nach dem Fix stieg die Trefferquote vollständiger
  Turns von ~57 % auf ~83 %, später auf ~100 %.
- **Audio-Echo-Loop** ohne Headset (Mikro nimmt die eigene Bot-Ausgabe auf → Endlosschleife) →
  Headset mit getrennter Ein-/Ausgabe, kein Bluetooth (Latenz)

Vollständige Liste mit Fixes: [`docs/phase-0-setup.md`](./phase-0-setup.md) (Troubleshooting-Tabelle).

## 2. Automatisierte Latenzmessung aufgebaut

Vorher wurde Latenz händisch aus Logs gegrept — nicht reproduzierbar, zu wenig Datenpunkte für
einen sinnvollen Median. Stattdessen aufgebaut:

- **Metrik-Collector** (`pipeline.py` + `metrics/collector.py`): verdrahtet Pipecats eingebauten
  `UserBotLatencyObserver` so, dass jeder Turn eine JSON-Zeile nach `experiments/runs/` schreibt —
  `e2e_ms` (VAD-Sprechende-erkannt → erstes Bot-Audio, das Kriterium aus `CLAUDE.md`), plus
  Breakdown (`turn_detection_ms`, `llm_ttfb_ms`, `tts_ttfb_ms`).
- **Synthetic Caller** (`tests/synthetic_caller.py` + `tests/synthetic_transport.py`): spielt
  WAV-Clips statt Mikro ein, real-time gepaced, wartet zwischen Turns auf Bot-Stille — läuft
  unbeaufsichtigt für beliebig viele Turns.
- **Fixture-Generator** (`tests/generate_fixtures.py`): 10 deutsche SDR-Äußerungen im tatsächlichen
  Pacemaker-Kontext (Opener + Reaktionen auf Einwände), per Azure-TTS synthetisiert.
- **Aggregator** (`metrics/aggregate.py`): pandas-basierte p50/p90/p95-Auswertung, prüft direkt
  gegen das 900-ms-p90-Akzeptanzkriterium aus `CLAUDE.md`.

Details und dabei gefundene Bugs (Metrik-Zuordnungsbug STT/TTS-Substring, Pfad-Bug im Aggregator,
falscher Modulpfad): [`docs/phase-0-setup.md`](./phase-0-setup.md), Punkte 7–9.

## 3. Baseline-Messung

Erster vollständiger 30-Turn-Lauf, lokaler Entwicklungsrechner (nicht die EU-Mess-VM):

| Metrik | p50 | p90 | p95 |
|---|--:|--:|--:|
| E2E (Akzeptanzkriterium) | 2176 ms | 2377 ms | 2476 ms |
| Turn-Detection-Overhead | 1036 ms | 1081 ms | 1099 ms |
| LLM TTFB | 444 ms | 569 ms | 596 ms |
| TTS TTFB | 499 ms | 599 ms | 614 ms |

**FAIL** gegen 900 ms p90 (2,6-faches Budget). Wichtigster Befund: Die Turn-Detection-Phase allein
überschreitet schon für sich das gesamte Budget — größter Einzelposten, in derselben
Größenordnung wie LLM- und TTS-TTFB zusammen.

Details: [`experiments/summaries/2026-09-06-stack-b-azure-eu-baseline.md`](../experiments/summaries/2026-09-06-stack-b-azure-eu-baseline.md) §3.

## 4. Optimierung — was funktioniert hat, was nicht

Ziel: aus Stack B das Maximum holen, bevor Infrastruktur-Änderungen (EU-VM) oder ein zweiter Stack
angegangen werden.

### Übernommen

**Azure STT `Speech_SegmentationSilenceTimeoutMs` 500ms → 200ms** (`stacks.py`, über das interne
`_speech_config`-Objekt, da Pipecat dafür keinen Konstruktor-Parameter exponiert):

| Einstellung | E2E p50 | E2E p90 | Turn-Detection p50 |
|---|--:|--:|--:|
| Azure-Default (~500ms) | 2176 ms | 2377 ms | 1036 ms |
| **200ms (übernommen)** | **1570 ms** | **1817 ms** | **476 ms** |
| 100ms (SDK-Minimum) | 1396 ms | 1566 ms | 337 ms |

100ms wurde verworfen: schneller, aber sichtbare Satz-Fragmentierung bei synthetischen Clips
("Guten Tag, hier ist Lena Fischer..." in zwei Turns zerschnitten). Bei echter Sprache mit mehr
Mikro-Pausen vermutlich stärker. Müsste vor Wiederaufnahme mit echter Sprache validiert werden.

**Ergebnis: E2E p90 2377ms → 1817ms (−24 %), aktueller Bestwert.**

### Getestet und verworfen

| Versuch | Hypothese | Ergebnis | Grund für Ablehnung |
|---|---|---|---|
| `wait_for_transcript=False` | STT-Finalisierung vom kritischen Pfad nehmen | Turn-Detection p50 1036→2648ms (schlechter!) | Mechanismus ungeklärt, Richtung eindeutig negativ |
| `LocalSmartTurnAnalyzerV3(cpu_count=4)` | Mehr Kerne für ONNX-Inferenz | Turn-Detection p50 476→487ms | Kein Effekt, innerhalb Messstreuung |
| TTS `TextAggregationMode.TOKEN` | Satzweise durch tokenweise Synthese ersetzen | Nicht getestet (Code-Analyse reicht) | Über den von Pipecat genutzten SSML-Weg ein `SpeechSynthesizer`-Request pro Chunk, hohes Risiko für abgehackte Bot-Stimme. *(Korrektur 2026-10-07: Azure bietet Text-Streaming-TTS über WebSocket v2 / TextStream — als eigener Versuch offen.)* |
| ChatHistory-Sliding-Window (15 Turns) | Wachsenden Prompt begrenzen | Prompt-Tokens 1759→993, aber E2E p50 1570→1770ms (schlechter!) | Zerstört Azures automatisches Prompt-Caching (Cache-Treffer 1664→0) — gecachte Tokens sind günstiger als weniger, aber frische |
| `SmartTurnParams.stop_secs` 3s→1.5s (synthetisch) | Tail-Latenz bei Fehlklassifikation senken | Turn-Detection p50 476→491ms, p90 unverändert | Saubere TTS-Clips lösen kaum `INCOMPLETE` aus — synthetisch nicht validierbar, weder Nutzen noch Cutoff-Risiko |

Auch geprüft und ohne Umsetzung verworfen: Temperatur/Top-P (kein Latenz-Effekt generell),
`max_completion_tokens` (kein Effekt auf TTFB), Speculative Decoding/Quantisierung/LoRA (kein
Zugriff über Azure Managed API), Edge-Caching häufiger Nutzer-Eingaben (widerspricht dem
Trainingszweck — Antworten müssen inhaltsabhängig bleiben).

Vollständige Herleitung aller zehn ursprünglich vorgeschlagenen Ansätze plus Nachträge:
[`experiments/summaries/2026-09-07-latenz-ansaetze-plausibilitaetspruefung.md`](../experiments/summaries/2026-09-07-latenz-ansaetze-plausibilitaetspruefung.md).

## 5. Wichtiger methodischer Fund: echte vs. synthetische Gespräche

Ein echter, manuell geführter Testanruf über dieselbe automatisierte Pipeline ergab (n=8 Turns):

| | Synthetisch (30 Turns) | Echtes Gespräch (8 Turns) |
|---|--:|--:|
| E2E p50 / p90 / p95 | 1570 / 1817 / — ms | **2028 / 3208 / 4171 ms** |
| Turn-Detection p50 / p90 | 476 / 545 ms | 447 / **1375 ms** |

**Echte Gespräche waren nicht schneller als synthetische Tests — eher schlechter und deutlich
unregelmäßiger.** Ein ursprünglicher gegenteiliger Eindruck ("echt fühlte sich schneller an") hält
der Messung nicht stand; er stammte vermutlich aus der Zeit vor der automatisierten Pipeline.

Konkreter Ausreißer: Ein Turn hatte `turn_detection_ms: 3199.8` — der Rohlog zeigt dazu vier
`INCOMPLETE`-Verdikte des Smart-Turn-Modells in Folge (echte, zögerliche Sprechpausen), nahe am
3-Sekunden-`stop_secs`-Default. Das korrigiert eine zuvor zu optimistische Annahme: Dieser
Mechanismus *kann* real spürbar in der Latenz auftauchen, auch wenn er in der Sache richtig
entscheidet (Person ist noch nicht fertig).

Details: [`experiments/summaries/2026-09-07-latenz-ansaetze-plausibilitaetspruefung.md`](../experiments/summaries/2026-09-07-latenz-ansaetze-plausibilitaetspruefung.md),
Nachträge 2–4.

## 6. Aktueller Stand

- **Konfiguration:** `Speech_SegmentationSilenceTimeoutMs=200`, alle anderen Parameter auf
  Pipecat-Default (`stop_secs=3`, `cpu_count=1`, `TextAggregationMode.SENTENCE`, voller
  Gesprächsverlauf ohne Fenster).
- **Bestwert synthetisch:** E2E p50 1570ms / p90 1817ms.
- **Akzeptanzkriterium (`CLAUDE.md`, `phase-0-proof-of-concept.md` §2): p90 < 900ms — weiterhin
  FAIL**, sowohl synthetisch als auch (deutlicher) im echten Gespräch.
- Code, Lint (`ruff check`/`format`) und Tests (`pytest`, 3 Tests) sind durchgehend sauber
  gehalten; jeder verworfene Versuch wurde vollständig zurückgerollt, nicht nur deaktiviert.

## 7. Offene nächste Schritte

Priorisiert nach vermuteter Wirkung:

1. **EU-Mess-VM (Hetzner) migrieren** — schneidet reine Netzwerk-RTT nach `germanywestcentral`
   auf allen drei Legs (STT/LLM/TTS) ab; noch nicht gezogen, vermutlich größter verbleibender
   Einzelhebel.
2. **Strukturelle Grenze einordnen:** Azure STT ist laut Pipecats eigenem Benchmark
   (`stt_latency.AZURE_TTFS_P99 = 1.8s`) der langsamste unterstützte STT-Provider (Deepgram:
   0,35s). Ob 900ms p90 ohne STT-Provider-Wechsel überhaupt erreichbar ist, ist offen.
3. **Zweiten Stack anbinden** (A/US-Baseline oder C/EU-souverän) für den im Phase-0-Plan
   geforderten Vergleich — aktuell nur `azure-eu` implementiert.
4. **Barge-in-Latenz und Rollenbruch-Check** (Schritt 10 im Phase-0-Plan) nachziehen — noch nicht
   gemessen bzw. nur auf Keyword-Ebene (LLM-Judge offen).
5. **`stop_secs=1.5s` mit echtem Gespräch validieren** (nicht mehr synthetisch möglich, siehe §5) —
   insbesondere darauf achten, ob legitime Sprechpausen fälschlich abgeschnitten werden.
6. Kleiner, risikoarmer Nebenpunkt: lokaler TTS-Cache für die wenigen wirklich fixen Phrasen.

## 8. Sonstiges

- **Zweites Gerät einrichten:** `brew install uv portaudio`, Repo klonen, `cd agent && uv sync`,
  `.env` aus `.env.example` neu anlegen (nicht über Git, da gitignored), Headset ohne Bluetooth.
  Kein Docker/LiveKit nötig für `--transport local`-Testanrufe.
- **macOS-Systemschlaf** killt unbeaufsichtigte Hintergrund-Messläufe hart (SIGSEGV in Azures
  TTS-SDK beim Aufwachen) → Läufe immer mit `caffeinate -i <command>` starten.
