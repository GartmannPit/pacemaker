# Plausibilitätsprüfung: 10 Latenz-Ansätze ohne EU-VM-Migration

**Datum:** 2026-09-07
**Kontext:** Ergänzung zu [`2026-09-06-stack-b-azure-eu-baseline.md`](./2026-09-06-stack-b-azure-eu-baseline.md).
Prüft 10 vom Nutzer vorgeschlagene Ansätze gegen die tatsächliche Architektur (Pipecat 1.8.1,
Azure-Managed-APIs für STT/LLM/TTS, LiveKit/WebRTC-Transport) und die bereits gemessenen Ergebnisse
aus §4 der Baseline. **Reine Prüfung, keine Umsetzung** — Ausarbeitung folgt für die als plausibel
markierten Punkte.

**Zentrale Einschränkung, die für mehrere Punkte gilt:** Stack B nutzt ausschließlich
**Azure-Managed-APIs** (Azure AI Speech, Azure OpenAI). Wir haben keinen Zugriff auf
Modellgewichte, Sampling-internals, Serving-Infrastruktur oder GPU-Allokation — nur auf das, was
die jeweilige SDK/REST-Schnittstelle exponiert. Ansätze, die Zugriff auf diese Ebene voraussetzen
(Quantisierung, Speculative Decoding, LoRA/Prefix-Tuning), sind für Stack B **strukturell nicht
umsetzbar**, unabhängig davon, wie gut die Idee an sich ist. Sie wären erst bei einem
**self-hosted** Stack (Stack C, "sovereign") relevant.

---

## 1. Paralleles Streaming statt sequentiell

**Verdict: ⚠️ Teilweise bereits vorhanden, Kernidee bereits getestet und widerlegt**

- „TTS startet sofort mit erstem Token" = `TextAggregationMode.TOKEN`. Genau das haben wir am
  2026-09-06 per Code-Analyse geprüft und **verworfen** (siehe Baseline-Doku §4.3): Azure hat
  keine echte Token-Streaming-Synthese, jeder Chunk löst einen eigenen `SpeechSynthesizer`-Request
  aus → erwartbar abgehackte Sprache statt eines Latenzgewinns.
- „LLM beginnt Token-Stream parallel zu STT, sobald 2-3 Worte erkannt" = im Kern das, was wir mit
  `wait_for_transcript=False` bereits **empirisch getestet** haben (Baseline §4.1). Ergebnis war
  das Gegenteil der Erwartung: Turn-Detection-Latenz p50 1036→2648 ms. Der Mechanismus blieb
  ungeklärt, aber die Richtung war eindeutig negativ, nicht neutral.
- Was schon automatisch läuft, ohne dass wir es konfiguriert haben: Pipecats `TTSService` sendet
  standardmäßig satzweise an Azure TTS (`TextAggregationMode.SENTENCE`), sobald ein Satzende im
  LLM-Stream erkannt wird — bei einer mehrsätzigen Antwort synthetisiert Azure den ersten Satz
  bereits, während der zweite noch generiert wird. Der Spielraum dafür ist bei uns aber klein, weil
  der Persona-Prompt explizit „ein bis drei Sätze" vorschreibt und die meisten Antworten in der
  Praxis ein einzelner Satz sind (siehe Beispiel-Transkript im letzten Testlauf).

**Fazit:** Die zwei konkreten Hebel hinter diesem Punkt (früher an LLM, früher an TTS) haben wir
bereits mit echten Zahlen getestet — beide mit negativem statt dem behaupteten positiven Ergebnis.
Ohne neue Evidenz, die unsere eigenen Messungen widerlegt, ist der behauptete Gewinn
(„~300–400 ms") nicht plausibel für diesen Stack.

## 2. Speculative Decoding / Token-Prefetching

**Verdict: ❌ Nicht umsetzbar über Azure OpenAI Managed API**

Speculative Decoding im eigentlichen Sinn (Draft-Modell erzeugt Kandidaten-Tokens, Zielmodell
verifiziert sie in einem Batch-Forward-Pass) erfordert Zugriff auf Logits und die
Inferenz-Pipeline des Modells selbst. Azure OpenAI stellt nur eine Chat-Completions-Schnittstelle
bereit — kein Zugriff auf diese Ebene, unabhängig vom Deployment.

Die im Text tatsächlich beschriebene Variante („häufigste Antwort-Starts vorab generieren, Top-3
spekulativ") ist streng genommen kein Speculative Decoding, sondern eine Antwort-Cache-Heuristik —
das überschneidet sich mit Punkt 5 (TTS-Cache) und Punkt 9 (Edge-Caching), dort bewertet.
Zusätzliches Problem hier: Die Persona-Antwort hängt vom tatsächlichen Nutzer-Turn ab
(„Sprich jetzt als Markus Brandt" reagiert auf das, was der Anrufer gerade gesagt hat) — die
„ersten 20-30 Tokens" sind nicht unabhängig vom Gesprächsverlauf vorhersagbar, außer bei der
allerersten Reaktion auf sehr generische Opener.

## 3. VAD aggressiv tunen

**Verdict: ✅ Teilweise plausibel — aber größtenteils schon umgesetzt oder bereits eingepreist**

- „Streaming-VAD mit niedriger Schwelle": `SileroVADAnalyzer` läuft bereits mit
  `stop_secs=0.2` (Pipecat-Default, ungetestet ob niedriger sinnvoll wäre — echter offener Punkt).
- „Prediction-VAD, Nutzer spricht wahrscheinlich zu Ende": Das ist exakt das, was
  **Smart-Turn-v3** bereits tut — ein ML-Modell, das über reine Stille-Erkennung hinaus
  entscheidet, ob ein Turn semantisch abgeschlossen wirkt. Läuft bereits als Default-Stop-Strategie
  in unserer Pipeline (`TurnAnalyzerUserTurnStopStrategy(LocalSmartTurnAnalyzerV3())`).
- „Interrupt-Ready, TTS läuft aber VAD kann jederzeit unterbrechen": `allow_interruptions=True`
  ist bereits gesetzt (`pipeline.py`). Barge-in ist architektonisch vorhanden, aber **die Latenz
  dafür haben wir noch nie gemessen** (offener Punkt aus Baseline §5).
- Der größte Teil des hier behaupteten Gewinns („~200-300 ms") haben wir mit der
  `Speech_SegmentationSilenceTimeoutMs`-Anpassung (500→200 ms) bereits realisiert: Turn-Detection
  p50 1036→476 ms, also **560 ms**, mehr als hier veranschlagt.

**Was tatsächlich noch offen ist:** `SmartTurnParams` (stop_secs, pre_speech_ms) selbst haben wir
noch nicht angefasst — nur Azures serverseitigen STT-Parameter. Das ist der einzige in diesem
Punkt noch nicht geprüfte, echte Hebel.

## 4. LLM-Modellwahl & Quantisierung

**Verdict: ❌ Prämisse trifft auf unseren Stack nicht zu**

„Mistral 7B oder Llama 3.1 8B statt 70B" und „Quantisierung INT8 statt FP32" setzen ein
selbst-serviertes Modell voraus, bei dem wir Gewichte/Precision wählen. Wir nutzen
**`gpt-4.1-mini`** über Azure OpenAI — bereits die kleine, latenzoptimierte Modellklasse, nicht
das unterstellte 70B-Vergleichsmodell. Quantisierung ist auf einem Managed-API-Deployment nicht
konfigurierbar; Azure entscheidet über die Serving-Infrastruktur.

Gemessener LLM-TTFB liegt bei 444–557 ms (p50, zwei unabhängige Läufe) — das ist bereits ein
kleines/schnelles Modell. Ein noch kleineres Azure-OpenAI-Modell (falls in der Region verfügbar)
wäre ein legitimer, aber anderer Test als hier beschrieben — die Größenordnung „150-250 ms" ist
ohne konkretes Alternativ-Modell nicht verifizierbar.

## 5. TTS Time-to-First-Audio radikal senken

**Verdict: ⚠️ Gemischt — Provider-Wechsel ist Stack-C/A-Gebiet, lokaler Cache ist der einzige
wirklich neue, plausible Punkt in der ganzen Liste**

- „ElevenLabs, Cartesia, Deepgram TTS": Alle drei sind nicht-EU-Provider bzw. müssen einzeln auf
  EU-Region + AVV geprüft werden (harte Produkt-Constraint, `CLAUDE.md`). Das ist kein
  Parameter-Tuning an Stack B, sondern ein neuer Stack — deckt sich mit dem ohnehin offenen Punkt
  „zweiten Stack anbinden".
- „Neural Codec (Codec2, Eva)": Betrifft Übertragungsgröße/Bitrate, nicht Time-to-First-Byte der
  Synthese. Bei 16 kHz PCM sind wir ohnehin schon low-bitrate; ein anderer Codec ändert nicht, wie
  schnell Azure den ersten Audio-Frame erzeugt. Kein plausibler Hebel für **Latenz**.
- **„Local TTS-Cache für häufige Phrases": einzige neue Idee, die hier wirklich trägt.**
  Einschränkung: Die Persona antwortet reaktiv auf das, was der Anrufer sagt — es gibt aktuell
  keine wirklich fixen Bot-Sätze außer eventuell sehr kurzen Fragmenten. Trotzdem plausibel für
  einen kleinen, klar abgegrenzten Fall: Falls wir dem Trainer eine gescriptete Eröffnungszeile o.
  Ä. mitgeben, könnte deren Audio vorab synthetisiert und aus dem Cache gespielt werden —
  spart die volle TTS-TTFB (aktuell 474–499 ms p50) für diesen einen Turn komplett.
  **Reichweite ist aber klein** (ein bis wenige Turns pro Gespräch), kein struktureller Fix.

## 6. Systemprompt + Pre-Computed Context

**Verdict: ❌ Setzt Modellzugriff voraus, den wir nicht haben — und das eigentliche Problem ist
bereits gelöst, ohne dass wir es gebaut haben**

„Embedding vorkompilieren", „LoRA-Adapter/Prefix-Tuning statt Prompt" — erfordert Fine-Tuning-
bzw. Adapter-Zugriff auf ein selbst gehostetes Modell. Auf einem Azure-OpenAI-Deployment nicht
verfügbar.

„RAG-Wissensbasis minimal halten": Wir nutzen aktuell **kein RAG** — ein einziger fester
System-Prompt (~600 Tokens), kein Retrieval-Schritt. Der Punkt geht an der Architektur vorbei.

**Faktischer Fund aus dem letzten Testlauf-Log:** Azure OpenAI cached bereits automatisch:

```
AzureLLMService#0 prompt tokens: 1759, completion tokens: 11, cache read input tokens: 1664
```

1664 von 1759 Prompt-Tokens kamen aus dem Cache — Azures **eigenes** Prompt-Caching greift also
bereits, ganz ohne unser Zutun. Weiteres Kürzen des System-Prompts hätte damit vermutlich nur noch
einen Bruchteil des behaupteten Effekts, weil der teure Teil (wiederholter Kontext) schon
gecached wird.

## 7. Regional-Latenz optimieren

**Verdict: ⚠️ Ist im Kern die EU-VM-Migration, die der Nutzer explizit ausklammern wollte — Rest
ist bereits umgesetzt**

„Alles im selben Rechenzentrum (eu-central-1 / europe-west1)" ist inhaltlich identisch mit
Baseline-§6-Punkt 1 (EU-Mess-VM-Migration nach Hetzner/nahe `germanywestcentral`) — nur mit
anderen Cloud-Anbietern benannt. Da die Aufgabenstellung dieser Prüfung explizit „ohne
VM-Migration" war, würde eine Umsetzung dieses Punktes den selbst gesetzten Rahmen verlassen.

„WebRTC statt HTTP-Requests für Browser-Audio": **Bereits vorhanden.** LiveKit ist laut
`CLAUDE.md`-Tech-Stack von Anfang an WebRTC-basiert, kein HTTP-Polling. Kein neuer Hebel.

## 8. Adaptive Streaming & Fallback-Strategie

**Verdict: ❌ Verbessert P90-Konsistenz unter Stress, senkt aber nicht die Baseline-Latenz — und
fällt unter „nicht in Phase 0"**

„Quantisiertes Modell als Warm-Start" setzt wie Punkt 4 self-hosted Modelle voraus. Der Rest
(High-Latency-Fallback auf kleineres Modell/weniger Chunks bei langsamer Verbindung) ist
Resilienz-Engineering für Produktionsbetrieb — nützlich, aber laut `CLAUDE.md` („Nicht in
Phase 0": Produktionshärtung) explizit außerhalb des aktuellen Scopes, und würde unsere p50/p90
im Normalfall nicht verändern, nur den ungünstigen Ausreißerfall abfedern.

## 9. Caching & Memoization auf Edge

**Verdict: ❌ Widerspricht dem Produktzweck**

„Häufigste Nutzer-Inputs (Namen, Standard-Objekte, Preise) lokal abfangen, kein LLM-Call für
Wiederholungen" — Pacemaker ist ein **Trainingstool**, dessen Wert genau darin liegt, dass die
Persona inhaltlich auf das reagiert, was der SDR tatsächlich sagt. Ein Pattern-Match, der
„ähnliche" Eröffnungen auf eine gecachte generische Antwort abbildet, riskiert:

- Dass echte inhaltliche Unterschiede (z. B. eine schwächere vs. eine starke Eröffnung)
  ununterscheidbar werden — widerspricht dem Trainingszweck direkt.
- Trifft denselben Geist wie die Emotionserkennungs-Grenze in `CLAUDE.md` („Scoring nur über
  Gesprächsinhalt und -struktur"): Wenn Antworten nicht mehr inhaltsabhängig sind, verliert das
  Training seine Aussagekraft.

Für ~15-20 % „gesparte" Turns ist das Risiko einer entwerteten Trainingsqualität zu hoch — dieser
Punkt sollte nicht weiterverfolgt werden, unabhängig vom Latenzgewinn.

## 10. Audio-Normalisierung & VAD lokal im Browser

**Verdict: ⚠️ Adressiert nicht den gemessenen Engpass**

Client-seitige VAD (nur Sprachsegmente an den Server senden) spart Bandbreite, aber unser
gemessener Engpass ist nicht „Server wartet auf ankommendes Audio", sondern **wie lange Azure STT
braucht, um ein bereits eingetroffenes Segment zu finalisieren** (die
`Speech_SegmentationSilenceTimeoutMs`, die wir in §4.2 bereits optimiert haben). Client-seitiges
Vorschneiden ändert diese serverseitige Finalisierungszeit nicht. Zusätzliches Risiko: Azure STT
braucht etwas Vorlauf-Audio vor Sprachbeginn für gute Erkennungsgenauigkeit (siehe
`pre_speech_ms`-Konzept bei Smart-Turn) — zu aggressives Client-Trimming könnte das unterlaufen.

---

## Zusammenfassung

| # | Ansatz | Verdict | Grund |
|---|---|---|---|
| 1 | Paralleles Streaming | ❌ | Beide Kernhebel bereits getestet, Ergebnis negativ (§4.1, §4.3) |
| 2 | Speculative Decoding | ❌ | Kein Modellzugriff über Azure Managed API |
| 3 | VAD aggressiv tunen | ⚠️ | Größtenteils schon umgesetzt; `SmartTurnParams` als einziger offener Rest |
| 4 | Kleineres/quantisiertes LLM | ❌ | Bereits Mini-Modell, Quantisierung nicht verfügbar |
| 5 | TTS-TTFB radikal senken | ⚠️ | Provider-Wechsel = Stack-C-Gebiet; **lokaler Phrase-Cache ist plausibel, kleiner Scope** |
| 6 | Pre-Computed Context | ❌ | Kein Modellzugriff; Azure cached Prompt bereits automatisch (belegt im Log) |
| 7 | Regional-Latenz | ⚠️ | Ist die EU-VM-Migration, die ausdrücklich ausgeklammert war; WebRTC bereits vorhanden |
| 8 | Adaptive Fallback | ❌ | Resilienz statt Latenz-Baseline; explizit „Nicht in Phase 0" |
| 9 | Edge-Caching häufiger Inputs | ❌ | Widerspricht dem Trainingszweck (inhaltsunabhängige Antworten) |
| 10 | Client-seitige VAD | ⚠️ | Adressiert nicht den gemessenen Engpass (STT-Finalisierung, nicht Audio-Ankunft) |

**Von 10 Punkten bleibt real Neues und Plausibles für Stack B übrig:**

1. **`SmartTurnParams` (stop_secs/pre_speech_ms) tunen** (aus Punkt 3) — einziger noch nicht
   geprüfter Parameter am bestehenden Turn-Detection-Mechanismus.
2. **Lokaler TTS-Cache für wenige, wirklich fixe Phrasen** (aus Punkt 5) — kleiner Scope, aber
   risikoarm und ohne Zielkonflikt mit dem Trainingszweck.

Alle anderen acht Punkte sind entweder bereits umgesetzt, bereits mit gegenteiligem Ergebnis
getestet, setzen eine Infrastruktur voraus, die Stack B nicht hat (self-hosted Modell), fallen
unter „Nicht in Phase 0", oder stehen im Widerspruch zum eigentlichen Produktzweck.

---

## Nachtrag: ChatHistory-Fenster — getestet und verworfen

Zusätzlich zur obigen Liste kam die Frage auf, ob sich über Azure-AI-Foundry-Modell-Settings
(ChatHistory, `max_completion_tokens`, Temperatur, Top P) noch etwas holen lässt.

- **Temperatur, Top P:** kein Latenz-Effekt — beeinflussen nur die Token-*Auswahl*, nicht die
  Anzahl der Rechenschritte pro Token.
- **`max_completion_tokens`:** kein Effekt auf `llm_ttfb_ms` (Zeit bis zum ersten Token), nur eine
  Obergrenze für die Gesamtlänge. Als Absicherung gegen seltene Ausreißer sinnvoll, aber kein
  Latenz-Hebel für unsere Kernmetrik.
- **„ChatHistory":** existiert nicht als Server-Einstellung des Deployments — nur als
  Playground-eigene Anzeige-Option in der Foundry-Oberfläche, ohne Wirkung auf unser Deployment
  (Azure OpenAI ist zustandslos, jeder Request trägt seine eigene Nachrichtenliste). Um den an das
  LLM gesendeten Verlauf zu begrenzen, muss das im eigenen Code passieren.

**Testweise umgesetzt** (`ContextWindowLimiter`, FrameProcessor zwischen
`context_aggregator.user()` und `services.llm`, Sliding Window auf die letzten 15 Turns,
mittlerweile wieder entfernt): 30-Turn-Vergleich gegen die bestehende Baseline (kein Fenster) —

| | Kein Fenster (Baseline) | 15-Turn-Fenster |
|---|--:|--:|
| E2E p50 / p90 | 1570 / 1817 ms | **1770 / 2154 ms** |
| LLM TTFB p50 / p90 | 444 / 569 ms | **546 / 713 ms** |
| Prompt-Tokens (Turn 30) | 1759 | 993 |
| Cache Read Tokens (Turn 30) | 1664 | **0** |

**Klare Regression, trotz weniger Prompt-Tokens.** Ursache: Azure OpenAI cached automatisch einen
stabilen Prompt-Prefix (siehe §6 „Systemprompt + Pre-Computed Context" oben). Ein Sliding Window
verschiebt bei jedem Turn die ältesten zwei Nachrichten aus dem Kontext — damit ändert sich der
Prefix bei jedem Turn, und der Cache greift nicht mehr. Weniger, aber frische (unge­cachte)
Tokens sind offenbar langsamer zu verarbeiten als mehr, aber überwiegend gecachte Tokens. **Für
die Latenz kontraproduktiv.** Für reines Kosten-Controlling bei sehr langen Gesprächen (jenseits
dessen, was Caching noch abfedert) könnte die Grundidee trotzdem relevant bleiben — das wäre dann
ein separates Ziel, nicht Latenz, und müsste eigens bewertet werden.

**Code zurückgerollt** (`ContextWindowLimiter` entfernt, `pipeline.py` wieder auf
vollständigen Verlauf), Fund als Kommentar in `pipeline.py` dokumentiert.

---

## Nachtrag 2: `SmartTurnParams` (stop_secs/pre_speech_ms) — geprüft, verworfen ohne Testlauf

Letzter offener Punkt aus der ursprünglichen Liste (Punkt 3). Code-Analyse von
`base_smart_turn.py` und `turns/user_stop.py` (`TurnAnalyzerUserTurnStopStrategy`) zeigt: Beide
Parameter sind keine echten Latenz-Hebel, aus unterschiedlichen Gründen.

- **`pre_speech_ms`** (Default 500 ms) bestimmt nur, wie viel bereits gepuffertes Audio *vor*
  Sprechbeginn dem Modell als Kontext mitgegeben wird — reine Segment-*Inhalt*-Frage, keine
  Wartezeit. Verändert die Modell-*Genauigkeit*, nicht die Latenz bis zur Entscheidung.
- **`stop_secs`** (Default 3 s) ist eine **Fallback-Obergrenze** für den Fall, dass das
  Smart-Turn-Modell nach einer VAD-erkannten Pause `INCOMPLETE` statt `COMPLETE` meldet — dann
  wartet die Pipeline auf weitere Sprache oder bis diese 3 Sekunden rohe Stille erreicht sind.
  Der normale, schnelle Pfad (VAD-Stop → Modell-Inferenz → `COMPLETE` → warten auf finalisiertes
  Transkript) läuft unabhängig von `stop_secs`.

**Reale Evidenz statt nur Code-Lektüre:** Ein manueller Testlauf mit echter Sprache (Headset,
2026-09-07, nicht synthetisch) zeigte `EndOfTurnState.INCOMPLETE` bei 10 von 44
Modell-Aufrufen (~23 %) — deutlich häufiger als in unseren synthetischen 30-Turn-Tests, wo die
enge Streuung zwischen p50 und p95 nahelegt, dass das dort kaum vorkommt. Eine Detailanalyse einer
INCOMPLETE-Sequenz zeigt aber: Das sind **keine Latenz-Ausreißer**, sondern das Modell erkennt
korrekt natürliche Sprechpausen *innerhalb* eines mehrsätzigen Redebeitrags (z. B. Atempausen
mitten im Satz) und wartet zu Recht weiter, statt die Testperson zu unterbrechen. Die von uns
gemessene `turn_detection_ms`-Metrik beginnt erst beim *letzten*, tatsächlich turn-beendenden
VAD-Stop — frühere INCOMPLETE-Zyklen innerhalb eines laufenden Redebeitrags fließen gar nicht in
die Messung ein.

**Konsequenz:** `stop_secs` senken würde unsere gemessenen p50/p90-Werte nicht verbessern (der
schnelle Erfolgspfad ist davon unabhängig), aber das echte Risiko schaffen, Testpersonen bei
längeren, legitimen Sprechpausen mitten im Satz zu unterbrechen — ein Qualitäts-Downgrade ohne
Latenz-Gegenwert. Kein Testlauf durchgeführt, Ablehnung beruht auf Kombination aus Code-Analyse
und echten Log-Daten.

**Nebenbefund:** Bestätigt und schärft die in §5 der Baseline genannte Einschränkung „nur
synthetische Turns" — sie unterschätzen die reale Turn-Detection-Latenz vermutlich, weil saubere
TTS-Clips kaum INCOMPLETE-Zyklen auslösen, echte Sprache mit natürlichen Pausen aber schon.
Verstärkt die Priorität von „100ms-Schwelle mit echter Sprache validieren" (§6, Baseline-Doku).

**Damit sind beide in §6 als „übrig" markierten Punkte abgeschlossen** (TTS-Phrase-Cache bleibt
als einziger noch offener, kleiner Punkt aus der ursprünglichen Liste). Die verbleibenden
substantiellen Hebel sind die zwei strukturellen aus Baseline §6: EU-VM-Migration und
STT-Provider-Wechsel.

---

## Nachtrag 3: Echter Gesprächstest — widerlegt die Ausgangsvermutung, korrigiert Nachtrag 2

Anlass: Der Eindruck, echte Gespräche seien spürbar schneller gewesen als die synthetischen
Messungen. Um das nicht weiter aus dem Gedächtnis zu diskutieren, ein realer Testlauf über
dieselbe automatisierte Pipeline (`pacemaker-agent --stack azure-eu --transport local`, echtes
Mikro/Headset) — diesmal die JSONL-Datei nicht versehentlich gelöscht wie beim vorigen Versuch.

| | Synthetisch (30 Turns, Baseline §3/§4.2) | **Echtes Gespräch (8 Turns)** |
|---|--:|--:|
| E2E p50 / p90 / p95 | 1570 / 1817 / — ms | **2028 / 3208 / 4171 ms** |
| Turn-Detection p50 / p90 | 476 / 545 ms | **447 / 1375 ms** |

**Ergebnis: Echte Gespräche waren nicht schneller, tendenziell eher schlechter und deutlich
unregelmäßiger.** Die Ausgangsvermutung hält der Messung nicht stand — vermutlich beruhte der
frühere Eindruck auf der alten, nicht-automatisierten Methode oder auf subjektiver Wahrnehmung
während eines laufenden Gesprächs, nicht auf einer vergleichbaren Messung.

**Korrektur an Nachtrag 2:** Turn 3 dieses Laufs hatte `e2e_ms: 5134.1`, `turn_detection_ms:
3199.8` — ein einzelner Ausreißer, der p90/p95 im Alleingang dominiert. Rohlog dazu: zwischen
14:50:51 und 14:50:57 Uhr liefert das Smart-Turn-Modell **viermal hintereinander `INCOMPLETE`**,
bevor es `COMPLETE` meldet — nahe am 3-Sekunden-`stop_secs`-Default. Die in Nachtrag 2 getroffene
Aussage „INCOMPLETE-Zyklen tauchen nie in der `e2e_ms`-Metrik auf" ist damit **widerlegt**: Bei
einer wirklich zögerlichen, mehrfach unterbrochenen realen Äußerung akkumuliert sich das sehr
wohl messbar. Die Grundaussage bleibt aber gültig — das Modell wartet hier korrekt auf eine
Person, die noch formuliert, nur mit echtem statt „unsichtbarem" Latenz-Preis.

**Konsequenz:** `SmartTurnParams.stop_secs` wird wieder als offener Testkandidat eingestuft, jetzt
mit echter Evidenz statt nur Code-Analyse. n=8 (ein Ausreißer) reicht nicht zum blinden Tunen —
nächster Schritt: gezielter Vergleichstest mit gesenktem `stop_secs` (z. B. 1,5s statt 3s) gegen
einen weiteren echten Gesprächslauf, unter Beobachtung, ob dabei legitime Sprechpausen
fälschlich abgeschnitten werden.
