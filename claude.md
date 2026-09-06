# Pacemaker — CLAUDE.md

## Was das ist

Deutschsprachiger KI-Sprachrollenspielpartner für B2B-SaaS-Vertriebstraining: SDRs üben
Verkaufsgespräche gegen eine Echtzeit-KI-Persona, danach Transkript + Scoring.
Strategie: `Pacemaker.md`. Phasenpläne: `docs/`. Aktuelle Phase: **Phase 0 — Technischer PoC**
(`docs/phase-0-proof-of-concept.md`).

## Kommunikation

- Projektsprache ist **Deutsch**: Antworten, Commit-Messages, Doku, Code-Kommentare.
- Produkt-/UI-Texte in der Sie-Form. Kein Marketing-Ton in Code oder Kommentaren.

## Harte Produkt-Constraints (ab Tag 1, nicht verhandelbar)

- **EU-Datenresidenz.** Sprachdaten, Transkripte und alle Ableitungen werden ausschließlich in
  der EU verarbeitet und gespeichert. Kein Provider ohne EU-Region **und** verfügbaren AVV im
  Produktpfad. US-Provider ausschließlich in Messläufen, die explizit als „Baseline/Referenz"
  markiert sind — nie im Produkt.
- **Keine Emotionserkennung.** Keine Prosodie-, Stimmlagen- oder Stress-Analyse, kein
  Emotions-Score. Scoring nur über Gesprächsinhalt und -struktur. (EU-AI-Act Art. 5, am
  Arbeitsplatz verbotene Praxis.) Auch nicht „nur zum Testen" einbauen.
- **Latenzbudget.** E2E-Antwortzeit (VAD erkennt Sprechende-hört-auf → erstes Audio der
  Persona): **p90 < 900 ms**, Ziel p50 < 700 ms.
- **KI-Transparenz.** Die KI-Natur des Gesprächspartners ist im Produkt jederzeit erkennbar.
- **Web-only.** Browser + WebRTC. Keine native App, keine Client-Installation.

## Tech-Stack (ab Phase 0)

| Bereich | Wahl |
|---|---|
| Voice-Agent | Python 3.12, **Pipecat** |
| WebRTC-Transport | **LiveKit**, self-hosted (Docker), EU-VM |
| Frontend | **Vite + TypeScript**, LiveKit JS SDK (kein UI-Framework im PoC) |
| VAD / Turn-Taking | Silero VAD / Pipecat Smart Turn |
| Python-Pakete | **uv** (kein pip/poetry) |
| JS-Pakete | **pnpm** |
| Container | Docker + `docker compose` |
| Tests | **pytest** (Agent). Frontend im PoC ohne Testsuite. |
| Lint/Format Python | **ruff** (Lint + Format) |
| Lint/Format TS | eslint + prettier, `strict: true` |
| Metriken | Pipecat-Metrik-Frames → JSON-Zeilen → pandas-Aggregation |

Provider-Kandidaten und die Vergleichsmatrix (Stacks A–D): `docs/phase-0-proof-of-concept.md` §1.3.
Stack-Auswahl im Agent per CLI-Flag: `--stack baseline | azure-eu | sovereign | s2s`.

## Repo-Layout

- `agent/` — Python Voice-Agent: Pipecat-Pipeline, Personas, Metrik-Erfassung, Test-Harness
- `web/` — Frontend-PoC (verbinden, sprechen, hören, Transkript + Latenz-HUD)
- `infra/` — `docker-compose.yml` (LiveKit + Agent), EU-VM-Setup
- `docs/` — Phasenpläne + Ergebnisdokus
- `experiments/runs/` — Roh-Messdaten (gitignored); `experiments/summaries/` — aggregiert, eingecheckt
- `index_1.html` — bestehender Landingpage-Entwurf (eigenständig, Single-File, inline CSS/JS)
- `Pacemaker.md` — Strategiepapier

Vollständiger Soll-Baum: `docs/phase-0-proof-of-concept.md` §4.

## Befehle

> Existieren jeweils erst, sobald das Verzeichnis angelegt ist (Phase-0-Aufbau).

Agent:
```
cd agent
uv sync
uv run pacemaker-agent --stack baseline            # lokaler Lauf
uv run pytest
uv run python -m pacemaker_agent.tests.generate_fixtures              # einmalig, Test-Audio erzeugen
uv run python -m pacemaker_agent.tests.synthetic_caller --stack azure-eu --turns 30
uv run python -m pacemaker_agent.metrics.aggregate
```

Frontend:
```
cd web
pnpm install
pnpm dev
```

Infra (LiveKit + Agent lokal):
```
cd infra
docker compose up
```

## Konventionen

- **Provider-SDKs immer hinter einem schmalen Adapter** (`agent/src/pacemaker_agent/stacks.py`),
  nie direkt in der Pipeline-Logik. Austauschbarkeit ist der ganze Zweck von Phase 0.
- Python: Type-Hints an allen öffentlichen Funktionen. `ruff check` und `ruff format` müssen
  sauber sein.
- TS: `strict`, prettier vor Commit.
- Messläufe schreiben strukturierte JSON-Zeilen, kein `print`. Handgestoppte Latenzen zählen nicht.
- Secrets nur in `.env` (gitignored). `.env.example` je Projekt pflegen.
- Commit-Messages auf Deutsch, imperativ („Füge Metrik-Collector hinzu").

## Nicht in Phase 0

Scoring, Dashboard, Auth, Multi-Tenancy, Persistenz über Flatfiles hinaus, mehr als ein
Szenario / eine Persona, konfigurierbare Personas, Produktionshärtung, CI/CD, unterschriebene
AVVs (nur Verfügbarkeit prüfen). Details: `docs/phase-0-proof-of-concept.md` §0.
