# Pacemaker

Deutschsprachiger KI-Sprachrollenspielpartner für B2B-SaaS-Vertriebstraining.
Kontext: [`Pacemaker.md`](Pacemaker.md) · Arbeitsanweisungen: [`CLAUDE.md`](CLAUDE.md) ·
Phase 0: [`docs/phase-0-proof-of-concept.md`](docs/phase-0-proof-of-concept.md)

## Aktueller Stand: Phase 0, Woche 1 — lokaler Sprachpfad

Ziel dieses Schritts: ein zusammenhängendes deutsches Gespräch mit der Persona über
Mikrofon und Lautsprecher. Latenz ist hier noch nicht das Thema (siehe Phase-0-Plan §3, W1).

### Voraussetzungen

- Python 3.12 und [uv](https://docs.astral.sh/uv/)
- Mikrofon + Lautsprecher — **Kopfhörer empfohlen**, sonst hört sich die Persona selbst
- Azure-Zugänge (siehe unten), Keys in `agent/.env`
- Erst für den WebRTC-Schritt danach: Docker Desktop, Node + pnpm

### Azure einrichten

Vollständige Anleitung (Ressourcen anlegen, Netzwerktyp, `.env`-Zuordnung,
Troubleshooting): **[`docs/phase-0-setup.md`](docs/phase-0-setup.md)**.

Kurz: zwei Ressourcen im Azure-Portal, beide Region **Germany West Central** —
**Azure AI Speech** (Tier F0) und **Azure OpenAI** mit einem `gpt-4.1-mini`-Deployment.
Netzwerktyp **„All networks"**.

### Starten

```bash
cd agent
cp .env.example .env      # dann die Azure-Keys eintragen
uv sync
uv run pacemaker-agent --stack azure-eu --transport local
```

Sprich auf Deutsch. Die Persona (Markus Brandt, Head of Operations) nimmt den
Kaltakquise-Anruf entgegen. `Strg+C` beendet.

> **Pipecat-Version:** Die Transport- und Service-Importe unter
> `agent/src/pacemaker_agent/` folgen der Pipecat-Quickstart. Pipecat bewegt sich
> schnell — nach `uv sync` mit `uv pip show pipecat-ai` die installierte Version prüfen
> und Importpfade in `stacks.py` / `main.py` bei Bedarf angleichen.

### Latenzauswertung (ab Woche 2 relevant)

```bash
uv run python -m pacemaker_agent.metrics.aggregate experiments/runs
```

### Tests & Lint

```bash
uv run pytest
uv run ruff check .
```

## Repo-Struktur

Vollständiger Soll-Baum: [`docs/phase-0-proof-of-concept.md`](docs/phase-0-proof-of-concept.md) §4.

- `agent/` — Python Voice-Agent (Pipecat): Pipeline, Personas, Metrik-Erfassung, Test-Harness
- `infra/` — `docker-compose.yml` (LiveKit) + EU-Mess-VM-Setup
- `docs/` — Phasenpläne und Ergebnisdokus
- `experiments/` — `runs/` Roh-Messdaten (gitignored), `summaries/` aggregierte Tabellen
- `index_1.html` — Landingpage-Entwurf (eigenständig, Single-File)
