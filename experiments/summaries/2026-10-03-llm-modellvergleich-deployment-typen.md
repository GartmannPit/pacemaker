# LLM-Modellvergleich, Azure-Deployment-Typen und Realtime-Stack

**Datum:** 2026-10-03, Neumessung mit bereinigten Test-Clips 2026-10-04 (§11)
**Stacks:** `azure-eu` (Azure AI Speech STT/TTS + Azure OpenAI) und neu `s2s` (Azure OpenAI
Realtime, §9), Pipecat 1.8.1, Python 3.12.15
**Messrechner:** Windows-Desktop (`DESKTOP-C60J786`), **nicht** der Mac der Messungen vom
2026-09-06/07 und nicht die EU-Mess-VM
> **Vorbehalt (2026-10-04):** Alle Läufe in §4–§9 liefen mit Test-Clips, die in mehrere
> Turns zerfielen (§6). Dadurch fehlten gerade die Messwerte langsamer Antworten — beim
> Realtime-Stack bis zu 22 % der Turns. **Belastbar sind die Werte aus §11.** Die älteren Werte
> bleiben untereinander vergleichbar und zur Nachvollziehbarkeit stehen.

**Vorgeschichte:** [`docs/2026-09-07-ueberblick-azure-eu-optimierung.md`](../../docs/2026-09-07-ueberblick-azure-eu-optimierung.md)

---

## 1. Fragestellungen

1. Bringt die Migration auf die EU-Mess-VM (Hetzner) einen relevanten Latenzgewinn? (bisher als
   größter Einzelhebel eingestuft)
2. Ändert ein anderes LLM-Modell die Latenz — konkret: Ist `gpt-4.1-nano` schneller als
   `gpt-4.1-mini`?
3. Welchen Einfluss hat der Azure-Deployment-Typ?
4. Ist ein Speech-to-Speech-Modell (Azure OpenAI Realtime) schneller als die Kaskade? (§9)

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
- ~~Ursache offen~~ **Ursache geklärt (2026-10-04):** Die Azure-TTS-Clips enthielten an der
  Satzgrenze bis zu **1060 ms** Pause (alter Opener) — weit über der VAD-Stopp-Schwelle von
  200 ms. Smart Turn wertete den ersten Satz dann zu Recht als vollständig.
- **Verzerrung größer als zunächst angenommen:** Beginnt der zweite Teil, bevor die Persona auf
  den ersten geantwortet hat, entsteht für den ersten Teil kein Messwert. Es fallen also gerade
  langsame Antworten heraus — p90 wird zu günstig. Erkannte User-Turns ohne Messwert:
  `mini`/`nano` je 2 von 46 (4 %), Realtime 13 von 58 (22 %) bzw. 9 von 54 (17 %). Bei
  Realtime mehr, weil die Turn-Erkennung ohne STT nicht auf ein Transkript wartet und früher
  schneidet.
- Behoben und neu gemessen in §11.

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

## 9. Realtime-Stack (`s2s`, Stack D)

### 9.1 Aufbau

- `gpt-realtime-2.1` als **Data Zone Standard (EU)**. `gpt-realtime-mini` war nur als Global
  Standard verfügbar und kam deshalb nicht infrage.
- Pipecats `AzureRealtimeLLMService` über die v1-Realtime-API (`wss://…/openai/v1/realtime`).
  Kein separates STT/TTS: Das Modell nimmt Audio entgegen und antwortet mit Audio. Stimme `cedar`.
- **Turn-Erkennung bleibt lokal** (Silero VAD + Smart Turn wie bei `azure-eu`), serverseitige
  Turn-Detection ist abgeschaltet (`turn_detection=False`). Pipecat schickt bei lokalem Turn-Ende
  selbst `input_audio_buffer.commit` + `response.create`. Damit beginnt die E2E-Messung am selben
  Punkt wie beim kaskadierten Stack — die Werte sind direkt vergleichbar.
- Neue Konfiguration: `AZURE_OPENAI_REALTIME_ENDPOINT`, `_API_KEY` (optional, sonst
  `AZURE_OPENAI_API_KEY`), `_DEPLOYMENT`, `_VOICE`, `_REASONING_EFFORT`. Die Reasoning-Stufe
  wird in `llm_model` mitgeschrieben, z. B. `gpt-realtime-2.1 (reasoning=minimal)`.

Beim Aufbau gelöste Probleme:

| Problem | Ursache | Lösung |
|---|---|---|
| Realtime-API lehnt Audio ab | API nimmt PCM nur mit 24 kHz, Pipeline/VAD/Fixtures arbeiten mit 16 kHz | `audio_resampler.py`: resampelt hinter dem User-Aggregator (VAD sieht weiter 16 kHz), direkt vor dem LLM. Ausgangsseitig resampelt der Output-Transport selbst |
| Keine einzige Bot-Antwort, nach ~50 s `keepalive ping timeout` | Der Stream-Resampler liefert anfangs leere Bytes; die API meldet leeres Audio als Fehler, und Pipecat beendet nach **jedem** API-Fehler die Empfangsschleife | Leere Frames im Resampler verwerfen |
| Persona würde nicht greifen | Bei `turn_detection=False` erreicht kein `LLMContextFrame` den Service — der System-Prompt aus dem Kontext käme nie an | System-Prompt direkt als `system_instruction` in die Session-Konfiguration (`build_stack(..., system_prompt=...)`) |

### 9.2 Ergebnisse

| Stack / Modell | E2E p50 | E2E p90 | E2E p95 | Turn-Det. p50 | Antwortzeit* p50 / p90 | < 900 ms | n |
|---|--:|--:|--:|--:|--:|--:|--:|
| `azure-eu` / `gpt-4.1-mini` | 1413 | 1656 | 1696 | 539 | ~874 / – | – | 44 |
| `azure-eu` / `gpt-4.1-nano` | 1369 | 1533 | 1552 | 535 | ~834 / – | – | 44 |
| `s2s` / `gpt-realtime-2.1` (Reasoning: Server-Default) | 1247 | 1375 | 1443 | 290 | 951 / 1085 | 2 / 45 | 45 |
| `s2s` / `gpt-realtime-2.1` (Reasoning: `minimal`) | **1126** | **1254** | **1278** | 288 | **813 / 955** | 3 / 45 | 45 |

Alle Werte in ms, alle Data Zone Standard (EU). *Antwortzeit = E2E − Turn-Detection; beim
kaskadierten Stack LLM + TTS (+ Satz-Aggregation), bei `s2s` das Modell allein. Pipecat erfasst
bei lokal gesteuerten Turns keine LLM-TTFB für den Realtime-Service, daher keine eigene Spalte.

**Akzeptanzkriterium p90 < 900 ms: alle FAIL.** Beide Realtime-Läufe ohne Fehler.

### 9.3 Befunde

1. **Der Vorsprung von Realtime kommt aus der Turn-Detection, nicht aus dem Modell.** Ohne Warten
   auf die Azure-Transkription sinkt sie von ~537 auf ~290 ms. Damit ist erstmals direkt
   gemessen, was das Warten auf Azure STT kostet: **~245 ms pro Turn**.
2. **Das Realtime-Modell antwortet nicht schneller als LLM + TTS der Kaskade.** Mit
   Server-Default-Reasoning ~950 ms bis zum ersten Audio, gegenüber ~870 ms für LLM + TTS bei
   `gpt-4.1-mini`.
3. **`reasoning=minimal` spart ~120 ms** (Antwortzeit p50 951 → 813 ms). Erklärt einen Teil, aber
   nicht den Großteil der Antwortzeit.
4. **900 ms p90 sind mit keiner getesteten Azure-Variante erreichbar.** Selbst Realtime mit
   `minimal` bräuchte bei ~290 ms Turn-Detection eine Antwortzeit von ~600 ms p90 (gemessen: 955).
5. **Für die Kaskade folgt:** Ein schnelleres STT ist der größte verbleibende Hebel. Rechnerisch
   (−245 ms) läge `gpt-4.1-mini` bei E2E p50 ~1170 ms — weiterhin über Budget.

### 9.4 Kosten

Pro Realtime-Lauf (30 Turns, 54–58 Antworten inkl. durch zerschnittene Clips abgebrochener):
~108.000 Prompt-Tokens (davon ~36.000 Audio-Input, großteils gecacht) und ~10.000–11.000
Completion-Tokens (davon ~7.000–7.700 Audio-Output). Nach Listenpreisen von `gpt-realtime`
**~1 $ pro Lauf**, also rund 50-mal so teuer wie ein Lauf mit `gpt-4.1-mini`. Preise für 2.1 in
Azure nicht verifiziert.

### 9.5 Offene Punkte

- **Persona nicht verifiziert:** Ob das Modell auf Deutsch und in der Rolle antwortet, ist ungeprüft
  (kein Mitschnitt der Bot-Antworten). Nachgewiesen ist nur, dass der System-Prompt ankommt
  (~500 Prompt-Tokens im ersten Turn). Gilt besonders für `minimal`, das die Rollentreue
  verschlechtern könnte.
- **Keine Nutzer-Transkription:** Ohne separates STT entsteht kein Transkript der SDR-Äußerungen.
  Für Latenzmessung irrelevant, für späteres Scoring nötig (Realtime-Transkription oder separates
  STT).
- **Compliance:** Das Modell verarbeitet Rohaudio. Kein Emotions-Score, aber vor einem Einsatz im
  Produktpfad bewusst gegen „keine Prosodie-Analyse" (`CLAUDE.md`) prüfen. Für Messläufe mit
  synthetischen Clips unkritisch.

## 10. Nächste Schritte

1. ~~**Stack A (US-Baseline) als markierten Referenzlauf** messen~~ — erledigt, siehe §12: Erreicht die Pipeline mit den
   schnellsten Anbietern überhaupt < 900 ms p90? Wenn nein, liegt die Grenze in der Architektur
   bzw. im Budget, nicht bei Azure.
2. ~~Bot-Antworten mitschneiden~~ — erledigt 2026-10-04 (§11.1).
3. **STT einzeln tauschen** (EU-Anbieter mit schneller Finalisierung) — größter Hebel der Kaskade
   laut §9.3.
4. ~~Zerschnittene Clips klären~~ — erledigt 2026-10-04 (§6, §11).
5. Optional: weiteres Nicht-Realtime-Modell für den Qualitätsvergleich (für die Latenz laut §5.1
   wenig Erkenntnisgewinn).
6. **Tail-Latenz des Realtime-Stacks** untersuchen (§11.3): Ausreißer von 1,8–3,0 s, gehäuft
   im letzten Drittel des Gesprächs. Wiederholungslauf, um Zufall von wachsendem Kontext zu
   trennen.

## 11. Neumessung mit bereinigten Test-Clips (2026-10-04)

### 11.1 Änderungen an der Messkette

| Änderung | Datei | Zweck |
|---|---|---|
| Jeder Clip ist genau **ein Satz**, echte Umlaute, keine Komma-Pause nach vollständigem Satzteil | `tests/generate_fixtures.py` | Kein Zerfall in mehrere Turns. Nebenbei: „Dreißig Sekunden: …" wurde von Azure STT als „30 neue Vertriebler" erkannt und ist ersetzt |
| **Pausenprüfung** beim Erzeugen: Abbruch, wenn die längste interne Pause ≥ `VAD_STOP_SECS` (200 ms) ist | `tests/generate_fixtures.py` | Problem kann nicht unbemerkt zurückkehren. Neue Clips: max. 50–120 ms. Gegenprobe alter Opener: 1060 ms |
| Synthetischer Ausgang spielt Audio **in Echtzeit** ab | `tests/synthetic_transport.py` | Vorher war der Bot nach Sekundenbruchteilen „fertig", Pipecat gab den Text aber im Sprechtempo frei — der nächste Clip markierte Antworten als unterbrochen und kürzte sie im Gesprächsverlauf. E2E-Messung (bis erstes Audio) davon unberührt |
| Nächster Clip erst nach **1 s ununterbrochener Bot-Stille** | `tests/synthetic_caller.py` | Lücken zwischen Antwort-Schüben (Realtime) lösen keinen Clip mehr aus |
| **Turn-Bilanz** am Ende jedes Laufs (Clips / erkannte Turns / Messwerte), Warnung bei Abweichung | `tests/synthetic_caller.py` | Verzerrung wird sofort sichtbar |
| **Transkript** pro Lauf (`experiments/runs/transcripts/`) | `metrics/transcript.py`, `pipeline.py` | Sprache und Rollentreue prüfbar |

Die alten Läufe liegen in `experiments/runs/_fixtures-v1/`.

### 11.2 Ergebnisse

`mini` und Realtime: Turn-Bilanz **30 / 30 / 30**, keine unterbrochene oder leere Bot-Antwort,
keine Fehler. `nano`: 30 / 30 / **29** — siehe Befund 8.

| Stack / Modell | E2E p50 | E2E p90 | E2E p95 | max | Turn-Det. p50 | Antwortzeit* p50 / p90 | < 900 ms |
|---|--:|--:|--:|--:|--:|--:|--:|
| `azure-eu` / `gpt-4.1-mini` (Data Zone) | 1526 | **1632** | 1693 | 2127 | 531 | 940 / 1188 | 0 / 30 |
| `azure-eu` / `gpt-4.1-nano` (Data Zone) | 1361 | **1628** | 1721 | 2011 | 519 | 869 / 1035 | 0 / 29 |
| `s2s` / `gpt-realtime-2.1` (`minimal`) | **1208** | 2048 | 2330 | 2961 | 292 | 906 / 1755 | 0 / 30 |

Alle Werte in ms. *Antwortzeit = E2E − Turn-Detection. Kaskade: LLM TTFB p50 424 ms (`mini`)
bzw. 415 ms (`nano`), TTS TTFB p50 326 bzw. 290 ms.

Vergleich mit den verzerrten Werten (§4, §9):

| | E2E p50 alt → neu | E2E p90 alt → neu |
|---|--:|--:|
| `gpt-4.1-mini` | 1413 → 1526 | 1656 → 1632 |
| `gpt-4.1-nano` | 1369 → 1361 | 1533 → 1628 |
| Realtime `minimal` | 1126 → 1208 | **1254 → 2048** |

### 11.3 Befunde

1. **Die Verzerrung hat den Realtime-Stack massiv geschönt.** p90 steigt von 1254 auf
   **2048 ms**. Bei der Kaskade bleibt p90 praktisch gleich (1656 → 1632) — dort fehlten nur
   4 % der Messwerte.
2. **Realtime ist im Median schneller, im p90 deutlich langsamer.** p50 1208 vs. 1526 ms, aber
   p90 2048 vs. 1632 ms. Das Akzeptanzkriterium ist p90 — dort liegt die **Kaskade vorn**.
3. **Realtime hat einen schweren Tail.** Fünf von 30 Antworten brauchen 1,8–3,0 s (Turns 12,
   21, 23, 27, 30), nicht an bestimmte Clips gebunden, gehäuft im letzten Drittel. Mögliche
   Ursachen: Schwankung auf Serverseite (Data Zone), wachsender Audio-Kontext. Bei n = 30
   bestimmen drei Werte das p90 — Wiederholungslauf nötig.
4. **Die Kaskade ist stabil.** `gpt-4.1-mini` streut kaum (p90 − p50 ≈ 100 ms), auch über die
   Messung mit verzerrten Clips hinweg.
5. **Der Turn-Detection-Vorteil von Realtime ist echt** (292 vs. 531 ms, pro Messung erfasst),
   wird aber vom Antwort-Tail mehr als aufgezehrt.
6. **Persona:** In beiden Läufen alle 30 Antworten vollständig im Transkript, auf Deutsch und in
   der Rolle (Stichprobe von je 6 Antworten gelesen, keine systematische Bewertung). Auffällig:
   Die Clips wiederholen sich alle 10 Turns. `gpt-4.1-mini` begrüßt beim zweiten Opener erneut
   („Hallo Frau Fischer …"), Realtime reagiert zunehmend ungeduldig bis zum angekündigten
   Gesprächsabbruch — passend zur Geduldsschwelle der Persona. Realtime-Antworten sind zudem
   länger. Für einen Qualitätsvergleich braucht es ein Skript ohne Wiederholungen.
7. **Weiterhin kein Stack unter 900 ms p90.** Beste Werte: Kaskade mit `gpt-4.1-nano` (1628 ms)
   und `gpt-4.1-mini` (1632 ms) — gleichauf.
8. **`nano` ist bei p90 nicht schneller als `mini`.** Der frühere Vorsprung (1533 vs. 1656 ms)
   war Teil der Verzerrung bzw. Zufall. Im Median ist `nano` ~165 ms schneller, vor allem durch
   etwas kürzere TTS-Zeit. Das bestätigt §5.1: Die Modellgröße ist kein relevanter Hebel.
9. **Sporadischer TTS-Ausfall:** In Turn 8 des `nano`-Laufs lieferte Azure TTS für einen
   normalen Satz nach 3 s kein Audio (`completed with no audio`) — die Persona blieb in diesem
   Turn stumm, der Messwert fehlt. Für das Produkt relevant (stumme Persona im Gespräch); im
   Auge behalten, ob es wiederkehrt.
10. **Persona bei `nano`:** Auf Deutsch und in der Rolle, wirkt aber eintöniger — viele
    Antworten wiederholen „wie gesagt … schicken Sie mir eine Mail". Stichprobe, keine
    systematische Bewertung.

### 11.4 Tokenverbrauch

| Lauf | Prompt-Tokens (davon gecacht) | Completion-Tokens |
|---|--:|--:|
| `gpt-4.1-mini` | 37.105 (25.088) | 697 |
| `gpt-4.1-nano` | 38.972 (24.704) | 885 |
| Realtime `minimal` | 60.616 (55.104, davon 19.328 Audio) | 8.191 (davon 6.070 Audio) |

Mit sauberen Clips gibt es 30 statt 44–58 LLM-Aufrufe; der Verbrauch sinkt entsprechend
(Realtime grob ~0,6 $ pro Lauf).

## 12. Stack A — US-Baseline (2026-10-04, Referenz, nicht EU-konform)

> **Nur Referenz.** Deepgram, OpenAI und ElevenLabs verarbeiten in den USA. Ausschließlich
> synthetische Test-Clips, keine echten Stimmen. Nie Produktpfad (`CLAUDE.md`).

### 12.1 Aufbau

Deepgram Nova-3 (`de`, `mip_opt_out`) → OpenAI `gpt-4.1-mini` (direkt, gleiches Modell wie
`azure-eu`) → ElevenLabs Flash v2.5. Setup: [`docs/phase-0-setup-stack-a.md`](../../docs/phase-0-setup-stack-a.md).

| Problem im Probelauf | Ursache | Lösung |
|---|---|---|
| ElevenLabs liefert kein Audio, nach 3 Fehlschlägen wird der Dienst stillgelegt | HTTP 402: *„Free users cannot use library voices via the API"* — gewählte Stimme stammt aus der Community-Bibliothek | Für die Messung vorinstallierte Stimme „Eric" (`cjVigY5qzO86Huf0OWal`), nur per Umgebungsvariable für den Lauf. Spricht über Flash v2.5 Deutsch, ist aber englischsprachig angelegt |
| Persona bekommt nur die erste Hälfte der Äußerung, Rest startet einen Schein-Turn, LLM-Anfrage wird abgebrochen (3 Clips → 5 Turns, unplausible LLM-TTFB 7–18 ms) | Pipecat beendet den Turn bei Smart-Turn-COMPLETE + Transkript, sobald die STT-Sicherheitsfrist (aus Pipecats Default `DEEPGRAM_TTFS_P99`) abgelaufen ist. Deepgrams Finalize-Antwort brauchte von hier 0,35–0,9 s — länger als die Frist | `ttfs_p99_latency=1.0` (Frist nur noch Sicherheitsnetz; der Turn endet sofort mit dem finalisierten Transkript) und `endpointing=False` (keine Teil-Finals nach ~10 ms Stille). Danach 5/5/5 bzw. 30/30/30 |

### 12.2 Ergebnisse

Turn-Bilanz **30 / 30 / 30**, keine unterbrochene Antwort, keine Fehler.

| Stack | E2E p50 | E2E p90 | E2E p95 | max | Turn-Det. p50 | LLM TTFB p50 / p90 | TTS TTFB p50 / p90 |
|---|--:|--:|--:|--:|--:|--:|--:|
| **A — US-Baseline** | **1224** | **1501** | 1800 | 1908 | **414** | 600 / 756 | **140 / 165** |
| `azure-eu` / `gpt-4.1-mini` | 1526 | 1632 | 1693 | 2127 | 531 | **424 / 494** | 326 / 452 |
| `azure-eu` / `gpt-4.1-nano` | 1361 | 1628 | 1721 | 2011 | 519 | 415 / 477 | 290 / 468 |
| `s2s` Realtime `minimal` | 1208 | 2048 | 2330 | 2961 | 292 | – | – |

Alle Werte in ms, alle mit bereinigten Clips (§11). **Akzeptanzkriterium p90 < 900 ms: alle FAIL**,
auch Stack A (kein einziger Turn unter 900 ms, Minimum 1071 ms).

### 12.3 Befunde

1. **Mit den damals getesteten Konfigurationen wurden 900 ms p90 nicht erreicht — auch nicht
   mit den schnellsten US-Anbietern** (1501 ms p90). *(Korrigiert 2026-10-07: ursprünglich
   „unabhängig vom Anbieter nicht erreichbar"; das war überdehnt — wenige Stunden später lag
   p90 bei 1153 ms, §13.)*
2. **Beobachteter Unterschied der beiden Stacks: ~130 ms p90** (1632 vs. 1501 ms) bzw. ~300 ms
   p50. *(Korrigiert 2026-10-07: ursprünglich „EU-Aufpreis". STT, TTS, Routing und
   Einstellungen unterscheiden sich zugleich — ein isolierter Effekt der EU-Datenresidenz lässt
   sich daraus nicht ableiten.)*
   Für die Phase-0-Frage „Was kostet EU-Datenresidenz?" ist das die bezifferte Antwort
   (`phase-0-proof-of-concept.md` §2, Compliance-Kriterium).
3. **Wo Stack A schneller ist:**
   - **TTS:** ElevenLabs 140 ms vs. Azure 326 ms p50 — größter Einzelvorteil (~185 ms).
   - **Turn-Detection:** 414 vs. 531 ms (~115 ms) — Deepgram finalisiert schneller als Azure STT.
4. **Wo Stack A langsamer ist: LLM.** OpenAI direkt (US) 600 ms vs. Azure OpenAI EU 424 ms p50 —
   die Strecke in die USA kostet ~175 ms. Für ein EU-Produkt ist Azure OpenAI EU hier sogar der
   bessere Baustein.
5. **Rechnerische Bestkombination** aus gemessenen Bausteinen: Turn-Detection ~414 (schnelles STT)
   + LLM ~424 (Azure EU) + TTS ~140 (schnelles TTS) ≈ **~1000 ms p50** plus Pipeline-Overhead —
   weiterhin über 900 ms, und das im Median, nicht im p90.
6. **Verbleibender großer Block ist die Turn-Erkennung** (~290–530 ms je nach Stack). Darin
   stecken VAD-Stopp (200 ms), Smart-Turn-Inferenz und das Warten aufs Transkript. Selbst ohne
   STT-Wartezeit (Realtime) bleiben ~290 ms.
7. **STT-Qualität Deepgram:** Vereinzelt doppelte Wörter („Kost Kosten", „nächste nächste") und
   „Brand" statt „Brandt" — inhaltlich unkritisch, für Scoring aber relevant.

### 12.4 Konsequenz für Phase 0

Das Akzeptanzkriterium „≥ 1 EU-Stack mit p90 < 900 ms" ist mit kaskadierter Architektur und
heutigen Anbietern nicht erfüllbar — auch nicht mit US-Anbietern. Optionen (Entscheidung offen):

- **Architektur-Hebel prüfen:** LLM-Anfrage spekulativ schon auf Zwischentranskripte starten,
  VAD-Stopp/Smart-Turn feiner einstellen, kurze Bestätigungslaute („Mhm") aus einem Cache
  sofort abspielen (verkürzt die wahrgenommene, nicht die gemessene Latenz — Definition klären).
- **EU-Bausteine mischen:** schnelleres EU-STT + Azure OpenAI EU + schnelleres EU-TTS. Laut §12.3
  liegt das Potenzial bei rund 300–400 ms gegenüber `azure-eu`.
- **Budget überprüfen:** Ob 900 ms p90 die richtige Schwelle für ein Trainingsszenario ist —
  ggf. mit echten Testgesprächen bewerten, ab welcher Latenz das Gespräch unnatürlich wirkt.

## 13. Pipeline-Optimierung (2026-10-04)

Ziel: mit Eingriffen an der Pipeline das 900-ms-Kriterium erreichen, ohne die Schwelle zu
ändern (Begründung der Schwelle: [`docs/2026-10-04-recherche-latenzbudget.md`](../../docs/2026-10-04-recherche-latenzbudget.md)).
Alle Läufe `azure-eu`, 30 Turns, bereinigte Clips, Turn-Bilanz jeweils 30/30/30.

### 13.1 Zerlegung der Antwortzeit (Ausgangslage `gpt-4.1-mini`)

| Abschnitt (ab Turn-Ende) | p50 | p90 |
|---|--:|--:|
| → erstes LLM-Paket | 426 | 495 |
| erstes Paket → erster Satz fertig (TTS startet) | 176 | 217 |
| TTS-Start → erstes Audio | 330 | 457 |

Davor ~531 ms Turn-Erkennung. Die vorher nicht zugeordneten ~245 ms (E2E − Turn − LLM − TTS)
waren die Zeit bis zum ersten vollständigen Satz.

### 13.2 Experimente

| # | Änderung | Ort |
|---|---|---|
| E1 | Persona beginnt jeden Redebeitrag mit einem kurzen Satz aus 1–4 Wörtern („Hm, nee." / „Moment mal." / „Ach so.") | `personas/kaltakquise_head_of_ops.py` |
| E2 | Azure-Inhaltsfilter im Streaming-Modus **„Asynchronous Filter"** statt Default | Azure-Portal (Foundry classic → Guardrails + controls → Content filters → Output filter → Streaming mode), Filter `Asynchronus_Filtering` |
| E3 | Azure-STT-Segmentierung 200 → **100 ms** | `stacks.py` (`AZURE_STT_SEGMENTATION_MS`, neuer Default 100) |

### 13.3 Ergebnisse

| Lauf | E2E p50 | E2E p90 | Turn | → LLM | → Satz | → Audio | Wörter 1. Satz |
|---|--:|--:|--:|--:|--:|--:|--:|
| Referenz `mini` | 1526 | 1632 | 531 | 426 | 176 | 330 | 10 |
| Referenz `nano` | 1361 | 1628 | 519 | 418 | 140 | 293 | 8 |
| `mini` + E1 | 1378 | 1537 | 521 | 439 | 193 | 216 | 2 |
| `mini` + E1 + E3 | 1328 | 1556 | 399 | 417 | 178 | 283 | 5 |
| **`nano` + E1 + E2 + E3** | **1043** | **1153** | 391 | 408 | **14** | 205 | 2 |
| US-Baseline (Stack A, §12) | 1224 | 1501 | 414 | 604 | 64 | 144 | 9 |

Alle Werte in ms (Teilschritte p50). Bester Lauf: kein Turn < 900 ms, Minimum 938 ms, Maximum 1896 ms.

### 13.4 Befunde

1. **E2 (asynchroner Inhaltsfilter) ist der größte Einzelhebel.** Direktmessung gegen die API
   (`gpt-4.1-nano`, je 4 Anfragen): Standardfilter erster Text 593 ms, alle Textpakete auf einmal
   (Abstand 0,2 ms); asynchroner Filter erster Text **327 ms**, Token für Token (Abstand 2,8 ms).
   Im Default-Modus hält Azure die komplette Antwort bis zur Filterprüfung zurück. Pipecats
   „LLM TTFB" misst dabei das erste, **leere** Paket und verschleiert diese Wartezeit.
2. **E1 wirkt über die kürzere TTS-Zeit** (330 → 216 ms bei 2 statt 10 Wörtern), nicht über
   schnelleres Schreiben — solange der Filter puffert, kommt der Text ohnehin auf einmal. Erst
   zusammen mit E2 fällt auch die Wartezeit bis zum ersten Satz weg (176 → 14 ms).
3. **E3 spart ~120 ms Turn-Erkennung** (521 → 399 ms). Alle 30 Nutzer-Äußerungen kamen
   vollständig an. Die 2026-09 beobachtete Zerstückelung bei 100 ms ist damit für saubere
   Ein-Satz-Clips widerlegt; für echte Sprache mit Denkpausen und Korrekturen ist sie offen
   *(präzisiert 2026-10-07)*.
4. **Der EU-Stack ist jetzt schneller als die US-Referenz** (p90 1153 vs. 1501 ms) — obwohl die
   US-Referenz die schnelleren STT/TTS-Anbieter hat. Ein Teil der Referenz-Werte ist aber nicht
   optimiert (E1/E2 wurden dort nicht angewendet; OpenAI direkt puffert ohnehin nicht).
5. **Bis 900 ms p90 fehlen ~250 ms.** Verbleibende Blöcke (p50): Turn-Erkennung ~390, LLM bis
   erstes Paket ~410, TTS ~205.
6. **`gpt-4.1-mini` noch ohne E2 gemessen:** Der asynchrone Filter ist laut Portal zugeordnet,
   wirkte bei der Direktmessung aber noch nicht (auch nicht per Header `x-policy-id`). Vermutlich
   Verzögerung bei Azure; erneut prüfen.
7. **Persona mit E1:** natürlich und variiert („Hm, ja. Ich hab ehrlich gesagt keine drei
   Minuten …", „Naja. Das ist bei uns intern geregelt …"). Vereinzelt unpassend („Ja, und? Kein
   Ding, danke für den Anruf."). Stichprobe, keine systematische Bewertung.

### 13.5 Compliance-Hinweis zu E2

Im asynchronen Modus kann problematischer Inhalt ausgeliefert werden, bevor der Filter ihn
markiert; das Filtersignal kommt spätestens nach ~1.000 Zeichen. Für eine Trainings-Persona mit
festem System-Prompt vertretbar; vor dem Produktpfad bewusst entscheiden und ggf. eine
Behandlung des nachträglichen Filtersignals (`finish_reason: content_filter`) einbauen.

### 13.6 Weitere Experimente und Messstabilität (2026-10-04 abends)

| Uhrzeit | Lauf (`nano`, E1–E3 als Basis) | E2E p50 | E2E p90 | Turn | LLM | TTS |
|---|---|--:|--:|--:|--:|--:|
| 20:23 | E1+E2+E3 | 1043 | 1153 | 391 | 408 | 205 |
| 20:32 | + E4: VAD-Stopp 200 → 100 ms | 1167 | 1756 | 431 | 450 | 217 |
| 20:42 | + E5: Aufwärmen beim Start (Lauf 1) | 1538 | 1841 | 412 | 588 | 388 |
| 20:50 | + E5: Aufwärmen (Lauf 2) | 1648 | 2178 | 473 | 682 | 456 |

**Netzwerk-RTT zu Azure** (`infra/rtt-check.sh`, 20 Samples): 2026-10-03 STT/TTS ~23 ms;
**2026-10-04 18:58 UTC: STT 48, TTS 64, Azure OpenAI 84 ms** — zwei- bis viermal so hoch.

Befunde:

1. **Die Läufe ab 20:32 sind nicht verwertbar.** LLM und TTS werden gleichzeitig und stetig
   langsamer, unabhängig von der jeweiligen Änderung; die gestiegene Netzwerklaufzeit der
   Entwicklungsleitung ist ein plausibler Mitverursacher; TCP-RTT trennt aber nicht Last bei
   Azure, Warteschlangen und Verbindungseffekte — die Ursache ist nicht vollständig
   nachgewiesen *(präzisiert 2026-10-07)*. E4 und E5 sind damit **offen**, nicht widerlegt.
2. **E4 (VAD 100 ms) vermutlich ohne Nutzen:** Die Turn-Erkennung sank nicht (391 → 431 ms) —
   bei `azure-eu` bestimmt das Warten auf das finale Azure-Transkript das Turn-Ende, nicht die
   VAD. Default bleibt 200 ms (`PACEMAKER_VAD_STOP_SECS` für Experimente).
3. **E5 (Aufwärmen) wirkt auf den ersten Turn:** LLM-TTFB im ersten Turn 449 / 641 ms statt
   ~1000 ms ohne Aufwärmen (Kaltstart in allen früheren Läufen). Bleibt aktiv
   (`PACEMAKER_WARM_UP=0` schaltet ab). Effekt auf p90 unter stabilen Bedingungen nachmessen.
4. **Korrektur zu §2:** Die VM-Migration war dort als „kein Haupthebel" eingestuft (−50 ms bei
   stabiler Leitung). Der Abend zeigt: Die Entwicklungsleitung schwankt so stark, dass sie
   Optimierungen von 100–300 ms überdeckt. Die EU-Mess-VM ist damit **Voraussetzung für
   belastbare Vergleiche**, nicht nur Latenzhebel.
5. **Bester belastbarer Wert bleibt E1+E2+E3 mit `nano`: p90 1153 ms** (20:23, Netzwerkzustand
   zu dem Zeitpunkt nicht gemessen — mit Vorbehalt, Wiederholung unter stabilen Bedingungen
   nötig).

### 13.7 Nächste Schritte

1. **Messbedingungen stabilisieren:** EU-Mess-VM (Hetzner) aufsetzen; bis dahin vor und nach
   jedem Lauf `infra/rtt-check.sh` und Läufe mit RTT-Ausreißern verwerfen.
2. **Beste Konfiguration (E1+E2+E3+E5) mehrfach messen** (≥ 3 Läufe), um die Streuung zu kennen.
3. `gpt-4.1-mini` mit asynchronem Filter nachmessen. Der Filter greift dort inzwischen
   (Direktmessung 2026-10-04 ~21:05: Paketabstand 2,3 ms, erster Text = erstes Paket); die
   Umstellung im Portal brauchte bei Azure offenbar längere Zeit, bis sie wirkte.
4. Verbleibende Hebel: Eingangsfilter / Prompt Shields von Azure (prüfen, ob die synchrone
   Prüfung der Eingabe Zeit kostet), schnelleres EU-TTS als Azure (~205 ms).

## 14. Messreihe auf der EU-Mess-VM (2026-10-07)

Erste Messung unter stabilen Netzwerkbedingungen. Hetzner Cloud (Deutschland), `infra/messreihe.sh`:
`mini` und `nano` abwechselnd, je 3 Läufe à 30 Turns, RTT vor und nach jedem Lauf. Gleiche
Konfiguration für beide: E1 (kurzer Einstieg), E2 (asynchroner Inhaltsfilter, bei beiden per
Direktmessung bestätigt), E3 (Segmentierung 100 ms), E5 (Aufwärmen), VAD 200 ms.

| Lauf | p50 | p90 | p95 | max | 1. Turn | < 900 ms | Turn | LLM | TTS | RTT Speech / OpenAI |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| `mini`-1 | 1119 | 1317 | 1394 | 1648 | 1223 | 2 | 380 | 402 | 220 | 4,8 / 28,3 |
| `nano`-1 | 924 | 1103 | 1170 | 1407 | 931 | 12 | 347 | 355 | 128 | 4,8 / 28,9 |
| `mini`-2 | 1068 | 1324 | 1374 | 1628 | 1273 | 4 | 359 | 372 | 209 | 4,8 / 28,2 |
| `nano`-2 | 892 | 1014 | 1071 | 1146 | 990 | 16 | 360 | 367 | 105 | 5,0 / 28,0 |
| `mini`-3 | 1043 | 1227 | 1237 | 1689 | 1070 | 9 | 361 | 377 | 159 | 6,2 / 29,0 |
| `nano`-3 | 899 | 1206 | 1230 | 1387 | 979 | 15 | 352 | 365 | 124 | 4,8 / 28,2 |

Werte in ms, Teilschritte p50. Alle Läufe Turn-Bilanz 30/30/30, keine Ausfälle. Jeder Lauf
einzeln ausgewertet (nicht gepoolt).

Befunde:

1. **RTT vor und nach jedem Lauf stabil** (Speech 4,8–6,2 ms, OpenAI 28–29 ms).
   Netzwerkeffekte innerhalb eines Laufs schließt das nicht aus; Dienstlast, Scheduling und
   Stichprobenstreuung sind mögliche Ursachen der Streuung *(präzisiert 2026-10-07)*.
2. **Streuung gleicher Konfiguration: p90 ±50–100 ms** (Spannweite `mini` 97 ms, `nano` 192 ms).
   Effekte in dieser Größenordnung brauchen mehrere Läufe; die Nachweisbarkeit hängt von
   Versuchsanordnung und Stichprobe ab, eine feste Grenze ist das nicht
   *(präzisiert 2026-10-07)*.
3. **`nano` bei gleicher Konfiguration durchgehend schneller als `mini`:** p50 ~150 ms, p90
   20–310 ms. Haupttreiber TTS (105–128 vs. 159–220 ms, vermutlich kürzere Einstiege), LLM nur
   10–30 ms. Korrigiert §5.1/§11.3 Befund 8, soweit sie „kein Modellvorteil" nahelegten — unter
   den damaligen Bedingungen (gepufferter Filter, Laptop) war keiner messbar.
4. **`nano`: p50 ~900 ms, p90 1014–1206 ms, bis 16/30 Turns < 900 ms.** Kriterium p90 < 900 ms
   weiterhin verfehlt (~100–300 ms).
5. **Kein auffälliger Erstturn-Nachteil mit Aufwärmen:** Erster Turn liegt in der normalen
   Verteilung; p90 mit/ohne Turn 1 gleich. Kausal belegt ist das nicht — ein Vergleichslauf
   ohne Aufwärmen auf der VM fehlt *(präzisiert 2026-10-07)*.
6. **Azure-OpenAI-Endpoint ~28 ms RTT** von der VM (Speech ~5 ms): Ressource vermutlich nicht in
   Frankfurt — offen.

Einschränkungen (siehe [Einordnung der Projektbewertung](../../docs/2026-10-07-einordnung-projektbewertung.md)):
Messung endet beim ersten Audio, häufig dem kurzen Einstieg — „Zeit bis zum Inhalt" noch nicht
erfasst. Reihenfolge immer `mini` vor `nano`. Saubere synthetische Clips mit Wiederholung alle
10 Turns.
