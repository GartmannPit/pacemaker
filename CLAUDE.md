# OneTry

## Projekt und Phase

**Produktname: OneTry** (bis 2026-10-28 „Pacemaker“; Gründerentscheidung Pit). Technische
Bezeichner bleiben bis zu einem eigenen, geplanten Umbau: Paket `pacemaker_agent`, Befehl
`pacemaker-server`, Variablen `PACEMAKER_*`, Pfade `~/.pacemaker`, Repo-Ordner, VM-Pfade,
Dateiname `Pacemaker.md`. Historische Dokumente, Messberichte und Fixtures (Aufnahmen sagen
„Pacemaker GmbH“) nicht umschreiben.

Deutschsprachiger KI-Sprachrollenspielpartner für B2B-SaaS-Vertriebstraining.
SDRs üben Gespräche mit einer Echtzeit-KI-Persona; Transkript und Scoring sind das Produktziel.
Aktuell: **Phase 1 — MVP für Pilotkunden**, Plan `docs/phase-1-mvp.md` freigegeben
(Pit, 2026-10-27). Phase 0 ist abgeschlossen (`docs/phase-0-ergebnisse.md` §8). Umsetzung in
der Reihenfolge von Plan §2; Grenzen unter „Nicht in Phase 1“.
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

## Zusammenarbeit Claude und Codex

Gründervorgabe Pit, 2026-10-27. Gilt für beide Agenten ohne erneuten Hinweis; Claude
organisiert die Schritte selbstständig. `AGENTS.md` ist ein versionierter, relativer Symlink
auf diese Datei; Codex liest damit dieselben Regeln.

- **Beide entwickeln.** Claude plant zusätzlich, koordiniert, verwaltet Worktrees und
  schreibende Git-Operationen und spricht externe Dienste und die Mess-VM an. Codex arbeitet
  in der Sandbox ohne Shell-Netz, ohne VM und ohne Keys.
- **Pläne prüft Codex.** Jeder Plan von Claude (Phasenplan, Präregistrierung, Feature- oder
  Architekturentwurf) geht vor der Umsetzung schreibgeschützt an Codex:
  `codex exec -s read-only -C "<repo>" -o "<absoluter-berichtspfad>" - < "<auftrag>"`.
  Claude arbeitet die Punkte ein oder begründet die Ablehnung; ungeklärte Widersprüche
  entscheidet Pit. Ein Codex-Review ersetzt keine Gründerfreigabe.
- **Code prüft der jeweils andere.** Claudes Code: `codex exec -s read-only -C "<worktree>"
  review --uncommitted` bzw. `review --base "<branch>"` (beide ohne eigenen Prüftext); mit
  Prüfauftrag stattdessen `codex exec -s read-only … - < "<auftrag>"` mit Verweis auf den Diff.
  Codex' Code: Review durch Claude (Diff lesen, Fachwissen aus früheren Läufen gegenprüfen,
  Tests selbst ausführen). Während eines Reviews bleibt der Stand eingefroren; relevante
  Änderungen danach brauchen ein neues Review. Integriert wird erst nach Review und grünen
  Tests; in der Sandbox nicht ausführbare Prüfungen holt Claude nach und dokumentiert sie.
- **Ein Worktree je Aufgabe, genau ein schreibender Agent darin.**
  `git worktree add "../pacemaker-worktrees/<branch>" -b "<branch>" "<basis-sha>"`; nicht
  committete Dateien werden nicht übernommen. Vor Übergabe in `<worktree>/agent`
  `uv sync --locked` (eigene `.venv` je Worktree). Übergabe an Codex:
  `codex exec -s workspace-write -c sandbox_workspace_write.network_access=false
  -C "<worktree>" -o "<absoluter-berichtspfad>" - < "<auftrag>"`. Codex prüft mit
  `PYTHON_DOTENV_DISABLED=1 uv run --offline --no-sync …`.
- **Jeder Auftrag** enthält Ziel, Umfang, Basisstand, betroffene Dateien, Prüfbefehle,
  Abnahmekriterien und den Hinweis, nicht zu committen oder zu pushen.
- **Merge, Push, VM, externe API-Läufe** (z. B. OpenAI, Azure): durch Claude. Messläufe auf
  der VM strikt nacheinander. Kostenpflichtige API-Läufe nur mit Pits Freigabe und
  Kostenschätzung vorab; die normale Nutzung von Claude und Codex ist davon nicht betroffen.
  Ausnahme (Pit, 2026-10-28): Kleinläufe unter 1 $ je Lauf ohne Einzelfreigabe; Schätzung
  vorher und Ist-Kosten danach trotzdem nennen. Ab der Größenordnung der Lasttests
  (mehrere Dollar) wieder vorab fragen.
- **Design-Skills** (Frontend, ab Schritt 2): geprüfte Kopien in `.claude/skills/` und
  `.agents/skills/` (Impeccable ohne Engine, Emil Kowalski, Vercel Web Interface Guidelines).
  Regeln und Herkunft in `.claude/skills/HERKUNFT.md`; `npx impeccable` nicht ausführen.
- **Datenschutz gilt auch indirekt:** `.env`, Keys und `agent/fixtures/robust` weder lesen
  noch über Tests, Skripte oder Unterprozesse zugänglich machen; nicht in Worktrees kopieren
  oder verlinken. `.gitignore` ist keine Zugriffssperre. Alle übrigen Regeln dieser Datei
  gelten für beide.

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
| Voice-Agent | Python 3.12, Pipecat; Sprachpfad OpenAI GPT-Live (`gpt-live-1`, Gründerentscheidung 2026-10-15); Azure-Kaskade bleibt im Code, wird aber nicht als Rückfall gepflegt (2026-10-27) |
| WebRTC | Produktpfad (Hybrid, Gründerentscheidung 2026-10-27): Browser ↔ OpenAI direkt per WebRTC, Steuerung über serverseitigen Sideband, Browser-Datenkanal gesperrt (`docs/phase-1-architekturversuch-hybrid.md`). LiveKit + Pipecat nur im bisherigen Mess- und Testpfad |
| Frontend | Vite + TypeScript, WebRTC ohne LiveKit-SDK im Produktpfad; kein UI-Framework |
| VAD / Turn-Taking | Kaskade: Silero VAD / Pipecat Smart Turn; `live`: serverseitig durch GPT-Live |
| Paketverwaltung | Python: uv; JavaScript: pnpm; kein pip/poetry/npm für Projektpakete |
| Container | Docker + docker compose |
| Tests | pytest für den Agenten; keine Frontend-Testsuite in Phase 0 |
| Python-Qualität | ruff check und ruff format |
| TypeScript-Qualität | strict: true, eslint, prettier |
| Metriken | Messpfad: Pipecat-Metrik-Frames → JSONL → pandas-Aggregation; Hybrid: Sideband-JSONL (`auswertung.py`), Browser-Messung neu zu instrumentieren |

Provider-Matrix: Phasenplan §1.3. Stack-Auswahl:
`--stack live | azure-eu | baseline | sovereign | s2s`. `live` verlangt
`OPENAI_LIVE_REGION=eu|referenz` (kein Default; `referenz` = api.openai.com).
Ein Stack-Name ist kein Nachweis einer geprüften EU-Konfiguration.

## Architektur und Konventionen

- Messpfad (Pipecat): Provider-spezifische SDK-Aufrufe hinter schmalen Adaptern in
  `agent/src/pacemaker_agent/stacks.py` kapseln, nicht in der Pipeline verteilen.
  Hybrid-Produktpfad: Provider-Protokoll (Sitzungserzeugung, Sideband) ebenso in einem
  schmalen Modul kapseln, nicht über Server und Frontend verteilen.
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
- agent/src/pacemaker_agent/hybrid/: Hybrid-Server (Phase 1, Schritt 1: Anmeldung, Sitzungen, Budget, Sideband)
- agent/tools/gptlive_browser/: Hybrid-Prototyp aus dem Architekturversuch (nicht Produktpfad)
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
uv run pacemaker-server nutzer-anlegen <name>                       # Hybrid-Server: Nutzer (Passwort verdeckt)
uv run pacemaker-server serve                                       # Hybrid-Server (Konfiguration: .env.example)
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

## Nicht in Phase 1

Manager-Dashboard, konfigurierbare Personas, CRM-/LMS-Anbindung, SLA, Mandantentrennung über
die Mindestanforderung in `docs/phase-1-mvp.md` §5 hinaus. Reale Nutzerdaten erst nach den
Voraussetzungen in Plan §1 (EU-Freigabe, DPA/AVV aller Dienste). Persistenz, Scoring und
Modellanbindungen erst im jeweiligen Planschritt nach Datenflussprüfung.
