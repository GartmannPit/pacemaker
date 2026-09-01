# Phase 0 — Technischer Proof of Concept

*Aufschlüsselung von Phase 0 aus `Pacemaker.md`, Abschnitt 5. Stand: 2026-09-01.*

---

## 0. Ziel und Abgrenzung

**Eine Frage soll Phase 0 beantworten:**
Ist eine Ende-zu-Ende-Sprachantwortzeit von **< 900 ms** bei **akzeptabler deutscher Sprachqualität** mit einem **Provider-Stack, der EU-Datenresidenz bietet**, überhaupt erreichbar — und wenn ja, mit welchem Stack?

Das ist laut Strategiepapier das größte technische Risiko. Alles andere (Scoring, Dashboard, Auth, mehrere Szenarien) wird in Phase 0 **nicht** gebaut. Wenn die Latenzfrage nicht positiv beantwortet werden kann, ändert sich die gesamte Produktarchitektur — deshalb zuerst.

**Zeitrahmen:** 2–4 Wochen. **Team:** 1 Person (Technik), Gründer als Testhörer.

### Explizit nicht Teil von Phase 0

- Scoring-/Feedback-Pipeline
- Manager-Dashboard, jegliche Aggregation über Nutzer
- Authentifizierung, Nutzerverwaltung, Mandantentrennung
- Persistenz über flache Log-Dateien hinaus (keine Datenbank)
- Mehr als **ein** Szenario (Kaltakquise) und **eine** Persona
- Konfigurierbare Personas / Persona-Editor
- Produktionshärtung, Skalierung, CI/CD
- Unterschriebene AVVs — in Phase 0 wird nur geprüft, ob sie je Provider **verfügbar** sind
- Emotionserkennung in jeder Form (dauerhaft verboten, nicht nur in Phase 0)

---

## 1. Technische Umsetzung

### 1.1 Sprache und Laufzeit

| Komponente | Wahl | Begründung |
|---|---|---|
| **Voice-Agent** | **Python 3.12** | Das Ökosystem für Voice-Agenten (Pipecat, LiveKit Agents, Vocode) und sämtliche STT/LLM/TTS-SDKs mit eingebauter Latenzinstrumentierung ist quasi vollständig Python. Für einen Mess-PoC ist das der schnellste Weg. |
| **Frontend** | **TypeScript** (Vite, kein UI-Framework) | Nur eine Seite: verbinden, sprechen, hören, Transkript + Latenz-HUD sehen. React/Vue wäre Overhead. Design-Sprache aus `index_1.html` wiederverwendbar. |
| **Infrastruktur-Skripte** | Bash + `docker compose` | Reproduzierbarer lokaler Start von LiveKit + Agent. |

**Alternative, falls bewusst All-TypeScript gewünscht:** LiveKit Agents hat auch ein Node-SDK, Pipecat nicht. Der Preis wäre weniger Provider-Integrationen out-of-the-box und mehr Eigenbau bei der Metrik-Erfassung. Empfehlung bleibt Python für Phase 0; ein späterer Rewrite des dünnen Agent-Teils ist überschaubar.

### 1.2 Pipeline-Framework und Transport

| Zweck | Tool | Begründung |
|---|---|---|
| **Pipeline** | **Pipecat** | Modelliert STT → LLM → TTS als austauschbare Prozessoren — exakt die „STT/LLM/TTS als austauschbare Komponenten"-Anforderung aus `Pacemaker.md` §4.1. Liefert Metrik-Frames (TTFB pro Stufe, Processing-Zeit) frei Haus. Transport-agnostisch, voll self-hostbar. |
| **WebRTC-Transport** | **LiveKit**, self-hosted (Docker), auf EU-VM | Open Source, komplett in der EU betreibbar (kein SaaS-Zwang), brauchbare Echo-Cancellation und VAD, fertiger Pipecat-LiveKit-Transport. Alternative Daily.co scheidet für den Produktpfad wegen US-Hosting aus, wäre aber für rein lokale Tests schneller aufgesetzt. |
| **VAD / Turn-Taking** | Silero VAD (in Pipecat enthalten), optional Pipecat **Smart Turn** | Barge-in / Unterbrechbarkeit ist Kernfunktion (siehe Hero-Mockup „Ich hab ehrlich gesagt keine drei Minuten"). |

### 1.3 Provider-Kandidaten (die zu vergleichenden Stacks)

Phase 0 misst **drei bis vier** Stacks. Der US-Baseline-Stack dient nur als Referenz für die technische Obergrenze und kommt **nie** in den Produktpfad.

| Stack | STT | LLM | TTS | Zweck | EU-Residenz |
|---|---|---|---|---|---|
| **A — Baseline (US)** | Deepgram Nova-3 | gpt-4.1-mini | ElevenLabs Flash v2.5 | Technische Obergrenze: „Wie schnell geht es überhaupt?" | ❌ nur Referenz |
| **B — EU-Region** | Azure Speech (Germany West Central / Frankfurt) | Azure OpenAI, EU Data Zone | Azure Neural TTS, deutsche Stimmen (Region DE) | Der wahrscheinliche Produkt-Stack: ein Anbieter, EU-Region, AVV verfügbar | ✅ EU-Region, US-Mutterkonzern (CLOUD-Act-Restrisiko, vertraglich abbildbar) |
| **C — EU-souverän** | Gladia (FR) *oder* self-hosted `faster-whisper` large-v3 | Mistral Large (La Plateforme, EU) | Azure Neural TTS DE *oder* self-hosted (Piper/Kokoro) | Für Kunden mit Anforderungen über Standard-DPA/SCC hinaus | ✅ EU-Unternehmen bzw. self-hosted; TTS bleibt die Schwachstelle |
| **D — Speech-to-Speech (optional)** | OpenAI Realtime API bzw. Gemini Live (integriert) | | | Referenzmessung: wie viel schneller ist S2S ohne Kaskade? | ❌ nur Referenz |

**Anmerkungen:**
- **TTS ist der Engpass für Souveränität** (deckt sich mit `Pacemaker.md` §3). Self-hosted deutsche TTS in Echtzeit und mit natürlicher Prosodie ist Stand jetzt schwach. Azure Neural TTS DE (EU-Region, US-Mutter) ist der pragmatische Kompromiss für Stack C.
- Alle Provider-SDKs sitzen hinter einem schmalen Adapter (`agent/src/pacemaker_agent/stacks.py`). Ein Stack-Wechsel ist ein CLI-Flag, keine Code-Änderung in der Pipeline.
- **LLM-Modell:** `gpt-4o-mini` läuft bei Azure aus; Default ist jetzt `gpt-4.1-mini`. In Woche 3 zusätzlich `gpt-4.1-nano` als Latenz-Option gegen `gpt-4.1-mini` messen (Qualität vs. Antwortzeit).

### 1.4 Werkzeuge und Infrastruktur

| Zweck | Tool | Begründung |
|---|---|---|
| Python-Pakete | **uv** | Schnell, Lockfile, reproduzierbar. Kein pip/poetry. |
| JS-Pakete | **pnpm** | |
| Container | **Docker + docker compose** | LiveKit-SFU + Agent lokal mit einem Befehl. |
| Mess-VM | **1× Hetzner Cloud** (Region Deutschland: Nürnberg/Falkenstein), alternativ Scaleway/STACKIT | Realistische Netzlatenz zu den Provider-Endpunkten. Möglichst nah an der Provider-Region (Azure DE = Frankfurt). Ab Woche 2 laufen **alle** Messungen von dort, nicht vom Entwicklerlaptop. |
| Metrik-Erfassung | Pipecat-Metrik-Frames → strukturierte JSON-Zeilen pro Turn → Aggregation mit **pandas** | Keine handgestoppten Latenzen. |
| Test-Harness | **pytest** + „Synthetic Caller" (spielt vordefinierte deutsche WAV-Clips über die Pipeline ab, N Turns automatisiert) | Reproduzierbare Verteilung über ≥ 30 Turns statt Einzeleindruck. |
| Lint/Format Python | **ruff** (Lint + Format) | |
| Lint/Format TS | **eslint + prettier** | |
| Secrets | `.env` pro Stack (gitignored), `.env.example` gepflegt | |

### 1.5 Latenz-Definitionen (damit alle dasselbe messen)

- **E2E-Antwortzeit:** Zeitpunkt, an dem der VAD das Ende der Nutzeräußerung erkennt → Zeitpunkt des ersten ausgehenden Audio-Chunks der Persona. **Das ist die Zielmetrik.**
- **Teillatenzen:** STT-Endpointing, STT-Finalisierung, LLM-TTFT (time to first token), TTS-TTFB (time to first byte). Werden pro Turn mitgeloggt, um Engpässe zu lokalisieren.
- **Barge-in-Latenz:** Nutzer beginnt zu sprechen → Persona-Audio verstummt.
- **Reporting:** p50 / p90 / p95 über alle Turns eines Laufs, getrennt nach Stack. Mindestens 30 Turns synthetisch + ~15 Minuten manuelles Gespräch pro Gründer und Stack.

---

## 2. Akzeptanzkriterien für Phase 0

Phase 0 gilt als **bestanden**, wenn alle Punkte unter „Muss" erfüllt und dokumentiert sind.

### Muss

- [ ] **Latenz:** Mindestens **ein** Stack mit EU-Datenresidenz (Stack B oder C) erreicht **p90 der E2E-Antwortzeit < 900 ms**, gemessen über ≥ 30 Turns von der EU-Mess-VM auf einem deutschen Kaltakquise-Skript.
- [ ] **Sprachqualität:** Für diesen Stack bewerten **beide Gründer** die deutsche Sprachausgabe unabhängig als „für ein Rollenspiel ausreichend natürlich" (einfache 1–5-Skala, Mittel ≥ 3,5; wenn möglich Blind-A/B der Stimmen).
- [ ] **Barge-in:** Die Persona verstummt innerhalb von **≤ 300 ms**, nachdem der Nutzer zu sprechen beginnt. Funktioniert in ≥ 9 von 10 Testfällen.
- [ ] **Rollen-Konsistenz:** Die Persona bleibt über ein vollständiges ~5-minütiges Kaltakquise-Gespräch in der Rolle — kein „Als KI-Sprachmodell…", respektiert Budgetgrenze und Geduldsschwelle. Geprüft über **10 Testläufe** mit einem Rollenbruch-Check (Keyword-Filter + LLM-Judge über das Transkript).
- [ ] **EU-Compliance dokumentiert:** Für den empfohlenen Stack ist je Subdienstleister (STT, LLM, TTS) schriftlich festgehalten: EU-Region verfügbar (ja/nein, welche), AVV/DPA verfügbar (ja/nein, Link/Kontakt), CLOUD-Act-Exposition (US-Mutter ja/nein). Die Latenzdifferenz EU-Stack vs. US-Baseline ist beziffert.
- [ ] **Transkript + Timing:** Vollständiges Transkript mit Zeitstempeln pro Sprecherwechsel wird geloggt und ist als Datei exportierbar.
- [ ] **Kosten:** Kosten pro Gesprächsminute je Stack sind aus Provider-Preislisten + gemessenem Verbrauch geschätzt (STT/LLM/TTS getrennt ausgewiesen).
- [ ] **Reproduzierbarkeit:** Eine dritte Person kann anhand von `README.md` das Repo klonen, Abhängigkeiten installieren und lokal ein Kaltakquise-Gespräch in < 30 Minuten starten.
- [ ] **Ergebnisdokument:** `docs/phase-0-ergebnisse.md` liegt vor mit Vergleichstabelle (Latenz p50/p90/p95, Sprachqualität, EU-Compliance, Kosten/Min je Stack), einer **Stack-Empfehlung für Phase 1** und einer **Go/No-Go-Einschätzung**.

### Soll

- [ ] Zweiter EU-Stack ebenfalls vollständig vermessen (B **und** C), nicht nur einer.
- [ ] Speech-to-Speech-Referenzmessung (Stack D) durchgeführt und der Latenzvorteil beziffert.
- [ ] VAD-/Turn-Parameter für den Kandidaten-Stack grob getunt (Endpointing-Timeout, Mindestpause).
- [ ] Kurzer Abschnitt „Was uns überrascht hat" im Ergebnisdokument (für die Phase-1-Planung).

### Kann

- [ ] Einfache Web-Ansicht mit Live-Transkript und Latenz-HUD während des Gesprächs (statt nur Konsole).
- [ ] Automatischer Nightly-Lauf des Synthetic Callers gegen alle Stacks mit CSV-Ausgabe.

---

## 3. Grober Implementierungsplan

Reihenfolge folgt dem Prinzip: **erst ein durchgehender (langsamer) Sprachpfad, dann Messung, dann Provider-Matrix, dann Auswertung.** Kein Stack-Vergleich, bevor die Messkette steht.

> **Anpassung bei der Umsetzung (2026-09-01):** Zwei Abweichungen vom ursprünglichen Wortlaut unten, weil bei Azure bereits registriert wurde:
> - **Stack B (Azure EU) zuerst** statt Stack A (US-Baseline) — spart drei Provider-Registrierungen, und die erste Messung ist gleich die produktrelevante. Stack A dient in Woche 3 nur noch als Referenz-Obergrenze.
> - **Woche-1-Milestone über lokalen Audio-Transport** (`--transport local`, Mikro/Lautsprecher direkt) statt LiveKit. Null Infrastruktur für den „redet es auf Deutsch?"-Nachweis. LiveKit/WebRTC folgt unmittelbar danach (Schritt 2 + `infra/docker-compose.yml` liegen bereit).
>
> Setup dazu: [`phase-0-setup.md`](phase-0-setup.md).

### Woche 1 — Durchstich: ein Gespräch auf Deutsch, egal wie langsam

1. Repo-Struktur anlegen (siehe §4), `uv`- und `pnpm`-Setup, `README.md` mit Startanleitung.
2. LiveKit self-hosted via `docker compose` lokal zum Laufen bringen.
3. Pipecat-Agent mit **Stack A (Baseline)** als erster Pipeline: Mikrofon → Deepgram → gpt-4.1-mini → ElevenLabs → Lautsprecher. Zuerst mit lokalem Transport, dann über LiveKit.
4. Minimaler Web-Client (Vite + LiveKit JS): verbinden, sprechen, Antwort hören, Transkript in der Konsole.
5. **Meilenstein W1:** Ein zusammenhängendes deutsches Gespräch ist möglich. Latenz noch irrelevant.

### Woche 2 — Messkette und Persona

6. Metrik-Erfassung: Pipecat-Metrik-Frames abgreifen → pro Turn eine JSON-Zeile (Teillatenzen + E2E) → `experiments/runs/`.
7. Aggregations-Skript (`metrics/aggregate.py`): p50/p90/p95 je Lauf und Stack aus den JSON-Zeilen.
8. **Synthetic Caller** (`tests/synthetic_caller.py`): 8–12 vordefinierte deutsche Kaltakquise-Äußerungen als WAV, werden nacheinander in die Pipeline gespielt, E2E-Latenz je Turn gemessen, über N Wiederholungen aggregiert.
9. Persona v0 (`personas/kaltakquise_head_of_ops.py`): System-Prompt + einfacher Zustand (`geduld: int`, sinkt bei Wiederholung/Monolog; Budgetgrenze; Abbruch bei `geduld <= 0`). Szenario aus dem Hero-Mockup: Head of Operations, 180 MA.
10. Rollenbruch-Check (`tests/test_persona_consistency.py`): Keyword-Filter + LLM-Judge über gespeicherte Transkripte.
11. EU-Mess-VM (Hetzner DE) provisionieren, Agent + LiveKit dort deployen. **Ab jetzt alle Messungen von der VM.**
12. **Meilenstein W2:** `synthetic_caller` liefert eine reproduzierbare Latenzverteilung für Stack A von der EU-VM.

### Woche 3 — Provider-Matrix

13. **Stack B (Azure EU)** über den Adapter einbauen — nur STT/LLM/TTS-Implementierungen austauschen, Pipeline unverändert.
14. **Stack C (EU-souverän)** einbauen: Gladia *oder* `faster-whisper` self-hosted + Mistral Large + Azure TTS DE.
15. Optional **Stack D (S2S)** als Referenz: OpenAI Realtime bzw. Gemini Live.
16. Je Stack: ≥ 30 synthetische Turns + ~15 Minuten manuelles Gespräch pro Gründer. Rohdaten nach `experiments/runs/`.
17. Kosten pro Gesprächsminute je Stack aus Preislisten + gemessenem Token-/Audio-Verbrauch.
18. Je Provider die Compliance-Fakten zusammentragen (EU-Region, AVV-Verfügbarkeit, Mutterkonzern-Sitz).
19. **Meilenstein W3:** Vollständige Rohdaten für Stacks A–C (D optional).

### Woche 4 — Auswertung, Tuning, Entscheidung

20. Barge-in / VAD-Parameter für den/die Kandidaten-Stacks tunen und Barge-in-Latenz gegen das Kriterium messen.
21. Blind-A/B der TTS-Stimmen auf Deutsch mit beiden Gründern.
22. Vergleichstabelle finalisieren: Latenz p50/p90/p95, Sprachqualität, EU-Compliance, Kosten/Min.
23. `docs/phase-0-ergebnisse.md` schreiben: Empfehlung für den Phase-1-Stack, offene Risiken, „Was uns überrascht hat".
24. **Go/No-Go mit Marvin.** Bei Go: Übergabe der Erkenntnisse in `docs/phase-1-mvp.md`.

---

## 4. Directory-Aufbau (Soll)

Monorepo. `agent/` (Python) und `web/` (TS) sind getrennte Projekte mit eigenem Dependency-Management; `infra/`, `docs/`, `experiments/` liegen im Root.

```
pacemaker/
├── CLAUDE.md                         # Stack + Konventionen (dieses Repo)
├── README.md                         # Startanleitung (< 30 Min zum ersten Gespräch)
├── Pacemaker.md                      # bestehendes Strategiepapier
├── index_1.html                      # bestehender Landingpage-Entwurf (Single-File)
├── .gitignore                        # + Python-, .env-, experiments/runs-Einträge ergänzen
│
├── docs/
│   ├── phase-0-proof-of-concept.md   # dieses Dokument
│   ├── phase-0-ergebnisse.md         # Ergebnis + Empfehlung (Output von Phase 0)
│   ├── phase-1-mvp.md                # folgt
│   ├── phase-2-team.md               # folgt
│   └── phase-3-enterprise.md         # folgt
│
├── agent/                            # Python Voice-Agent (Pipecat)
│   ├── pyproject.toml
│   ├── uv.lock
│   ├── .env.example
│   ├── src/pacemaker_agent/
│   │   ├── main.py                   # Einstieg, wählt Stack per CLI-Flag
│   │   ├── pipeline.py               # Pipecat-Pipeline-Aufbau (stack-unabhängig)
│   │   ├── stacks.py                 # Provider-Kombinationen hinter Adaptern
│   │   ├── config.py
│   │   ├── personas/
│   │   │   └── kaltakquise_head_of_ops.py   # System-Prompt + Zustand
│   │   └── metrics/
│   │       ├── collector.py          # Pipecat-Metrik-Frames -> JSON-Zeilen
│   │       └── aggregate.py          # pandas: p50/p90/p95 je Lauf/Stack
│   ├── tests/
│   │   ├── test_pipeline.py
│   │   ├── test_persona_consistency.py
│   │   └── synthetic_caller.py       # spielt deutsche WAV-Clips ab, misst E2E
│   └── fixtures/audio/               # vordefinierte deutsche Test-Äußerungen (WAV)
│
├── web/                             # Frontend-PoC (Vite + TS + LiveKit JS)
│   ├── package.json
│   ├── vite.config.ts
│   ├── index.html
│   └── src/
│       ├── main.ts
│       ├── room.ts                  # LiveKit-Verbindung
│       └── hud.ts                   # Live-Transkript + Latenz-Anzeige
│
├── infra/
│   ├── docker-compose.yml           # LiveKit-SFU + Agent lokal
│   ├── livekit.yaml
│   └── hetzner-setup.md             # Provisionierung der EU-Mess-VM
│
└── experiments/
    ├── runs/                        # Roh-Messdaten pro Lauf (JSON/CSV) — gitignored
    └── summaries/                   # aggregierte Tabellen — eingecheckt
```

**`.gitignore` ergänzen um:** `__pycache__/`, `.venv/`, `*.pyc`, `.env`, `.env.*` (bereits drin), `experiments/runs/`, `agent/fixtures/audio/*.wav` (falls groß) — Audio-Fixtures ggf. per Git LFS oder Download-Skript.

---

## 5. Risiken und Gegenmaßnahmen

| Risiko | Auswirkung | Gegenmaßnahme in Phase 0 |
|---|---|---|
| Kein EU-Stack schafft < 900 ms | Kernannahme des Produkts wackelt | Früh messen (Woche 2/3). Falls knapp verfehlt: S2S-Stack (D) und aggressiveres Streaming/Endpointing prüfen, bevor No-Go. |
| Deutsche TTS-Qualität in EU-Region unzureichend | Persona wirkt „robotisch" | Mehrere deutsche Stimmen testen (Azure Neural + HD), Blind-A/B. Souveräne self-hosted TTS als klar dokumentierte Schwachstelle festhalten. |
| Rollenbrüche der Persona | Größtes Qualitätsrisiko laut §4.2 | Rollenbruch-Check als automatisierter Test ab Woche 2, nicht erst am Ende. |
| Messungen vom Laptop verzerren Latenz | Falsche Stack-Wahl | Ab Woche 2 ausschließlich von der EU-VM messen, Provider-Region-Nähe dokumentieren. |
| Provider-EU-Region an „eligible customer"-Status gebunden | Stack in der Praxis nicht nutzbar | In Woche 3 je Provider konkret klären (Sales-Kontakt), nicht nur Doku lesen. |
| CLOUD-Act bei US-Mutterkonzern | Landingpage-Aussage angreifbar | Nicht in Phase 0 lösbar — sauber im Ergebnisdokument als Rest­risiko benennen (Input für AVV-Formulierung, siehe `Pacemaker.md` §6). |

---

## 6. Output von Phase 0

1. Lauffähiger PoC-Code im Repo (`agent/`, `web/`, `infra/`).
2. Rohmessdaten in `experiments/runs/`, aggregierte Tabellen in `experiments/summaries/`.
3. `docs/phase-0-ergebnisse.md`: Vergleichstabelle, **Stack-Empfehlung für Phase 1**, Compliance-Faktenblatt je Provider, Kosten/Min, offene Risiken, Go/No-Go.
4. Startpunkt für `docs/phase-1-mvp.md`.
