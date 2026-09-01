# Phase 0 — Setup & erster Lauf

Schritt-für-Schritt bis zum ersten deutschen Kaltakquise-Gespräch mit der Persona
(lokales Audio, Azure-Stack). Ziel dieses Schritts: „redet es auf Deutsch?" — Latenz
ist hier noch kein Thema (siehe [`phase-0-proof-of-concept.md`](phase-0-proof-of-concept.md) §3, Woche 1).

---

## 1. Lokale Voraussetzungen

| Was | Prüfen / Installieren |
|---|---|
| **Python 3.12** | `python --version`; sonst übernimmt `uv` das (Schritt 4). |
| **uv** | `uv --version`; sonst: `powershell -c "irm https://astral.sh/uv/install.ps1 \| iex"` |
| **Headset** | Kopfhörer + Mikro. **Ohne Kopfhörer** hört die Persona sich selbst (Echo). |
| Docker Desktop, Node 20+, pnpm | Erst für den WebRTC-Schritt **nach** diesem Milestone. Jetzt noch nicht nötig. |

---

## 2. Azure-Ressourcen anlegen

Zwei Ressourcen im [Azure-Portal](https://portal.azure.com), **beide in derselben
Resource Group und derselben Region**.

- **Resource Group:** neu anlegen, Name z. B. `pacemaker-poc` (alles an einem Ort, am
  Ende von Phase 0 in einem Rutsch löschbar).
- **Region:** `Germany West Central` (Frankfurt). Das ist der Hebel für EU-Datenresidenz.

### 2.1 Azure AI Speech (STT + TTS)

1. Portal → **Create a resource** → nach `Speech` suchen → **Speech** (von Microsoft) → **Create**.
2. **Basics:**
   - Subscription: deine
   - Resource group: `pacemaker-poc`
   - Region: **Germany West Central**
   - Name: z. B. `pacemaker-speech`
   - Pricing tier: **Free F0** (1× pro Subscription kostenlos: 5 h STT + 0,5 Mio.
     Zeichen Neural-TTS pro Monat — reicht für Phase 0). Falllback: `Standard S0`.
3. **Network:** siehe [2.3](#23-netzwerkzugriff--welchen-type).
4. **Review + create** → **Create**. Nach dem Deployment: **Go to resource**.
5. Linke Navigation → **Keys and Endpoint**. Notieren:
   - **KEY 1** → `AZURE_SPEECH_KEY`
   - **Location/Region** (z. B. `germanywestcentral`) → `AZURE_SPEECH_REGION`

### 2.2 Azure OpenAI (LLM)

1. Portal → **Create a resource** → **Azure OpenAI** → **Create**.
2. **Basics:**
   - Resource group: `pacemaker-poc`
   - Region: **Germany West Central** (falls nicht wählbar: `Sweden Central` oder
     `France Central` — beide EU)
   - Name: z. B. `pacemaker-openai`
   - Pricing tier: **Standard S0**
   - Falls ein Hinweis **„Request access"** erscheint: kurzes Formular ausfüllen
     (Freischaltung meist < 1 Tag, oft sofort).
3. **Network:** siehe [2.3](#23-netzwerkzugriff--welchen-type).
4. **Review + create** → **Create** → **Go to resource**.
5. **Modell-Deployment anlegen:** auf der Ressource → **Go to Azure AI Foundry portal**
   (oder [ai.azure.com](https://ai.azure.com), Ressource auswählen) → **Deployments**
   → **Deploy model** → **Deploy base model**:
   - Modell: **`gpt-4.1-mini`** (Nachfolger von `gpt-4o-mini`, das Azure ausläuft)
   - Deployment name: **`gpt-4.1-mini`** (frei wählbar — genau dieser Name kommt in die `.env`)
   - Deployment type: **Data Zone Standard** (EU) falls angeboten, sonst **Standard**
     (regional). *Nicht* „Global Standard" (routet ggf. außerhalb der EU).
   - „View code" im Deployment zeigt die passende **api-version** → nach `AZURE_OPENAI_API_VERSION`.
   - TPM/Quota: Default lassen; bei „quota exceeded" TPM auf z. B. 10K senken.
6. Zurück auf der **Azure-OpenAI-Ressource** (nicht Foundry) → **Keys and Endpoint**. Notieren:
   - **Endpoint** (`https://pacemaker-openai.openai.azure.com/`) → `AZURE_OPENAI_ENDPOINT`
   - **KEY 1** → `AZURE_OPENAI_API_KEY`

### 2.3 Netzwerkzugriff — welchen „Type"?

Im Tab **Network / Networking** beider Ressourcen: **„All networks" / „Alle Netzwerke"**
(öffentlicher Endpunkt aktiv).

- Der Agent läuft auf deinem Laptop und später auf einer Hetzner-VM. Beide rufen die
  Azure-API über das öffentliche Internet auf (HTTPS + API-Schlüssel).
- **„Selected networks" / „Private endpoint"** würde voraussetzen, dass der Aufrufer in
  einem Azure-VNet sitzt — hier nicht der Fall, die Verbindung würde scheitern.
- **Datenresidenz** wird über die **Region** gesteuert, nicht über den Netzwerktyp. Der
  Netzwerktyp steuert nur, *wer* den Endpunkt erreichen darf.
- Optionale Härtung (für den PoC nicht nötig): „Selected networks" + Firewall-Regel mit
  deiner öffentlichen IP; ab Woche 2 zusätzlich die IP der Mess-VM.

---

## 3. `.env` befüllen

```powershell
cd agent
Copy-Item .env.example .env
```

Dann `agent/.env` öffnen und eintragen:

| Variable | Quelle | Beispiel |
|---|---|---|
| `AZURE_SPEECH_KEY` | Speech → Keys and Endpoint → KEY 1 | `a1b2c3…` |
| `AZURE_SPEECH_REGION` | Speech → Keys and Endpoint → Location | `germanywestcentral` |
| `AZURE_TTS_VOICE` | fest vorgegeben (sachliche männliche Stimme) | `de-DE-ConradNeural` |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI → Keys and Endpoint → Endpoint | `https://pacemaker-openai.openai.azure.com/` |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI → Keys and Endpoint → KEY 1 | `d4e5f6…` |
| `AZURE_OPENAI_DEPLOYMENT` | **Deployment-Name** aus AI Foundry (nicht der Modellname, falls abweichend) | `gpt-4.1-mini` |
| `AZURE_OPENAI_API_VERSION` | aus „View code" des Deployments | `2025-01-01-preview` |

`agent/.env` ist gitignored und darf nicht eingecheckt werden.

---

## 4. Agent starten

```powershell
cd agent
uv sync                                    # Abhängigkeiten + Python 3.12
uv run pytest                              # test_persona_consistency muss grün sein
uv run ruff check .
uv run pacemaker-agent --stack azure-eu --transport local
```

Mit Kopfhörer auf **Deutsch** sprechen. Die Persona **Markus Brandt** (Head of
Operations, 180 MA) nimmt den Kaltakquise-Anruf entgegen. `Strg+C` beendet.

**Erfolg dieses Schritts:** ein zusammenhängendes deutsches Gespräch ist möglich,
egal wie langsam. Barge-in (Reinreden) sollte grundsätzlich funktionieren.

---

## 5. Troubleshooting

| Symptom | Ursache / Fix |
|---|---|
| `uv sync` bricht beim Bauen von **`pyaudio`** ab | Für Python 3.12/Windows gibt es Wheels — meist reicht ein erneuter Lauf. Sonst „Desktop development with C++" (VS Build Tools) installieren, dann `uv sync`. Alternativ diesen Milestone überspringen und direkt den WebRTC-Transport nehmen (kein `pyaudio` nötig). |
| **`ImportError`** aus `pipecat…` beim Start | Pipecat-API-Drift. `uv pip show pipecat-ai` → Version notieren, Importpfade in `agent/src/pacemaker_agent/stacks.py` und `main.py` an die installierte Version angleichen (Quickstart der jeweiligen Version). Version + Stacktrace an Claude geben. |
| `Invalid device` / kein Mikrofon | Windows-Sounseinstellungen → Standard-Eingabegerät setzen. `LocalAudioTransport` nutzt das System-Standardgerät. |
| Azure **`401` / `403`** | Falscher Schlüssel oder Region. Der Key gehört zu genau einer Ressource in genau einer Region — `AZURE_SPEECH_REGION` muss dazu passen. |
| Azure OpenAI **`404 DeploymentNotFound`** | `AZURE_OPENAI_DEPLOYMENT` muss der **Deployment-Name** aus AI Foundry sein, nicht zwangsläufig der Modellname. |
| Azure OpenAI **`429`** | TPM-Quota des Deployments zu klein oder erschöpft → in AI Foundry TPM erhöhen oder Quota-Antrag stellen. |
| TTS-Fehler „voice not found" | `AZURE_TTS_VOICE` muss in der Region verfügbar sein. `de-DE-ConradNeural` / `de-DE-KatjaNeural` sind breit verfügbar. |
| Antwort kommt spät / klingt roboterhaft | Für diesen Schritt normal. Latenz- und Qualitätsmessung ist Woche 2–3. |

---

## Danach

WebRTC-Transport (`infra/docker-compose.yml`, LiveKit) verdrahten und die Messkette
aufbauen — siehe [`phase-0-proof-of-concept.md`](phase-0-proof-of-concept.md) §3, Woche 2.
