# Pacemaker: unabhängige Bewertung der Ergebnisse und zusätzliche Ideen

**Stand: 7. Oktober 2026.** Grundlage sind Strategie, Phase-0-Plan, bisherige Auswertungen, Agent-Code und die lokal vorhandenen JSONL-Messungen vom 4. Oktober. Die Kennzahlen unten wurden aus den Rohdaten neu berechnet. Es wurden keine neuen Provider-Aufrufe, kostenpflichtigen Messungen oder Änderungen am Agenten vorgenommen.

„Neu“ bedeutet in diesem Dokument: in den vorliegenden Unterlagen noch nicht konkret ausgearbeitet oder getestet. Was Claude außerhalb dieses Repositories erwogen hat, kann ich nicht beurteilen.

## 1. Meine Einschätzung

**Pacemaker hat einen funktionierenden Sprach-PoC mit erheblichem Optimierungspotenzial. Das Projekt ist weder technisch gescheitert noch bereits für Phase 1 abgenommen.** Der beste EU-Lauf erreicht p50 **1043 ms** und p90 **1153 ms**. Das ist nahe genug am ursprünglichen Budget, um gezielt weiterzuarbeiten. Es rechtfertigt aber weder einen Nachweis von 900 ms noch eine Aussage über echte Browsergespräche.

Der nächste Engpass ist inzwischen auch die Aussagekraft der Versuche: einzelne Läufe, sehr saubere synthetische Sprache, ein wiederholtes Zehn-Clip-Skript und eine Zielmetrik, die schon auf „Hm“ anspringt. Zusätzliche technische Beschleunigung sollte deshalb zusammen mit einer realistischeren Qualitätsprüfung stattfinden.

**Meine Arbeitsentscheidung:** Azure-Kaskade als Referenz behalten; `mini` und `nano` unter gleichen Bedingungen vergleichen. Realtime als Forschungsoption behalten, nicht aufgrund seines besseren Medians zum Favoriten machen. Zuerst Messdefinition und Browserpfad schließen, dann höchstens wenige gezielte Architekturversuche. Das bestehende Abnahmekriterium bleibt bis zu einer ausdrücklichen Projektentscheidung unverändert.

## 2. Was die Zahlen tatsächlich sagen

Alle Werte in Millisekunden. Die Zeilen sind unterschiedliche Versuchsbedingungen und kein vollständig kontrollierter Wettbewerb.

| Lauf vom 04.10. | Antworten mit Messwert | p50 | p90 | p95 | Maximum |
|---|---:|---:|---:|---:|---:|
| Azure EU `mini`, bereinigte Clips | 30 | 1526 | 1632 | 1693 | 2127 |
| Azure EU `nano`, bereinigte Clips | 29 | 1361 | 1628 | 1721 | 2011 |
| Azure Realtime, `minimal` | 30 | 1208 | 2048 | 2330 | 2961 |
| US-Referenz | 30 | 1224 | 1501 | 1800 | 1908 |
| Azure `mini`, kurzer Einstieg E1 | 30 | 1378 | 1537 | 1645 | 2659 |
| Azure `mini`, E1 + Segmentierung 100 ms | 30 | 1328 | 1556 | 1633 | 1871 |
| Azure `nano`, E1 + asynchroner Filter + 100 ms | 30 | **1043** | **1153** | **1194** | 1896 |

Rohdateien: `experiments/runs/20261004T145417Z-azure-eu.jsonl`, `150201Z-s2s`, `151619Z-azure-eu`, `155624Z-baseline`, `174828Z-azure-eu`, `175827Z-azure-eu`, `182316Z-azure-eu` (die verkürzten Namen haben jeweils denselben Datumspräfix und die Endung `.jsonl`). Rohdaten sind gitignored; die Tabelle hält die überprüften Ergebnisse im Repository fest.

### Fortschritt: real, aber unterschiedlich gut abgesichert

Gegenüber der September-Baseline von 2377 ms p90 ist der beste Oktoberlauf rund **51 % schneller**. Dieser Vergleich enthält auch Rechner-, Fixture- und Konfigurationswechsel. Er beschreibt den erreichten Entwicklungsstand, keinen isolierten kausalen Effekt einer Optimierung.

Der beste Lauf liegt **253 ms über dem p90-Ziel**, also rund 22 % seines aktuellen Werts. Kein Turn darin war unter 900 ms; der schnellste lag bei 938 ms. Das ursprüngliche Ziel ist damit klar verfehlt. Das Maximum von 1896 ms betrifft den ersten Turn und zeigt zugleich, warum Kaltstart separat bewertet werden sollte.

### Realtime: schnellerer typischer Wechsel, schlechtere langsame Antworten

Realtime gewinnt im Median, verliert hier aber deutlich beim p90. Für das Gesprächserlebnis können mehrere Pausen von zwei bis drei Sekunden störender sein als eine durchgehend etwas langsamere Kaskade. Ein einzelner Lauf beweist noch keine allgemeine Unterlegenheit von Realtime; er reicht jedoch aus, um es nicht allein wegen p50 zu bevorzugen.

### `nano`: kein nachgewiesener allgemeiner Modellvorteil

Die unoptimierten `mini`-/`nano`-p90 liegen praktisch gleichauf. Der beste `nano`-Lauf kombiniert Modell, Filtermodus und Promptänderung. Ein gleich konfigurierter `mini`-Lauf fehlt. Daraus folgt weder „nano ist das beste Modell“ noch „Modellgröße spielt generell keine Rolle“. Nachgewiesen ist bisher nur ein kleiner Unterschied der beobachteten LLM-TTFB unter den damaligen Bedingungen.

Beim unoptimierten `nano` fehlt außerdem eine Antwort wegen TTS-Ausfall. Seine Quantile gelten für die **29 erfolgreichen Antworten**, nicht für alle 30 angebotenen Gesprächszüge.

## 3. Schlussfolgerungen, die ich korrigieren oder enger fassen würde

| Bisherige Aussage | Meine Einordnung |
|---|---|
| „900 ms sind mit dieser Architektur unabhängig vom Anbieter nicht erreichbar.“ | Zu stark. Getestete Konfigurationen erreichten sie nicht. Eine universelle Grenze wurde nicht bewiesen; spätere Optimierungen senkten p90 bereits auf 1153 ms. |
| „EU-Datenresidenz kostet etwa 130 ms.“ | Beobachteter Unterschied zweier ganzer Stacks. STT, TTS, Routing und Einstellungen ändern sich zugleich. Ein isolierter EU-Aufpreis lässt sich daraus nicht bestimmen. |
| „Die schlechteren Abendwerte werden durch die Leitung erklärt.“ | Netzwerkverschlechterung ist ein plausibler Mitverursacher. TCP-RTT trennt aber nicht Serving-Last, Warteschlangen, Filter und Verbindungseffekte. Ursache nicht vollständig nachgewiesen. |
| „100 ms waren nur wegen der alten Clips problematisch.“ | Die bereinigten Clips widerlegen das Problem für diese sauberen Ein-Satz-Fälle. Sie widerlegen es nicht für Menschen mit Satzpausen, Reparaturen und längeren Äußerungen. |
| `wait_for_transcript=False` widerlegt spekulativen LLM-Start. | Das Flag testet die Turn-Freigabe. Es implementiert keinen versionierten Vorabaufruf auf Zwischentranskripten mit Verifikation und Abbruch. Dieser Architekturversuch bleibt offen. |
| Azure kann keine echte Text-Streaming-TTS. | Für den verwendeten SSML-Adapter trifft die Einschränkung zu. Microsoft dokumentiert einen anderen TextStream-Modus; siehe Abschnitt 5. |

Auch die Latenzbudget-Recherche würde ich vorsichtiger lesen: Befunde aus Mensch-Mensch-Gesprächen und einem Kommunikationsroboter begründen keine universelle Toleranzgrenze für deutschsprachiges Vertriebstraining. **1500 ms wäre ein zu prüfender Produktwert, keine wissenschaftlich nachgewiesene Abnahmeschwelle.** Die eigene Doku weist bereits darauf hin, dass mehrere Originalartikel nicht im Volltext geprüft wurden. Ich habe diese Literatur hier nicht neu validiert.

## 4. Zusätzliche Befunde aus dem Code

### 4.1 Die Startdefinition der Metrik ist widersprüchlich

Der Phase-0-Plan nennt „VAD erkennt Ende → erstes Audio“. Der installierte `UserBotLatencyObserver` setzt jedoch den Start auf `VADUserStoppedSpeakingFrame.timestamp - stop_secs`: Er rechnet auf den geschätzten Beginn der Stille zurück. Die neuere Recherche beschreibt das zutreffend; mehrere ältere Texte und Collector-Kommentare verwenden weiter die andere Definition.

Das ist eine **Definitionsabweichung**, kein Beleg für falsche Rohwerte. Die bereits eingerechneten 200 ms VAD-Wartezeit dürfen nicht noch einmal addiert werden. Für einen fairen Vergleich braucht jede Tabelle dieselbe explizite Definition.

### 4.2 Erfolgreiche Audioanfänge sind noch keine erfolgreiche Unterhaltung

Der Collector schreibt erst bei einem gemessenen Bot-Audioanfang. Fehler und stumme Antworten erhalten keine eigene Ergebniszeile. Die Turn-Bilanz warnt zwar über fehlende Werte, der Aggregator berechnet trotzdem Quantile nur über vorhandene Antworten.

**Ergänzung:** Pro angebotener Äußerung einen eindeutigen Status erfassen: beantwortet, Timeout, Audiofehler, abgebrochen oder falsch geschnitten. Ausfälle separat als Fehlerrate ausweisen. Ein explizit gewählter Timeout darf für zusätzliche SLO-Auswertungen dienen, sollte aber nicht stillschweigend als gemessene Antwortlatenz erscheinen.

Als Größenordnungsbeispiel: Bei hypothetisch unabhängigen 3,3 % Ausfällen je Turn hätten nur etwa 36 % der 30-Turn-Gespräche gar keinen Ausfall. **Das ist keine Schätzung der tatsächlichen Ausfallrate** aus dem einzelnen `nano`-Lauf; es zeigt die Bedeutung von Zuverlässigkeit über ein ganzes Gespräch.

### 4.3 Die automatische Aggregation mischt Versuche

`metrics/aggregate.py` gruppiert nur nach `stack` und `llm_model`. Gespeichert wird zwar `device`, gruppiert wird danach nicht. Filtermodus, VAD-Werte, STT-Segmentierung, Promptversion und Warm-up fehlen als Konfigurationsmerkmale. Damit würden die sehr unterschiedlichen Oktober-`nano`-Läufe gemeinsam ausgewertet.

Zusätzlich schreibt `infra/messreihe.sh` RTT-JSONL ins gleiche Verzeichnis, aus dem der Aggregator **alle** obersten `*.jsonl` liest. Diese Dateien haben ein anderes Schema. Ihre Vermischung kann Auswertungen unvollständig oder irreführend machen und muss explizit verhindert werden.

**Vorschlag:** Ein Manifest je Lauf mit `run_id`, Git-Revision, Paketversionen, Deployment-Typ, Region, Filtermodus, Prompt-/Fixture-Hash und Parametern; RTT-Dateien getrennt halten. Zuerst je Lauf auswerten, erst danach gleichartige Läufe zusammenfassen.

### 4.4 Browser- und echte Rollentests fehlen noch

`main.py` implementiert nur den lokalen Transport; `webrtc` und `livekit` werfen `NotImplementedError`. Ein `web/`-Client liegt nicht vor. Die synthetische Ausgabe verwirft Audio und simuliert lediglich die Wiedergabedauer. Browserpuffer, tatsächlicher Hörbeginn und Barge-in am Endgerät sind damit nicht nachgewiesen.

Die drei Persona-Tests testen einen Regex-Detektor an Beispielsätzen. Sie testen weder echte Modellantworten noch Budgettreue oder Geduld. `PersonaState` existiert, ist aber nicht an die Pipeline angebunden. Die Persona ist aktuell im Wesentlichen promptgesteuert.

## 5. Zusätzliche oder noch nicht sauber geprüfte Ideen

### A. Azure TextStream statt eines Requests pro Textstück

**Konkretester zusätzlicher technischer Ansatz.** Microsoft dokumentiert Text-Streaming im Python-Speech-SDK über den WebSocket-v2-Endpunkt und `SpeechSynthesisRequestInputType.TextStream`. Dabei fließen LLM-Textstücke in einen laufenden Syntheseauftrag. Der installierte Pipecat-Adapter verwendet dagegen `speak_ssml_async(ssml)` für den jeweils aggregierten Text.

Das ist ein anderer Ansatz als `TextAggregationMode.TOKEN` einfach am vorhandenen Adapter einzuschalten. SSML wird im TextStream-Modus nicht unterstützt; die konkrete deutsche Stimme, EU-Region, Abbruchbehandlung und Wortzeitstempel müssen geprüft werden. [Microsoft: Speech-Synthese-Latenz und Text-Streaming](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/how-to-lower-speech-synthesis-latency).

**Versuch:** Separater schmaler Adapter, gleiche Stimme und gleicher Text; Satzmodus gegen TextStream messen und blind anhören. Besonders interessant für inhaltliche Antwortanfänge ohne vorgeschaltetes Füllwort. Beim besten aktuellen Lauf beträgt die dokumentierte Satzwartezeit schon nur etwa 14 ms: Dort ist kein weiterer Gewinn von mehreren hundert Millisekunden allein aus dieser Wartezeit zu erwarten. Der mögliche Wert liegt auch in längeren natürlichen Antworten und dem Verzicht auf erzwungene Kurzsatz-Einstiege.

### B. Zeit bis zum Inhalt zusätzlich zur Zeit bis zum ersten Audio

Kurze Einstiege und gecachte Bestätigungen wurden bereits erwogen. **Neu zu operationalisieren ist eine zweite Zielmetrik:** Ende der Nutzeräußerung → erster hörbarer, auf die Äußerung bezogener Inhalt. Daneben Abstand zwischen Einstieg und Hauptantwort sowie gesamte Antwortdauer erfassen.

Ein „Hm“ kann eine brauchbare natürliche Reaktion sein. Ein „Ach so“ oder „Hm, nein“ transportiert aber auch Verständnis oder Ablehnung. Solche Einstiege können das Verhalten des SDR verändern. Ihre Häufigkeit und Angemessenheit gehören deshalb in den Blindtest, nicht nur in die Latenztabelle. Die aktuelle Verbesserung kann echten Nutzen haben; wie viel davon eine schnellere inhaltliche Antwort ist, wurde noch nicht gemessen.

### C. Zwei Testkorpora statt immer saubererer Clips

Das aktuelle Fixture-Korpus eliminiert interne Pausen ab 200 ms. Das hilft einem reproduzierbaren Leistungstest, entfernt jedoch gerade die schwierigen Fälle des Turn-Takings.

**Zusätzliches Robustheitskorpus:** einwilligungsbasiert aufgezeichnete menschliche Sprache mit Mehrsatzäußerungen, 300–1000-ms-Denkpausen, Selbstkorrekturen, Zahlen, Firmennamen und kurzen Zwischenrufen. Gewollte Gesprächsgrenzen vorher manuell markieren. Messen: vorzeitige Antworten, fehlende Satzteile, unnötige Wartezeit und Audio-Stopp bei echter Unterbrechung. Die Prüfung verwendet Sprachinhalt und Timing, keine Emotionsanalyse.

Die zehn Clips außerdem als einzelne unabhängige Testfälle mit frischer Sitzung und als zusammenhängendes Gespräch **ohne wiederholten Opener** nutzen. So werden Cacheeffekte, Kontextwachstum und unpassender Dialogverlauf voneinander getrennt.

### D. Turn-Taking als Qualitäts-Latenz-Kurve

Statt nur „100 ms ist schneller“ zu fragen, 100/200/300 ms unter identischen Bedingungen gegen falsch abgeschnittene und verspätete Turns auftragen. Der beste Parameter liegt auf einem Kompromiss zwischen Antworttempo und vollständigem Verstehen.

Damit wird sichtbar, ob niedrigere Latenz aus besserer Technik oder aus aggressiverem Unterbrechen entsteht. Das bestehende 900-ms-Ziel bleibt dabei bestehen; die Kurve erklärt, welche Qualität es bei den getesteten Varianten kostet.

### E. Spekulativer LLM-Start mit Verifikation

Die allgemeine Idee steht bereits in der jüngsten Ergebnisdoku. Ein konkreter Prüfaufbau fehlt: Vorabantwort auf einem stabilen Zwischentranskript erzeugen; bei Turn-Ende nur übernehmen, wenn das finale Transkript nach einer vorher definierten konservativen Regel übereinstimmt. Sonst verwerfen und regulär neu starten. **Audio erst nach bestätigter Turn-Grenze ausgeben.**

Zusätzlich zu E2E messen: verworfene Anfragen, Mehrkosten, Korrektheit und tatsächlich nutzbare Vorarbeit. Zunächst nur Text vorbereiten; spekulative TTS erst nach positivem Nachweis. Das verworfene `wait_for_transcript=False` ist kein Ersatz für diesen Test.

### F. Realtime mit genau einer serverseitigen Turn-Erkennung

Der aktuelle Vergleich nutzt lokale Turn-Erkennung auch für Realtime. Das ist kontrolliert, prüft aber nicht zwingend dessen beste Betriebsart. Ein separater Versuch könnte die lokale **Stop-Entscheidung** deaktivieren und ausschließlich die vom Deployment unterstützte serverseitige Turn-Erkennung verwenden. Beide gleichzeitig wieder einzuschalten würde das dokumentierte Doppeltriggerproblem reproduzieren.

VAD darf dabei für Messzwecke erhalten bleiben, ohne die Antwortauslösung zu steuern. Neben der Latenz müssen falsche Turn-Grenzen und Abbruchverhalten geprüft werden. Verfügbarkeit und Einstellungen am konkreten Azure-Deployment sind vorher zu verifizieren. Dies ist eine Hypothese, keine Zusage eines Gewinns.

## 6. Wie ich die nächsten Versuche aufbauen würde

1. **Messkette bereinigen:** Startdefinition vereinheitlichen, Run-Manifest und Ergebnisstatus erfassen, Aggregation von RTT trennen. Inhaltlichen Audioanfang zusätzlich markieren.
2. **Browserdurchstich herstellen:** Eine Persona, eine Verbindung, Transkript; Audio am Endgerät und Barge-in prüfen. Noch kein Dashboard oder Scoring bauen.
3. **Fairer Basisvergleich:** `mini` und `nano` mit gleichem Filter, Prompt und STT-Parameter auf der EU-VM; mindestens drei getrennte Sitzungen je Variante. Reihenfolge auch umkehren oder randomisieren, nicht immer A vor B.
4. **Robustheit prüfen:** Menschliches Pausenkorpus und echte fünfminütige Gespräche. Gründer bewerten Natürlichkeit, Verständlichkeit, Einwandqualität und Gesprächsfluss getrennt, möglichst blind.
5. **Nur einen Architekturhebel gleichzeitig:** Zuerst TextStream; danach je nach Befund spekulativer Textstart oder serverseitiges Realtime-Turn-Taking. Gewinne nicht aus addierten Komponenten-Quantilen schätzen: p90 einer Summe ist nicht die Summe ihrer p90.

Für 30 Turns hängt p90 im Wesentlichen an wenigen langsamen Werten. Ein explorativer IID-Bootstrap des besten Laufs ergibt ungefähr **1100–1291 ms** als 95-%-Intervall für p90 (10.000 Resamples, NumPy, Seed 7). Das ist **kein belastbares Produktionsintervall**, weil wiederholte Clips und gemeinsame Sitzung die Unabhängigkeit verletzen. Aussagekräftiger sind mehrere unabhängige Sitzungen und später Auswertungen mit Resampling ganzer Gespräche.

Hohe RTT nicht nachträglich pauschal herausfiltern: Ausschlussregeln vorher festlegen. Schlechte Verbindungslagen zusätzlich separat berichten, denn sie gehören zum späteren Browserbetrieb. Ebenso Kaltstart getrennt ausweisen, aber in der Gesamtbilanz behalten.

## 7. Entscheidung und Bedeutung für das Produkt

**Weiterarbeiten: ja. Phase 0 als bestanden erklären: derzeit nein.** Es fehlt noch der Nachweis für Browserbetrieb, echte Sprachqualität, Barge-in, reproduzierbare Rollentreue und vollständige Kosten pro Gesprächsminute. Diese offenen Punkte sind im ursprünglichen Plan bereits enthalten; sie werden jetzt entscheidender als weitere unkontrollierte 30-Turn-Läufe.

Das Produkt verspricht Vertriebstraining. Ob es Verkäufer besser macht, ist durch schnelle Antworten allein nicht belegt. Für die nächste Phase sollte deshalb neben Technik eine kleine Nutzerprüfung vorbereitet werden: Können SDRs an einer konkreten Einwandbehandlung üben, bleibt die Persona konsistent, und wirkt die Übung auf ein anschließendes vergleichbares Gespräch? Das ist eine spätere Produktvalidierung, kein Vorschlag, jetzt die ausgeschlossene Scoring-Plattform zu bauen.

Ein festes Persona-Prompt genügt außerdem nicht als Nachweis, dass asynchron ausgelieferte Inhalte immer unproblematisch sind. Microsoft beschreibt gepufferte Textblöcke im Standardmodus und verzögerte Filtersignale im asynchronen Modus. Bereits abgespielte Sprache lässt sich nicht zurückholen; verbleibende Audioausgabe und Warteschlangen müssen bei einem Signal gestoppt werden können. [Microsoft: Content Streaming](https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/content-streaming).

Meine Priorität wäre daher: **eine verlässliche, vollständige und glaubwürdige Unterhaltung messen; anschließend deren Tempo optimieren.** Falls die reale Nutzung bei etwas über einer Sekunde funktioniert, ist eine bewusste Änderung des Produktbudgets denkbar. Sie sollte auf Nutzerbeobachtung und getrennten Qualitätskennzahlen beruhen, nicht auf dem besten synthetischen Lauf.

## 8. Nachvollziehbarkeit

- [Aktuelle Detailergebnisse und Optimierungen](../experiments/summaries/2026-10-03-llm-modellvergleich-deployment-typen.md), besonders §§11–13.
- [September-Baseline](../experiments/summaries/2026-09-06-stack-b-azure-eu-baseline.md) und [bisherige Ansätze](../experiments/summaries/2026-09-07-latenz-ansaetze-plausibilitaetspruefung.md).
- [Latenzbudget-Recherche](2026-10-04-recherche-latenzbudget.md) und [Phase-0-Abnahmekriterien](phase-0-proof-of-concept.md).
- Codeprüfung: `metrics/collector.py`, `metrics/aggregate.py`, `pipeline.py`, `stacks.py`, `main.py`, Synthetic Caller/Transport, Persona und Persona-Tests unter `agent/`; `infra/messreihe.sh`.
- Installierte Pipecat-Quellen: `agent/.venv/Lib/site-packages/pipecat/observers/user_bot_latency_observer.py` und `services/azure/tts.py`. Die Aussagen zur konkreten Adapterimplementierung beziehen sich auf diese lokale Version, nicht pauschal auf alle Pipecat-Versionen.
- Externe technische Aussagen wurden gegen die oben verlinkte Microsoft-Primärdokumentation geprüft. Keine Preise, Modellverfügbarkeiten oder Rechtslage neu bewertet.
