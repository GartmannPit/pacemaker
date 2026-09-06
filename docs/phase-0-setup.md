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
   - TPM/Quota: Default lassen; bei „quota exceeded" TPM auf z. B. 10K senken.
6. Zurück auf der **Azure-OpenAI-Ressource** (nicht Foundry) → **Keys and Endpoint**. Notieren:
   - **Endpoint** (`https://pacemaker-openai.openai.azure.com/`) → an `AZURE_OPENAI_ENDPOINT`
     zusätzlich **`openai/v1`** anhängen (siehe unten, § 3).
   - **KEY 1** → `AZURE_OPENAI_API_KEY`

**Wichtig — welche API-Version:** Pipecats `AzureLLMService` (≥ 1.8.0) nutzt die neue
Azure-**v1-API**, sobald `AZURE_OPENAI_ENDPOINT` auf `/openai/v1` endet — keine separate
`api-version` mehr nötig. Neu erstellte Azure-Ressourcen über den **AI-Foundry-„New
project"-Flow** (Beispielcode dort nutzt `DefaultAzureCredential` + `/openai/v1`) sprechen
teils **nur** diese v1-API; die klassische Route
(`/openai/deployments/<name>/chat/completions?api-version=...`) liefert dann `404 Resource
not found`, egal wie Deployment-Name oder api-version lauten. Immer `/openai/v1` anhängen,
dann funktioniert Key-Auth auf beiden Ressourcentypen.

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
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI → Keys and Endpoint → Endpoint, **+ `openai/v1` anhängen** | `https://pacemaker-openai.openai.azure.com/openai/v1` |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI → Keys and Endpoint → KEY 1 | `d4e5f6…` |
| `AZURE_OPENAI_DEPLOYMENT` | **Deployment-Name** aus AI Foundry (nicht der Modellname, falls abweichend) | `gpt-4.1-mini` |

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
| Azure OpenAI **`404 Resource not found`** bei **jedem** Chat-Call, egal welcher Deployment-Name | `AZURE_OPENAI_ENDPOINT` endet nicht auf `/openai/v1`. Manche (v. a. neu über den AI-Foundry-„New project"-Flow angelegte) Ressourcen sprechen **nur** die neue v1-API, nicht die klassische `/openai/deployments/...?api-version=...`-Route. Fix: `/openai/v1` an den Endpoint anhängen — funktioniert mit Key-Auth auf beiden Ressourcentypen. Direkt testbar mit `curl -s -w '%{http_code}' "$AZURE_OPENAI_ENDPOINT/responses" -H "api-key: $AZURE_OPENAI_API_KEY" -H "Content-Type: application/json" -d '{"model":"'$AZURE_OPENAI_DEPLOYMENT'","input":"OK"}'`. |
| Azure OpenAI **`429`** | TPM-Quota des Deployments zu klein oder erschöpft → in AI Foundry TPM erhöhen oder Quota-Antrag stellen. |
| Deployment von `gpt-4.1-mini` scheitert mit **„Insufficient quota" / „Quota exceeded"** (Deployment lässt sich gar nicht erst anlegen) | Bei **Free-Trial-Subscriptions** vergibt Azure für OpenAI-Modelle i. d. R. **0 Default-Quota**, unabhängig von Region oder Guthaben. Fix: Subscription auf **Pay-As-You-Go** upgraden (Portal → Subscriptions → Upgrade), danach erneut versuchen. Bleibt die Quota 0: AI Foundry → *Management Center* → *Quota* → Erhöhung beantragen (bei Standard-Deployment meist selfservice). Ggf. Region wechseln (`France Central` / `Sweden Central`). **Nicht** auf „Global Standard" ausweichen, um Quota-Probleme zu umgehen — das kann außerhalb der EU routen. |
| TTS-Fehler „voice not found" | `AZURE_TTS_VOICE` muss in der Region verfügbar sein. `de-DE-ConradNeural` / `de-DE-KatjaNeural` sind breit verfügbar. |
| Antwort kommt spät / klingt roboterhaft | Für diesen Schritt normal. Latenz- und Qualitätsmessung ist Woche 2–3. |
| Agent „hängt" / wiederholt sich endlos, wirkt aber nicht abgestürzt (kein Error im Log) | **Audio-Echo-Loop**: Das Mikro nimmt die eigene Lautsprecher-Ausgabe des Agenten auf, STT transkribiert sie als neuen User-Turn, das löst eine Interruption aus, der Bot fängt fast denselben Satz nochmal an — Loop. Im Log erkennbar an `broadcast_interruption` kurz nach `Bot started speaking`, plus User-Turns, die fast wortgleich mit dem vorherigen Bot-Turn sind. Fix: macOS → Systemeinstellungen → Ton → **Ausgabe** und **Eingabe** getrennt auf Headset stellen (nicht MacBook-Lautsprecher/-Mikro). Kabelgebundenes Headset ist zuverlässiger als Bluetooth (Latenz). |
| Auch mit Headset: viele Bot-Antworten bleiben aus, User-Turn wird kurz nach `User stopped speaking` sofort wieder `User started speaking` (Log-Gap oft < 1 s) | `LocalAudioTransportParams(vad_analyzer=...)` wird in Pipecat ≥ 1.8 von Pydantic still verworfen — kein Feld mehr dafür am Transport. VAD muss stattdessen auf Aggregator-Ebene via `LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer())` an `LLMContextAggregatorPair` übergeben werden (siehe `pipeline.py`). Ohne das läuft Turn-Erkennung rein über Transkription + das semantische Smart-Turn-v3-Modell (Default `stop_secs=3`), das bei Sprechpausen im Satz mitunter vorzeitig „Ende" erkennt. |
| Unbeaufsichtigter Messlauf (z. B. `synthetic_caller`) bricht nach einer langen Log-Lücke mit `EXIT 139` / Absturz ab, kurz davor `Azure TTS synthesis canceled: Codec decoding is not started within 2s` | **macOS ist zwischendurch in den Schlaf gegangen.** Beim Aufwachen wirft Azures TTS-SDK diesen Codec-Timeout, die Fehlerbehandlung im nativen SDK-Teil crasht hart. Fix: Läufe mit `caffeinate -i <command>` starten, verhindert Idle-Sleep für die Prozessdauer. |

---

## Danach

WebRTC-Transport (`infra/docker-compose.yml`, LiveKit) verdrahten und die Messkette
aufbauen — siehe [`phase-0-proof-of-concept.md`](phase-0-proof-of-concept.md) §3, Woche 2.
