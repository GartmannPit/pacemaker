# Pacemaker

Deutschsprachiger KI-Sprachrollenspielpartner für B2B-SaaS-Vertriebstraining: SDRs üben ein
Kaltakquise-Gespräch gegen eine Echtzeit-KI-Persona.
Kontext: [`Pacemaker.md`](Pacemaker.md) · Arbeitsanweisungen: [`CLAUDE.md`](CLAUDE.md) ·
Phase 0: [`docs/phase-0-proof-of-concept.md`](docs/phase-0-proof-of-concept.md) ·
Ergebnisse: [`docs/phase-0-ergebnisse.md`](docs/phase-0-ergebnisse.md)

## Stand: Phase 0 — technischer Proof of Concept

Ein Sprachgespräch auf Deutsch mit der Persona „Markus Brandt" (Head of Operations, wird kalt
angerufen) über Mikrofon und Lautsprecher, plus Messkette (Latenz, Turn-Protokoll, Transkript).
Empfohlener Stack `azure-eu`: Azure AI Speech (Germany West Central) + Azure OpenAI
`gpt-4.1-nano` (Data Zone EU). Browser/WebRTC folgt in Phase 1.

## Erstes Gespräch in < 30 Minuten

### 1. Voraussetzungen

- **Python 3.12** und **[uv](https://docs.astral.sh/uv/)** (`pip`/`poetry` werden nicht benutzt).
- **Headset** (Kopfhörer + Mikrofon). Mit Lautsprechern hört sich die Persona selbst und
  unterbricht sich.
- Ein **Azure-Konto** mit zwei Ressourcen (Schritt 2).

> **Windows:** Blockiert die „Intelligente App-Steuerung" (Smart App Control) die von uv
> installierte Python-Version (Fehler beim Laden von `libcrypto`/`_ssl`), Python 3.12 von
> python.org installieren (`py install 3.12` oder Installer) und uv auf System-Python
> festlegen: PowerShell `$env:UV_PYTHON_PREFERENCE="only-system"` vor `uv sync`.

### 2. Azure einrichten (~15 Min.)

Ausführlich: [`docs/phase-0-setup.md`](docs/phase-0-setup.md).
Kurzfassung — **alles in der EU**, sonst ist der Stack nicht produkttauglich (`CLAUDE.md`):

1. **Azure AI Speech**, Region **Germany West Central**, Tarif S0 (F0 reicht zum Ausprobieren).
   Unter „Keys and Endpoint" Key 1 notieren.
2. **Azure OpenAI** (EU-Region, z. B. Sweden Central oder Germany West Central). In Azure AI
   Foundry ein Deployment **`gpt-4.1-nano`** anlegen, Typ **„Data Zone Standard"** (nicht
   „Global Standard" — das verarbeitet ggf. außerhalb der EU).
3. **Inhaltsfilter auf „Asynchronous Filter"** stellen (Foundry → Guardrails/Content filters →
   neuen Filter mit Streaming-Modus „Asynchronous Filter" anlegen und dem Deployment zuweisen).
   Ohne das puffert Azure jede Antwort komplett, die Persona antwortet ~0,3 s später.

### 3. Installieren und starten

```bash
git clone <repo-url> && cd pacemaker/agent
cp .env.example .env          # AZURE_SPEECH_KEY, AZURE_OPENAI_ENDPOINT (endet auf /openai/v1),
                              # AZURE_OPENAI_API_KEY eintragen; AZURE_OPENAI_DEPLOYMENT=gpt-4.1-nano
uv sync
uv run pacemaker-agent --stack azure-eu --transport local
```

Sprechen Sie zuerst — die Persona nimmt den Anruf entgegen, Sie sind der Vertriebler. Sie ist
eine **KI-Trainingsfigur** und bestätigt das auf Nachfrage. Das Gespräch endet, wenn die Persona
auflegt, oder mit `Strg+C`.

### 4. Transkript ansehen

```bash
uv run python -m pacemaker_agent.metrics.transcript_export --latest
```

Schreibt Markdown und CSV mit Beginn/Ende je Redebeitrag nach `experiments/runs/transcripts/`.

## Messungen (Phase 0)

Rohdaten unter `experiments/runs/` (gitignored), Auswertungen unter `experiments/summaries/`.
Gemessen wird von der EU-Mess-VM ([`infra/hetzner-setup.md`](infra/hetzner-setup.md)), nicht
vom Laptop.

```bash
cd agent
uv run python -m pacemaker_agent.tests.generate_fixtures        # einmalig: synthetische Clips
uv run python -m pacemaker_agent.tests.synthetic_caller --stack azure-eu --turns 30
uv run python -m pacemaker_agent.metrics.aggregate               # Latenz je Lauf
uv run python -m pacemaker_agent.metrics.conversation <runs-ordner>   # Gespräch/Barge-in
uv run python -m pacemaker_agent.tests.role_test                 # Rollentreue (Textmodus)
```

Einstellungen für Experimente per Umgebungsvariable (Defaults in `agent/src/pacemaker_agent/config.py`):
`AZURE_STT_SEGMENTATION_MS`, `PACEMAKER_VAD_STOP_SECS`, `PACEMAKER_VAD_START_SECS`,
`PACEMAKER_VAD_MIN_VOLUME`, `PACEMAKER_WARM_UP`, `AZURE_TTS_EDGE_SILENCE_MS`,
`PACEMAKER_SHORT_OPENER`, `PACEMAKER_RUNS_DIR`. Andere Stacks: `--stack s2s` (Azure Realtime),
`--stack baseline` (US-Referenz, nur Messung, nie Produkt).

### Tests & Lint

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

## Repo-Struktur

- `agent/` — Python Voice-Agent (Pipecat): Pipeline, Persona, Messkette, Test-Harness
- `infra/` — EU-Mess-VM (Hetzner), Messreihen-Skripte, `docker-compose.yml` (LiveKit, Phase 1)
- `docs/` — Phasenpläne, Prüfungen, Ergebnisdokumente
- `experiments/` — `runs/` Rohdaten (gitignored), `summaries/` Auswertungen
- `index_1.html` — Landingpage-Entwurf (eigenständig, Single-File)
