# Pacemaker

## Projekt und Phase

Deutschsprachiger KI-Sprachrollenspielpartner für B2B-SaaS-Vertriebstraining.
SDRs üben Gespräche mit einer Echtzeit-KI-Persona; Transkript und Scoring sind das Produktziel.
Aktuell: **Übergang Phase 0 → Phase 1.** Phase 0 ist abgeschlossen (`docs/phase-0-ergebnisse.md` §8);
der Phase-1-Plan `docs/phase-1-mvp.md` ist ein Entwurf. Bis zu seiner Freigabe gelten die
Grenzen unter „Nicht in Phase 0“; Scoring wird noch nicht implementiert.
Strategie: `Pacemaker.md`. Phasenpläne: `docs/phase-0-proof-of-concept.md`, `docs/phase-1-mvp.md`.

## Arbeitsweise

- Vor Änderungen die betroffenen Dateien und den relevanten Abschnitt des Phasenplans lesen.
  Das Strategiepapier bei Produkt- oder Architekturentscheidungen hinzuziehen.
- Dokumentierte Pfade und Befehle können noch geplant sein. Existenz und Konfiguration
  zuerst prüfen; fehlende Implementierungen und Prüfergebnisse niemals erfinden.
- Harte Produkt-Constraints gelten auch für PoC, Test-Harness und neue Abhängigkeiten,
  soweit unten keine ausdrückliche Ausnahme steht. Widerspricht ein Plan diesen Regeln,
  den Konflikt benennen und die betroffene Entscheidung vor Umsetzung klären.
- Kleine, aufgabenbezogene Änderungen umsetzen. Keine zusätzlichen Frameworks,
  Infrastruktur oder Features späterer Phasen ohne entsprechenden Auftrag einführen.
- Bei SDK-Änderungen zuerst die im Lockfile gebundene Version ermitteln und passende
  offizielle Dokumentation prüfen. Beispiele anderer Versionen nicht ungeprüft übernehmen.
- Am Ende nennen: Änderungen, ausgeführte Prüfungen und Ergebnis, offene Einschränkungen.
  Nicht ausgeführte Tests und nicht gemessene Latenz ausdrücklich kennzeichnen.

## Kommunikation

- Antworten, Commit-Messages, Dokumentation und eigene Code-Kommentare auf Deutsch.
- Produkt- und UI-Texte in der Sie-Form. Kein Marketing-Ton in Code oder Kommentaren.
- Bestehende technische Bezeichner, SDK-Namen und erforderliche API-Felder beibehalten.
- Commit-Messages im Imperativ, z. B. „Füge Metrik-Collector hinzu“.

## Harte Produkt-Constraints

- **EU-Datenresidenz:** Sprachdaten, Transkripte und Ableitungen ausschließlich in der EU
  verarbeiten und speichern. Das umfasst auch Testdaten mit Personenbezug, Logs,
  Traces, Fehlerberichte und Backups. Anbieter brauchen eine geeignete EU-Konfiguration
  und einen verfügbaren AVV; die bloße Existenz einer EU-Region reicht als Nachweis nicht.
- **Baseline-Ausnahme:** Nicht-EU-Verarbeitung nur in ausdrücklich beauftragten und als
  „Baseline/Referenz“ gekennzeichneten Messläufen. Dafür ausschließlich synthetische
  Fixtures ohne reale Personen- oder Kundendaten verwenden. Keine automatische Baseline
  als Startkonfiguration und kein stiller Fallback auf andere Regionen oder Provider.
  **Ausnahme (Gründerfreigabe Pit, 2026-10-15):** Pits eigene Aufnahmen
  (`agent/fixtures/robust`) in automatischen Tests sowie manuelle Tests, die Pit auf
  Anweisung durchführt, dürfen weltweit verarbeitet werden. Gilt nicht für Stimmen oder
  Daten anderer Personen; solche Läufe bleiben als „Baseline/Referenz“ gekennzeichnet.
- **Phase 0 / AVV:** Verfügbarkeit prüfen und dokumentieren. Die Ausnahme für noch nicht
  unterschriebene AVVs gilt für synthetische PoC-Läufe; reale personenbezogene Daten
  bleiben ausgeschlossen, solange die erforderliche Freigabe fehlt.
- **Keine Emotionserkennung:** Keine Ableitung von Emotionen, Stress oder Persönlichkeit
  aus Stimme, Prosodie oder Stimmlage; auch nicht zu Testzwecken. Späteres Scoring nur
  anhand von Gesprächsinhalt und -struktur. VAD und Turn-Erkennung dienen ausschließlich
  der Gesprächssteuerung, nicht der Bewertung einer Person.
- **Latenz:** Gemessene GPT-Live-Latenz als angemessen beschlossen (Gründer, 2026-10-27);
  p90 < 900 ms ist kein Muss mehr. Änderungen dürfen die Latenz nicht ungemessen verschlechtern;
  neue Zielwerte setzen die Gründer. Messdefinition siehe unten.
- **Reale Nutzer:** Pilot- oder Kundendaten erst nach EU-Freigabe des OpenAI-Projekts und
  geprüftem DPA; bis dahin nur synthetische Daten und Pits eigene Stimme.
- **KI-Transparenz:** Die KI-Natur des Gesprächspartners ist im Produkt jederzeit erkennbar.
- **Web-only:** Browser und WebRTC; keine native App oder Client-Installation.
- **Entwicklungswerkzeuge:** Keine realen Gesprächsdaten, Secrets oder vertraulichen
  Kundeninformationen in Coding-Assistenten oder externe Dokumentations-/MCP-Abfragen geben.

## Tech-Stack

| Bereich | Wahl |
|---|---|
| Voice-Agent | Python 3.12, Pipecat; Sprachpfad OpenAI GPT-Live (`gpt-live-1`, Gründerentscheidung 2026-10-15), Azure-Kaskade als Rückfall |
| WebRTC | LiveKit, self-hosted über Docker auf EU-VM |
| Frontend | Vite + TypeScript, LiveKit JS SDK; kein UI-Framework im PoC |
| VAD / Turn-Taking | Kaskade: Silero VAD / Pipecat Smart Turn; `live`: serverseitig durch GPT-Live |
| Paketverwaltung | Python: uv; JavaScript: pnpm; kein pip/poetry/npm für Projektpakete |
| Container | Docker + docker compose |
| Tests | pytest für den Agenten; keine Frontend-Testsuite in Phase 0 |
| Python-Qualität | ruff check und ruff format |
| TypeScript-Qualität | strict: true, eslint, prettier |
| Metriken | Pipecat-Metrik-Frames → JSONL → pandas-Aggregation |

Provider-Matrix: Phasenplan §1.3. Stack-Auswahl:
`--stack live | azure-eu | baseline | sovereign | s2s`. `live` verlangt
`OPENAI_LIVE_REGION=eu|referenz` (kein Default; `referenz` = api.openai.com).
Ein Stack-Name ist kein Nachweis einer geprüften EU-Konfiguration.

## Architektur und Konventionen

- Provider-spezifische SDK-Aufrufe hinter schmalen Adaptern in
  `agent/src/pacemaker_agent/stacks.py` kapseln, nicht in der Pipeline verteilen.
- Pipeline, Metrik-Schema und Test-Harness möglichst unabhängig vom Provider halten.
- Python: Type-Hints für alle öffentlichen Funktionen. In asynchronen Audio-Pfaden
  keine blockierenden Netzwerk-, Datei- oder CPU-Aufgaben ausführen.
- Bei Änderungen an Audio-Verarbeitung auch Unterbrechungen durch den Nutzer,
  Abbruch laufender Ausgaben, Timeouts und Freigabe von Verbindungen berücksichtigen.
- Provider-/Regionskonfiguration explizit validieren. Bei fehlender oder unzulässiger
  Konfiguration verständlich abbrechen; keinen Ersatzprovider automatisch auswählen.
- Messdaten als strukturierte JSONL schreiben, kein print. Schemaänderungen mit Collector,
  Aggregation und betroffenen Tests abstimmen. Handgestoppte Latenzen zählen nicht.
- Secrets nur in gitignorierten .env-Dateien oder Laufzeit-Umgebungsvariablen halten.
  .env.example je Teilprojekt ohne echte Werte pflegen. Keine Secrets in Browser-Bundles,
  Logs, Fixtures oder Commit-Inhalten; das gilt insbesondere für LiveKit-API-Secrets.
- Neue Provider, Modelle und Abhängigkeiten auf zusätzliche Datenflüsse prüfen und
  die Entscheidung im Phasenplan dokumentieren. Lockfiles bei Änderungen mitpflegen.

## Messvertrag

- Start: geschätztes Sprechende = Zeitpunkt des VAD-Endereignisses minus stop_secs.
  Das ist ein Schätzwert; bei anderer Turn-Erkennung die Definition prüfen und dokumentieren.
- Stack `live`: kein VAD-Endereignis. Start = letztes hörbares Sample des Clips
  (`first_audio_after_clip_ms` im Turn-Protokoll); Persona-Audio während des Clips
  separat (`bot_starts_during_clip`). Turn-Enden von GPT-Live sind keine F2-Grundlage.
- Ende: erstes Audio der Persona. Im Turn-Protokoll immer den konkreten Messpunkt
  angeben: Provider-Ausgabe, Agent-Ausgabe oder Wiedergabebeginn im Browser.
  Eine Messung nur bis zur Agent-Ausgabe belegt keine vollständige Browser-E2E-Latenz.
- Browser-Wiedergabe separat instrumentieren, solange keine vergleichbare E2E-Messung
  existiert. Zeitstempel verschiedener Rechner nicht ohne validierte Synchronisierung abziehen.
- Erstes Audio und Beginn der inhaltlichen Antwort getrennt ausweisen; kurze Einstiege
  dürfen die Verzögerung bis zur eigentlichen Antwort nicht verdecken.
- Je Turn Status erfassen; Fehler, Timeouts und Unterbrechungen nicht still verwerfen.
  Bei Quantilen Grundgesamtheit, Ausschlüsse und Erfolgs-/Fehlerzahlen angeben.
- Je Lauf Stack, Provider/Modell, konfigurierte Region, Git-Stand, Abhängigkeitsversionen,
  relevante VAD-/Turn-Parameter und Fixture-Version festhalten; Kaltstarts separat ausweisen.
- 30 Turns dienen als kurzer Funktionslauf. Eine belastbare p90-Aussage benötigt einen
  vorab festgelegten größeren Messumfang und vergleichbare Testbedingungen.
- Turn-Protokoll: `metrics/turn_ledger.py`; den vollständigen Pfad im Repo prüfen.
- Vor jedem Vergleichslauf Präregistrierung in docs/ (Hypothese, Kriterien, Auswertung);
  Änderungen danach nur als gekennzeichneter Nachtrag.
- Latenzvergleiche nur auf der EU-Mess-VM und mit abwechselnden Bedingungen (A, B, A, B):
  Azure- und OpenAI-Latenz schwanken mit der Tageszeit.
- Fixtures auf Laptop und VM identisch halten (`fixtures_sha` im Manifest prüfen).

## Repo-Orientierung

- agent/: Pipeline, Personas, Metriken und Test-Harness
- web/: Verbinden, Sprechen, Hören, Transkript und Latenz-HUD (noch nicht angelegt)
- infra/: Docker Compose, LiveKit und EU-VM-Setup
- docs/: Phasenpläne und Ergebnisse
- experiments/runs/: Roh-Messdaten, gitignored
- experiments/summaries/: nur geprüfte, nicht sensible Aggregate einchecken
- index_1.html: eigenständiger Landingpage-Entwurf mit inline CSS/JS
- Pacemaker.md: Strategie; vollständiger Soll-Baum im Phasenplan §4

## Befehle und Prüfung

Aus dem ursprünglichen Plan übernommen; erst nach Anlage der Teilprojekte verfügbar.
Vor Ausführung Entry-Points, Skripte und Konfiguration prüfen.

Agent, aus agent/:
```sh
uv sync
uv run pacemaker-agent --stack azure-eu
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run python -m pacemaker_agent.tests.generate_fixtures
uv run python -m pacemaker_agent.tests.synthetic_caller --stack azure-eu --turns 30
uv run python -m pacemaker_agent.metrics.aggregate
PACEMAKER_RUNS_DIR=<ordner> uv run python -m pacemaker_agent.tests.synthetic_caller ...  # eigener Ordner je Messreihe
uv run python -m pacemaker_agent.metrics.conversation <runs_dir>   # T1/T2: F1–F6, Export für den Judge
uv run python -m pacemaker_agent.tests.judge <runs_dir>             # F4/F6, markierte Fälle von Hand prüfen
uv run python -m pacemaker_agent.tests.role_test                    # T3 Rollentreue (Textmodus)
```
Der azure-eu-Lauf setzt eine geprüfte EU-Konfiguration und synthetische Fixtures voraus.
Fixture-Erzeugung kann externe Dienste und Kosten auslösen; vorher Implementierung prüfen.
Baseline nur bei ausdrücklichem Messauftrag: `uv run pacemaker-agent --stack baseline`.

Frontend, aus web/: `pnpm install`, `pnpm dev`.
Bei TS-Änderungen vorhandene Typecheck-, Lint-, Format- und Build-Befehle aus package.json
verwenden. Fehlen diese, die Lücke benennen. Keine erfolgreichen Prüfungen behaupten.
Manuell prüfen: Mikrofonfreigabe, Verbindungsaufbau, Audiowiedergabe, Disconnect und HUD.

Infra, aus infra/: `docker compose config --quiet`, danach bei Bedarf `docker compose up`.
Bei Änderungen betroffene Agent-Tests ausführen; externe Provider nur für den beauftragten Lauf
ansprechen. Mocks für normale Unit-Tests verwenden. Messpfad-Änderungen zusätzlich messen.

## Nicht in Phase 0

Scoring, Dashboard, Auth, Multi-Tenancy, Persistenz über Flatfiles hinaus, mehrere Szenarien
oder Personas, konfigurierbare Personas, Produktionshärtung und CI/CD.
AVVs in Phase 0 auf Verfügbarkeit prüfen; Datenbeschränkungen oben gelten weiterhin.
Details: `docs/phase-0-proof-of-concept.md` §0.
