# Stack B (Azure EU) — Setup- und Latenz-Baseline

**Datum:** 2026-09-06
**Stack:** `azure-eu` (Azure AI Speech STT/TTS + Azure OpenAI `gpt-4.1-mini`)
**Status:** Woche-1/2-Meilensteine (Durchstich + Messkette) erreicht, siehe
[`phase-0-proof-of-concept.md`](../../docs/phase-0-proof-of-concept.md) §3.

---

## 1. Setup-Erkenntnisse

Nicht in der ursprünglichen Doku vorhergesehen, jetzt in
[`phase-0-setup.md`](../../docs/phase-0-setup.md) (Troubleshooting-Tabelle) nachgetragen:

| # | Problem | Fix |
|---|---|---|
| 1 | Azure-OpenAI-Quota bei **Free-Trial-Subscriptions** ist für neue Modelle i. d. R. 0, unabhängig von Region/Guthaben | Subscription auf **Pay-As-You-Go** upgraden |
| 2 | Deployment über den `ai.azure.com`-„New Project"-Flow angelegte Ressourcen sprechen teils **nur** die neue Azure-**v1-API** (`/openai/v1`), nicht die klassische `/openai/deployments/<name>/chat/completions?api-version=...`-Route → `404 Resource not found`, egal welcher Deployment-Name | `AZURE_OPENAI_ENDPOINT` auf `.../openai/v1` setzen; Pipecats `AzureLLMService` (≥ 1.8.0) schaltet daran automatisch auf den v1-Client, `api_version`-Parameter ist deprecated und entfällt |
| 3 | macOS: `uv sync` bricht beim Bauen von `pyaudio` ab (`portaudio.h` fehlt) | `brew install portaudio` vor `uv sync` |
| 4 | Pipecat-API-Drift ggü. beim Schreiben angenommener Version (installiert: `1.8.1`): `OpenAILLMContext` → `LLMContext`, `llm.create_context_aggregator()` → `LLMContextAggregatorPair(context)` | Importpfade + Aufrufe in `pipeline.py` angepasst |
| 5 | **VAD-Wiring-Bug:** `LocalAudioTransportParams(vad_analyzer=...)` wird von Pydantic still verworfen — kein Feld mehr dafür am Transport in Pipecat ≥ 1.8. VAD muss über `LLMUserAggregatorParams(vad_analyzer=...)` am Context-Aggregator laufen. Symptom: viele User-Turns wurden ohne Bot-Antwort „überholt" (Turn-Erkennung lief nur über Transkription + semantisches Smart-Turn-Modell, ohne VAD-Anteil) | In `pipeline.py` korrekt verdrahtet; Trefferquote stieg von ~57 % auf ~83 % vollständige Turns |
| 6 | **Audio-Echo-Loop** ohne Kopfhörer: Mikro nimmt die eigene Bot-Ausgabe auf, STT transkribiert sie als neuen User-Turn → Interruption → Endlosschleife | Headset mit getrennter Ein-/Ausgabe (kein Bluetooth wegen Latenz) |
| 7 | **Metrik-Zuordnungsbug:** Substring-Check `"TTS" in processor_name` matcht fälschlich auch `"AzureSTTService#0"` (enthält `"...STTS..."`) → STT-TTFB landete im TTS-Feld | Spezifischere Substrings `"LLMService"` / `"TTSService"` |
| 8 | **Pfad-Bug** in `metrics/aggregate.py`: Default war `cwd`-relativ (`Path("experiments/runs")`), `MetricsCollector` schreibt aber robust repo-root-relativ → beim dokumentierten Workflow (`cd agent` zuerst) fand der Aggregator nichts | Aggregator importiert jetzt denselben `RUNS_DIR` wie der Collector |
| 9 | Der in `CLAUDE.md`/Docstring dokumentierte Pfad `pacemaker_agent.tests.synthetic_caller` existierte nicht (`agent/tests/` ist kein Unterpaket von `pacemaker_agent`) | Synthetic Caller + Fixture-Generator nach `src/pacemaker_agent/tests/` verschoben, damit der Modulpfad stimmt |

## 2. Aufgebaute Infrastruktur

- **Metrik-Collector verdrahtet** (`pipeline.py`): Pipecats eingebauter `UserBotLatencyObserver`
  schreibt automatisch pro Turn eine JSON-Zeile nach `experiments/runs/` — `e2e_ms` (VAD-Sprechende-
  erkannt → erstes Bot-Audio, das Kriterium aus `CLAUDE.md`), plus Breakdown (`turn_detection_ms`,
  `llm_ttfb_ms`, `tts_ttfb_ms`).
- **Synthetic Caller implementiert** (`tests/synthetic_caller.py` + `tests/synthetic_transport.py`):
  spielt WAV-Clips statt Mikro ein, real-time gepaced (für unverfälschtes VAD/Turn-Detection-
  Verhalten), wartet zwischen Turns auf `BotStoppedSpeakingFrame`, damit sich Turns nicht
  überlappen. Läuft unbeaufsichtigt für beliebig viele Wiederholungen.
- **Fixture-Generator** (`tests/generate_fixtures.py`): erzeugt 10 deutsche SDR-Äußerungen per
  Azure-TTS, inhaltlich im Pacemaker-Kontext (Opener + Reaktionen auf Markus Brandts Einwände),
  16 kHz/16-bit/mono. Gitignored, jede Entwicklerin generiert lokal.

## 3. Ergebnis: 30 synthetische Turns

**Messrechner:** lokaler Entwicklungsrechner (macOS) — **noch nicht** die EU-Mess-VM aus
Schritt 11 des Phase-0-Plans. Zeitraum: 2026-09-06, 17:20–17:26 Uhr lokal.

| Metrik | p50 | p90 | p95 |
|---|--:|--:|--:|
| **E2E** (Akzeptanzkriterium) | 2176 ms | 2377 ms | 2476 ms |
| Turn-Detection-Overhead | 1036 ms | 1081 ms | 1099 ms |
| LLM TTFB (`gpt-4.1-mini`) | 444 ms | 569 ms | 596 ms |
| TTS TTFB (Azure Speech) | 499 ms | 599 ms | 614 ms |

**Akzeptanzkriterium** (`phase-0-proof-of-concept.md` §2: p90 < 900 ms): **FAIL** —
p90 liegt beim 2,6-Fachen des Budgets.

**Wichtigster Befund:** Die Turn-Detection-Phase allein (~1036–1099 ms) überschreitet schon für
sich das gesamte 900-ms-Budget, bevor LLM oder TTS überhaupt beginnen. Sie ist der größte
Einzelposten — in der gleichen Größenordnung wie LLM- und TTS-TTFB zusammen. Die geringe Streuung
zwischen p50/p90/p95 (< 15 % Spanne bei allen vier Metriken) zeigt: Das Verhalten ist konsistent,
kein Ausreißer-Rauschen — der Engpass ist strukturell, nicht zufällig.

## 4. Optimierungsversuche

Ziel: aus Stack B das Maximum rausholen, bevor ein zweiter Stack angebunden wird (Azure gilt
aktuell als produktiv attraktivster Stack). Ansatzpunkt: Turn-Detection-Overhead (§3) dominiert,
und Pipecats eigener Benchmark (`stt_latency.AZURE_TTFS_P99 = 1.8s`) zeigt Azure STT als
strukturell langsamsten unterstützten STT-Provider bei der Finalisierungslatenz (Deepgram: 0.35s).

### 4.1 `wait_for_transcript=False` — verworfen

Hypothese: `TurnAnalyzerUserTurnStopStrategy` wartet standardmäßig zusätzlich zum lokalen
Smart-Turn-Modell auf den finalisierten Azure-Transkript, bevor sie den Turn freigibt. Mit
`wait_for_transcript=False` sollte das lokale Modell allein entscheiden, Transkript-Finalisierung
liefe asynchron nebenher.

**Ergebnis (30 Turns): Gegenteil der Erwartung.** Turn-Detection-Overhead p50 stieg von 1036 ms auf
**2648 ms**, E2E p50 von 2176 ms auf **3768 ms**. LLM-/TTS-Werte blieben nahezu unverändert (schließt
allgemeines Netzwerk-Rauschen als Erklärung aus). Der genaue Mechanismus ließ sich aus dem
Pipecat-Quellcode nicht schlüssig ableiten — die Codepfade legen eigentlich nahe, dass die
Modell-Verdict-Logik (`COMPLETE`/`INCOMPLETE`) von diesem Flag unabhängig ist. **Änderung
zurückgerollt**, nicht übernommen.

### 4.2 Azure STT `Speech_SegmentationSilenceTimeoutMs` — übernommen

Zweiter Ansatzpunkt: Azures **serverseitige** Segmentierungs-Stille-Schwelle (steuert, wie lange
Azure selbst auf Stille wartet, bevor es ein Sprachsegment finalisiert), nicht in Pipecats
`AzureSTTService`-Konstruktor exponiert, aber über das interne `SpeechConfig`-Objekt setzbar
(`stt._speech_config.set_property(...)`, siehe `stacks.py`).

| Einstellung | E2E p50 | E2E p90 | Turn-Detection p50 | Anmerkung |
|---|--:|--:|--:|---|
| Azure-Default (~500 ms) | 2176 ms | 2377 ms | 1036 ms | Baseline §3 |
| **200 ms** | **1570 ms** | **1817 ms** | **476 ms** | **Übernommen** |
| 100 ms (SDK-Minimum) | 1396 ms | 1566 ms | 337 ms | Verworfen — siehe unten |

Bei 100 ms noch schneller, aber sichtbare **Überfragmentierung**: „Guten Tag, hier ist Lena
Fischer von der Pacemaker GmbH." wurde in zwei separate Turns zerschnitten statt als ein Satz
erkannt zu werden; bei 200 ms blieb er zusammen. Das zeigt sich schon mit sauber synthetisierten
TTS-Clips (klare Pausen) — bei echter menschlicher Sprache mit mehr Mikro-Pausen mitten im Satz
ist eine stärkere Fragmentierung zu erwarten. **200 ms übernommen** als Kompromiss; **100 ms vor
jedem weiteren Einsatz mit echter Sprache validieren**, falls später doch gewünscht.

**Zwischenstand nach Optimierung:** E2E p90 1817 ms — weiterhin **FAIL** gegen das
900-ms-Kriterium, aber von 2,6× auf ~2,0× über Budget reduziert, bei unveränderter LLM-/TTS-Latenz.

### 4.3 Nebenbefunde beim Testen

- **macOS-Systemschlaf killt Hintergrund-Messläufe hart:** Zwei 30-Turn-Läufe schlugen mit
  `EXIT 139` (SIGSEGV) fehl, jeweils nach einer ~15-minütigen Lücke im Log. Ursache: Der Rechner
  ging während des unbeaufsichtigten Laufs in den Schlaf; beim Aufwachen wirft Azures TTS-SDK
  `Codec decoding is not started within 2s`, und die Fehlerbehandlung im nativen SDK-Teil crasht.
  Fix: Läufe mit `caffeinate -i <command>` starten (macOS), verhindert Idle-Sleep für die Dauer
  des Prozesses.
- Der Synthetic Caller liefert gelegentlich mehr Datenzeilen als `--turns` (z. B. 37 statt 30) —
  vermutlich vereinzelte VAD-Fehltrigger während der eingespeisten Stille erzeugen zusätzliche,
  echte Turn-Zyklen. Kein Datenqualitätsproblem (keine Ausreißer in den Werten), aber noch nicht
  root-caused.

## 5. Einschränkungen dieser Messung

- **Nicht von der EU-Mess-VM** (Hetzner), sondern vom lokalen Rechner — Netzwerklatenz zu Azure
  `germanywestcentral` dürfte von einer EU-VM aus günstiger ausfallen.
- **Nur Stack B** — kein Vergleich gegen Stack A (US-Baseline) oder C (EU-souverän), siehe
  offene Punkte.
- **Nur synthetische Turns**, kein manuelles ~15-Minuten-Gespräch pro Gründer (Akzeptanzkriterium
  „Sprachqualität" separat offen).
- Barge-in-Latenz (≤ 300 ms-Kriterium) noch nicht separat gemessen.

## 6. Nächste Schritte

1. **100ms-Segmentierungsschwelle mit echter Sprache validieren** — falls das zusätzliche
   Latenz-Delta (§4.2) den Fragmentierungs-Tradeoff wert ist.
2. Verbleibenden Turn-Detection-Anteil (~476 ms bei 200 ms) weiter untersuchen — z. B.
   `stop_secs`/`pre_speech_ms` des Smart-Turn-v3-Modells selbst.
3. Auf **EU-Mess-VM** (Hetzner) migrieren, Messung wiederholen (Schritt 11–12 im Plan).
4. **Zweiten Stack** anbinden (A oder C) für den geforderten Vergleich — aktuell nur `azure-eu`
   implementiert, die anderen brauchen neue Provider-Accounts (siehe `stacks.py`).
5. Barge-in-Latenz und Rollenbruch-Check (Schritt 10) nachziehen.
