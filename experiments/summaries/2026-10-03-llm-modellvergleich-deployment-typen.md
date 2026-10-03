# LLM-Modellvergleich und Azure-Deployment-Typen

**Datum:** 2026-10-03
**Stack:** `azure-eu` (Azure AI Speech STT/TTS + Azure OpenAI), Pipecat 1.8.1, Python 3.12.15
**Messrechner:** Windows-Desktop (`DESKTOP-C60J786`), **nicht** der Mac der Messungen vom
2026-09-06/07 und nicht die EU-Mess-VM
**Vorgeschichte:** [`docs/2026-09-07-ueberblick-azure-eu-optimierung.md`](../../docs/2026-09-07-ueberblick-azure-eu-optimierung.md)

---

## 1. Fragestellungen

1. Bringt die Migration auf die EU-Mess-VM (Hetzner) einen relevanten Latenzgewinn? (bisher als
   größter Einzelhebel eingestuft)
2. Ändert ein anderes LLM-Modell die Latenz — konkret: Ist `gpt-4.1-nano` schneller als
   `gpt-4.1-mini`?
3. Welchen Einfluss hat der Azure-Deployment-Typ?

## 2. RTT-Check zu den Azure-Endpoints

Neues Skript [`infra/rtt-check.sh`](../../infra/rtt-check.sh): misst TCP-Handshake (~1 RTT) und
TLS-Handshake ohne Authentifizierung, gibt eine JSON-Zeile pro Host aus. 20 Samples je Host:

| Endpoint | TCP-RTT p50 | TLS-Handshake p50 |
|---|--:|--:|
| `germanywestcentral.stt.speech.microsoft.com` | 22,6 ms | 30,7 ms |
| `germanywestcentral.tts.speech.microsoft.com` | 22,7 ms | 28,7 ms |

Der Azure-OpenAI-Endpoint wurde nicht gemessen (zum Messzeitpunkt keine `agent/.env` auf dem
Rechner).

**Einordnung:** Eine Hetzner-VM in Deutschland liegt erfahrungsgemäß bei ~5 ms RTT nach Frankfurt,
spart also ~15–18 ms pro Round-Trip. Mit offenen Verbindungen liegen pro Turn etwa drei
Round-Trips im kritischen Pfad (STT-Ergebnis, LLM-Request, TTS-Request) → **~50 ms**; nur bei
Verbindungsaufbau pro Turn/Satz wären es ~100–150 ms. Die VM-Migration ist damit **kein
Haupthebel** gegen das 900-ms-Budget, bleibt aber Pflicht für LiveKit und die Abnahmemessung.

## 3. Methodik

- Synthetic Caller, 30 Turns je Lauf, 10 neu erzeugte Fixtures (Azure-TTS, `de-DE-ConradNeural`,
  Texte unverändert aus `generate_fixtures.py`).
- Konfiguration unverändert gegenüber dem Stand vom 2026-09-07:
  `Speech_SegmentationSilenceTimeoutMs=200`, sonst Pipecat-Defaults.
- Modellwechsel ausschließlich über `AZURE_OPENAI_DEPLOYMENT`, keine Codeänderung.
- Neu im JSONL-Schema: `llm_model` (Deployment-Name) und `device` (Hostname). Der Aggregator
  gruppiert jetzt nach Stack **und** Modell.
- Je Konfiguration **ein** Lauf (n = 44–45 Messpunkte, siehe §6).

## 4. Ergebnisse

### 4.1 Gültige Läufe (EU-konform)

| Modell | Deployment-Typ | E2E p50 | E2E p90 | E2E p95 | Turn-Det. p50 | LLM TTFB p50 / p90 | TTS TTFB p50 / p90 | n |
|---|---|--:|--:|--:|--:|--:|--:|--:|
| `gpt-4.1-mini` | Standard (regional) | 1412 | 1671 | 1700 | 534 | 406 / 552 | 332 / 441 | 45 |
| `gpt-4.1-mini` | Data Zone Standard (EU) | 1413 | 1656 | 1696 | 539 | 419 / 483 | 317 / 425 | 44 |
| `gpt-4.1-nano` | Data Zone Standard (EU) | **1369** | **1533** | **1552** | 535 | 425 / 517 | 250 / 382 | 44 |

Alle Werte in ms. **Akzeptanzkriterium p90 < 900 ms: alle FAIL.**

Rohdaten: `experiments/runs/` (gitignored); der regionale `mini`-Lauf liegt separat unter
`experiments/runs/_mini-standard-regional/`, damit er sich nicht mit dem gleichnamigen
Data-Zone-Lauf mischt.

### 4.2 Verworfener Lauf

| Modell | Deployment-Typ | E2E p90 | LLM TTFB p50 / p90 |
|---|---|--:|--:|
| `gpt-4.1-nano` | **Global Standard** | 2224 | 809 / 999 |

Verschoben nach `experiments/runs/_verworfen/`. Gründe:

- **Nicht EU-konform:** Global Standard kann Inferenz weltweit verarbeiten. Laut `CLAUDE.md` nur
  in explizit als „Baseline/Referenz" markierten Läufen zulässig — dieser Lauf war nicht so
  markiert, der Deployment-Typ wurde vor dem Start nicht geprüft. Es wurden ausschließlich
  synthetische TTS-Clips ohne Personenbezug verarbeitet.
- **Methodisch nicht verwertbar:** misst Modell und Routing gleichzeitig. Die doppelte LLM-TTFB
  ggü. demselben Modell als Data Zone (809 vs. 425 ms) ist dem Routing zuzuschreiben, nicht dem
  Modell.

## 5. Befunde

1. **Modellgröße beeinflusst die LLM-TTFB nicht messbar.** `mini` und `nano` liegen bei ~420 ms
   p50. Die Zeit bis zum ersten Token wird offenbar von fixem Overhead (Azure-Serving, Netzwerk,
   Prefill von ~500–2000 Prompt-Tokens, großteils gecacht) dominiert, nicht von der Modellgröße.
   Ein kleineres Azure-Modell schrumpft den LLM-Block nicht.
2. **Der E2E-Vorsprung von `nano` (−123 ms p90) stammt aus der TTS, nicht aus dem LLM.**
   Hypothese (ungeprüft): `nano` formuliert kürzere erste Sätze, die schneller synthetisiert
   werden. Bei n = 1 Lauf je Modell ist Zufall nicht ausgeschlossen; zur Einordnung: zwischen den
   beiden `mini`-Läufen lagen 15 ms p90.
3. **Data Zone Standard (EU) kostet gegenüber regionalem Standard keine messbare Latenz**
   (`mini`: p90 1656 vs. 1671 ms, LLM TTFB p90 sogar 483 vs. 552 ms).
4. **Deployment-Typ ist ein Compliance- und ein Latenzthema.** Zulässig im Produktpfad: Standard
   (regional, EU-Region) oder Data Zone Standard (EU). Global Standard: nein — und im Test
   zusätzlich doppelt so langsam.
5. **Qualität von `nano` nicht bewertet.** Rollentreue und Einwandbehandlung wurden nicht gemessen;
   der Latenzvorteil ist allein kein Grund für einen Wechsel.
6. **Budget-Lage unverändert:** Turn-Detection (~535 ms) + LLM-TTFB (~420 ms) liegen zusammen
   bereits über 900 ms. Ohne Änderung an Turn-Detection/STT ist das Kriterium mit diesem Stack
   nicht erreichbar.

## 6. Methodischer Befund: zerschnittene Clips

Clips mit **zwei Sätzen** (`01_opener`, `02_zeitdruck`, `03_wettbewerb`, `04_mail_brushoff`,
`06_budget`) werden an der Satzpause in zwei User-Turns zerlegt; die Persona antwortet auf beide
Hälften. Ergebnis: 44–45 LLM-Aufrufe bzw. Messpunkte statt 30 pro Lauf.

- Für den **relativen** Vergleich der Läufe untereinander unkritisch (gleicher Rechner, gleiche
  Clips, gleiches Verhalten in allen Läufen).
- Für **Absolutwerte** und den Vergleich mit den Mac-Zahlen vom 2026-09-07 (dort laut Überblick
  ~100 % vollständige Turns) eingeschränkt aussagekräftig.
- Ursache offen: anderer Rechner oder neu synthetisierte Fixtures mit längeren Satzpausen.
- Bestätigt die Beobachtung vom 2026-09-07, dass 200 ms Segmentierungs-Timeout an echten
  Satzgrenzen bereits trennt.

## 7. Tokenverbrauch

| Lauf | LLM-Aufrufe | Prompt-Tokens | davon gecacht | Completion-Tokens |
|---|--:|--:|--:|--:|
| `mini`, Data Zone | 45 | 54.261 | 34.688 | 766 |
| `nano`, Data Zone | 45 | 55.540 | 33.408 | 818 |

Vorab-Schätzung war ~35.000 Prompt-Tokens bei 30 Aufrufen; die Abweichung erklärt sich durch die
zusätzlichen Aufrufe aus §6. Kosten nach Listenpreis: < 2 Cent LLM pro Lauf; Speech (STT/TTS)
ist der größere Kostenposten, ebenfalls im Cent-Bereich.

## 8. Setup-Hinweise Windows

- `uv` über den offiziellen Installer (`irm https://astral.sh/uv/install.ps1 | iex`), installiert
  nach `C:\Users\<user>\.local\bin`; Python 3.12 bringt `uv` selbst mit. Kein `portaudio` nötig.
- Fixtures sind gitignored → auf neuem Rechner `generate_fixtures` erneut ausführen.
- Der in Azure AI Foundry angezeigte Endpoint endet teils auf `/openai/v1/responses`. Für Pipecat
  muss er auf **`/openai/v1`** enden, sonst fällt `AzureLLMService` auf die alte datierte API
  zurück.

## 9. Nächste Schritte

1. Weiteres Nicht-Realtime-Modell (Standard oder Data Zone EU) mit gleicher Methodik messen —
   Frage: Ist ein stärkeres Modell ohne Reasoning bei gleicher TTFB nutzbar?
2. Realtime-Modell als eigener Stack `s2s` (eigene Pipeline, nicht über `AZURE_OPENAI_DEPLOYMENT`
   austauschbar).
3. Zerschnittene Clips klären (§6), bevor Absolutwerte mit früheren Messungen verglichen werden.
4. Bei Interesse an `nano`: Rollentreue prüfen (Phase-0-Schritt 10), Läufe wiederholen, um den
   TTS-Effekt aus §5.2 von Zufall zu trennen.
