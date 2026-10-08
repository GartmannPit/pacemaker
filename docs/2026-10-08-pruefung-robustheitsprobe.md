# Unabhängige Prüfung der Robustheitsprobe (Phase 0)

**Stand:** 08.10.2026. **Auftrag:** Prüfung von §16 der [Modellvergleichs-Summary](../experiments/summaries/2026-10-03-llm-modellvergleich-deployment-typen.md), im Rahmen von [Plan §4 C](2026-10-07-pruefung-kritik-naechste-schritte.md). Ausschließlich lokale Auswertung vorhandener Dateien und Codelektüre; keine Codeänderungen, neuen Messläufe oder externen Dienste. Audio wurde weder weitergegeben noch auf Stimme, Emotion oder Prosodie untersucht. Die Pausenangaben wurden aus dem vorhandenen Index übernommen, nicht erneut am Audio verifiziert.

## 1. Urteil

**Nachgeprüfter Fakt:** Die zentralen Zählwerte und gerundeten Latenzen aus §16.1 stimmen mit den lokalen Rohdaten überein. Es sind 87 von 156 Sitzungen zerfallen (55,77 %); 76 dieser 87 haben mindestens eine unterbrochene Persona-Nachricht mit nichtleerem Text (87,36 %). Allerdings fehlen in den Latenzquantilen systematisch alle sechs R19-Sitzungen. Das dokumentierte R12-Beispiel hat vier erkannte Turns, also drei zusätzliche Turn-Grenzen. Quellen: sämtliche `experiments/runs/robust/manifests/*.json`, `turns/*.jsonl`, `transcripts/*.jsonl`; konkrete Fälle in §§2–3 unten.

**Interpretation:** Die Probe weist einen reproduzierbaren Fehler gegenüber der Vorgabe „eine Aufnahme = ein gewünschter Turn“ nach. Sie belegt weder Segmentierungsunabhängigkeit noch, dass Information vollständig verstanden wird. „Hörbar“ bezeichnet hier eine Näherung aus einer simulierten Ausgabe, keinen gemessenen Hörbeginn. Die 100-ms-Einstellung ist als vorläufige schnelle Referenz vertretbar; die Robustheitsvalidierung aus Schritt C ist damit nicht abgeschlossen. Grundlage: Zahlen in §2, Metrikgrenzen in §4, Aufbau in §5.

**Empfehlung:** Erst Messlücken und Zielmetriken präzisieren, dann den gemeinsamen Abbruch-/Kontextpfad absichern und einzelne Turn-Hebel vergleichen. Die 100-ms-Referenz vorläufig behalten, aber nicht als robust bestätigt deklarieren. Schritt C verlangt außerdem ein zusammenhängendes Gespräch; die vorliegende Reihe mit `--fresh` erledigt diesen Teil nicht. Quellen: Plan §4 A/B/C und §3.13–3.14; `tests/synthetic_caller.py:160–172`; Bewertung in §6.

## 2. Nachrechnung der Zahlen und Beispiele

### 2.1 Datengrundlage und Berechnung

**Fakt:** 156 Manifeste, je eine Ledger-Zeile pro Sitzung, mit 26 Clip-IDs, drei Segmentierungswerten und je zwei Wiederholungen. 69 Status `beantwortet`, 87 Status `zerfallen`; keine anderen Endstatus. Alle Manifeste nennen `azure-eu`, `gpt-4.1-nano`, VAD-Stopp 0,2 s, Aufwärmen an, Randstille 0 ms, kurzen Einstieg aus, frische Sitzung, Fixture-Hash `f5603a26fc72`, Prompt-Hash `5e57c31e3b90`, Git-Revision `4eea8f5`, Pipecat 1.8.1 und Gerät `pacemaker-mess-vm`. Das stützt die deklarierte Referenzkonfiguration, beweist für sich aber keine Deployment-Region oder EU-Residenz. Quellen: alle Manifeste, beispielsweise `manifests/20261008T152203Z-azure-eu-R01.json`; Summary §15 Variante B; Einwilligung in der Aufnahmeliste.

**Methode:** JSON-Dateien wurden unabhängig mit Python-Standardbibliothek eingelesen, ohne Pipeline-/Provider-Module zu importieren. Zerfall wurde direkt aus `n_turn_ends > 1` gezählt und mit dem Status abgeglichen. Die Text-Unterbrechungsquote zählt Sitzungen mit mindestens einer Assistant-Zeile, für die `interrupted == true` und `text.strip()` nicht leer ist. Quantile wurden aus den gespeicherten Ledger-Werten selbst berechnet: sortieren, Position `(n−1) × q`, linear zwischen den beiden benachbarten Werten interpolieren. Das entspricht `metrics/aggregate.py:29–38`, ist aber keine Wiederholung eines Messlaufs. Rohdatenbasis für jede folgende Tabellenzelle: `robust/manifests/<run_id>.json` (Segmentierung/Clip), `robust/turns/<run_id>.jsonl` (Status/Timing), `robust/transcripts/<run_id>.jsonl` (Unterbrechung/Text).

| Segmentierung | Zerfall / alle Sitzungen | Mit unterbrochenem Text / zerfallen | Ohne unterbrochenen Text | Nicht zerfallen | Mit VAD-Latenzwert | Erstes Audio p50 / p90, ms | Turn-Ende p50 / p90, ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| 100 ms | 30/52 = 57,69 % | 26/30 = 86,67 % | 4 | 22 | 20 | 943,80 / 1265,71 | 355,50 / 531,14 |
| 200 ms | 29/52 = 55,77 % | 25/29 = 86,21 % | 4 | 23 | 21 | 1236,80 / 1636,00 | 438,60 / 616,30 |
| 300 ms | 28/52 = 53,85 % | 25/28 = 89,29 % | 3 | 24 | 22 | 1331,05 / 3833,89 | 564,75 / 1057,80 |

**Fakt:** Rundung auf ganze Millisekunden reproduziert §16.1. Auch dessen Turn-Ende-Spalte gilt für die **nicht zerfallene Teilmenge**, nicht für alle Sitzungen. Die Summen „4/4/3“ sind arithmetisch korrekt, ihre Bezeichnung „nur still verworfen“ ist nicht unmittelbar gemessen: Nachgewiesen ist das Fehlen unterbrochener Transkripttexte, nicht die Stille jedes verworfenen Kandidaten. Quellen: Tabelle oben; Definition `TranscriptRecorder.record` in `metrics/transcript.py`; Ausgabepfad in `tests/synthetic_transport.py`.

**Fakt zur Reproduzierbarkeit:** Das derzeitige `metrics/robustness.py`, Funktion `report` (ab Z. 82) erzeugt diese Summary-Tabelle nicht unverändert. Es zählt **alle** unterbrochenen Assistant-Zeilen, auch leere, und bildet die Latenzquantile über alle Sitzungen mit Wert. Damit wären die Sitzungszahlen „mit Abbruch“ 30/29/28. Über alle Sitzungen ergeben sich erstes Audio p50/p90 987,35/5790,76; 1214,45/5154,03; 1219,20/4006,36 ms (je n=50). Turn-Ende entsprechend 356,10/505,21; 451,65/636,86; 561,65/848,36 ms. §16 benutzt nachvollziehbare zusätzliche Filter, die im genannten Auswertungsprogramm nicht abgebildet sind. Empfehlung: diese Filter und Nenner ausdrücklich dokumentieren, statt allein auf das Programm zu verweisen.

### 2.2 Clip-Muster und Beispiele

**Fakt:** Die Liste der in allen sechs Sitzungen zerfallenen Aufnahmen stimmt: R03, R05, R08, R10, R11, R12, R14, R15, R17, S01, S02, S03, S05. R01 zerfällt bei 100/200/300 ms in 2/1/2 Sitzungen; S04 in 2/2/0. Alle übrigen ausgewerteten IDs zerfallen in keiner Sitzung. Quellen: Ledger-Dateien mit den jeweiligen Clip-Suffixen; Zuordnung über die Manifeste.

**Fakt:** Die vier zitierten Fragment-/Persona-Beispiele entsprechen dem ersten 100-ms-Durchgang. Fundstellen sind jeweils `experiments/runs/robust/transcripts/<run_id>.jsonl`, mit Zeilenangaben:

| Clip / run_id | Nachweis | Präzisierung |
|---|---|---|
| R03 / `20261008T152242Z-azure-eu-R03` | Z. 1–3: „Es hängt bei uns.“ / „Ja, das ist verständlich,“ / Fortsetzung | Zwei Turn-Enden laut gleichnamigem Ledger. |
| R10 / `20261008T152440Z-azure-eu-R10` | Z. 1–3: Chef-Fragment / „Ja, genau,“ / „Nicht abstimmen …“ | Vorzeitige Zustimmung ist als Text belegt; kein Hörtest. |
| R11 / `20261008T152457Z-azure-eu-R11` | Z. 1–3: Mail verschickt / „Danke, das hatte ich schon“ / Rücknahme | Zwei Turn-Enden. |
| R12 / `20261008T152515Z-azure-eu-R12` | Z. 1–8: vier Nutzerfragmente, drei abgebrochene Antworten, davon eine leer | `n_turn_ends=4`; genauer: vier Turns durch drei zusätzliche Grenzen, nicht drei Turns. |

**Interpretation:** Die Beispiele illustrieren realen Textzerfall und vorzeitige Reaktionen. Sie sind keine statistische Antwortqualitätsbewertung. Gerade R10 antwortet abschließend mit einer allgemeinen Nachfrage statt einer erkennbaren Verarbeitung der Budget-Korrektur (Transkript Z. 4); das trägt die Behauptung „vollständig verstanden“ nicht.

### 2.3 Vergleich auf derselben Clip-Teilmenge

**Fakt:** Die nicht zerfallenen Gruppen enthalten unterschiedliche Clips. Für alle sechs Sitzungen nicht zerfallen sind R02, R04, R06, R07, R09, R13, R16, R18, R19, R20, R21. Nach Ausschluss der sechs R19-Werte ohne VAD-Basis bleiben je Segmentierung exakt 20 Werte derselben zehn Clips. Deren Audio-p50/p90 beträgt 943,80/1265,71 (100), 1236,25/1656,97 (200), 1314,85/2208,76 ms (300). Quellen: Manifeste/Ledger dieser IDs; gleiche Quantilformel wie §2.1.

**Interpretation:** Auch dieser vergleichbarere Ausschnitt zeigt 100 ms als schnellste Einstellung. Der p90-Abstand zu 300 ms ist aber deutlich kleiner als in der ungleichen Summary-Teilmenge. Mit je 20 Werten und nur zwei Wiederholungen ist die genaue Differenz im Verteilungsrand unsicher. Keiner dieser p90-Werte erfüllt `CLAUDE.md` (p90 < 900 ms).

## 3. Warum fehlen sechs Latenzdateien?

**Fakt:** Die sechs fehlenden Dateien gehören sämtlich zu R19 („OK.“), je zwei pro Segmentierungswert. Ihre Manifeste, Transkripte und Ledger sind vorhanden. Alle haben ein Turn-Ende, keine erfassten Fehler und Status `beantwortet`. Alle VAD-relativen Zeiten sind `null`, aber `first_audio_from_clip_ms` ist vorhanden:

| run_id | Segmentierung | Erstes Audio ab Clip-Sprechende, ms |
|---|---:|---:|
| `20261008T152730Z-azure-eu-R19` | 100 | 3518,1 |
| `20261008T161656Z-azure-eu-R19` | 100 | 3322,2 |
| `20261008T153722Z-azure-eu-R19` | 200 | 3389,0 |
| `20261008T160708Z-azure-eu-R19` | 200 | 3189,5 |
| `20261008T154731Z-azure-eu-R19` | 300 | 3384,1 |
| `20261008T155718Z-azure-eu-R19` | 300 | 3572,0 |

Quellen: jeweils `robust/turns/<run_id>.jsonl:1`, gleichnamiges Manifest und Transkript.

**Fakt zur Messmechanik:** `MetricsCollector.__init__` legt lediglich den Dateipfad fest; die Datei entsteht erst in `record_turn` beim Schreiben (`metrics/collector.py`). `pipeline.py:47–80` verdrahtet den Latenzobserver mit dem Collector. Der lokal installierte Pipecat-1.8.1-Code `observers/user_bot_latency_observer.py`, `_handle_bot_started_speaking`, emittiert Nutzer→Bot-Latenz nur mit vorhandenem `_user_stopped_time`, gesetzt aus `VADUserStoppedSpeakingFrame`. Das Ledger sucht ebenfalls ein VAD-Sprechende vor dem ersten Turn-Ende (`metrics/turn_ledger.py`, `summarize`, ab Z. 106). Ohne diesen Anker werden seine relativen Werte `null`.

**Fakt aus Logs:** Bei R19 startet der Nutzerturn per `TranscriptionUserTurnStartStrategy`, und die Inferenz erfolgt jeweils etwa 1,8 s danach. Beispiel Durchgang 1/100: `durchgang1-seg100.log:1683–1698` (Clip 15:27:31.621, Transkriptstart 15:27:33.995, Inferenz 15:27:35.797, Botstart 15:27:36.480). Durchgang 2/100: `durchgang2-seg100.log:1687–1702` (16:17:00.408 → 16:17:02.211 → 16:17:02.682). Entsprechende R19-Blöcke der anderen vier Durchgangslogs zeigen denselben Transkriptstart und Abstand.

**Interpretation, stark gestützt:** R19 läuft über den Transkript-Fallback ohne verwertbaren VAD-Stopp. Der lokale Pipecat-Code `turns/user_stop/turn_analyzer_user_turn_stop_strategy.py:293–305` setzt in diesem Fall „complete“ und wartet einen Transkript-Inaktivitätstimeout. Der Log-Abstand passt dazu. Es handelt sich um eine deterministische Messlücke bei einem speziellen Eingabetyp, nicht um sechs fehlgeschlagene Sitzungen oder zufälligen Dateiverlust. Warum die VAD bei diesem kurzen Clip nicht greift, ist nicht isoliert: Clipdauer, Schwellen und Startlogik kommen als Ursachen in Frage; eine konkrete Ursache wurde hier nicht experimentell bewiesen. Index R19: `speech_s=0.27`.

**Empfehlung:** 156 angebotene, 69 nicht zerfallene und 63 nicht zerfallene mit VAD-Latenz separat ausweisen. R19 als „beantwortet, aber Timing-Fallback und Messlücke“ sichtbar halten. Die Clip-basierten 3,19–3,57 s sind ein deutlicher Befund gegen das Ziel „kurze Äußerungen sofort beantworten“ (Aufnahmeliste R19–R21). Sie dürfen nicht still verschwinden und auch nicht ungekennzeichnet mit VAD-relativen Werten vermischt werden. Die Clip-Referenz beruht auf einer RMS-Schwelle und Einspeisezeit, kein manuell annotiertes oder clientseitiges Hörende (`tests/synthetic_transport.py`, `last_voiced_sample`, `feed_clip`).

## 4. Tragfähigkeit der Metriken

### 4.1 „Zerfallen“

**Fakt:** `metrics/turn_ledger.py`, Funktion `classify` (ab Z. 78) priorisiert mehr als ein Turn-Ende vor allen anderen Status. Das ist für die Aufgabe „eine angebotene Aufnahme soll ein Turn sein“ eine brauchbare strukturelle Metrik. Sie sagt nicht, ob vor der gewünschten Grenze Audio ausgegeben wurde, ob eine Grenze gesprächspragmatisch vertretbar war oder ob Mindestinformation fehlte. Fehler, Abbruch und Zerfall können gleichzeitig auftreten, erscheinen aber nicht gleichzeitig im Endstatus. Die Downstream-/Frame-ID-Deduplizierung (`on_push_frame`, ab Z. 185) reduziert Doppelzählung; die vorhandenen Zusammenfassungen erlauben keine vollständige Rekonstruktion jedes Roh-Frame-Ereignisses.

**Empfehlung:** Einen Endstatus beibehalten, ergänzend orthogonale Flags nutzen: zusätzliche Turn-Grenzen, Antwortstart vor annotiertem Sollende, Ausgabe vor Fortsetzung, Abbruch und Mindestinfo erfüllt. Eine unsinnige Antwort auf unvollständige Eingabe kann auch bei nur einem Turn-Ende vorkommen; `classify` prüft den Inhalt nicht. „Zerfallsquote“ daher nicht mit „Gesamtfehlerquote“ oder „falsche Unterbrechung“ gleichsetzen. Quelle: `classify` und Aufnahmeliste mit Grenze/Mindestinfo.

### 4.2 „Hörbar unterbrochen“ und „still verworfen“

**Fakt:** Der Synthetic Output verwirft PCM, wartet aber pro Chunk dessen Dauer (`tests/synthetic_transport.py`, `write_audio_frame` (ab Z. 120)). Die Assistant-Aggregation liegt hinter `transport.output()` (`pipeline.py:176–192`); sie zeichnet den bei Turn-Stopp aggregierten Text auf (`pipeline.py:98–102`). Das ist näher am fortgeschrittenen Ausgabepfad als bloß generierter LLM-Text. Der Aggregator akzeptiert jedoch Textframes mit `append_to_context`, nicht nur einen expliziten Beleg abgespielter, nichtstiller PCM-Samples (lokaler Pipecat-Code `llm_response_universal.py:2076–2095`).

**Interpretation:** Nichtleerer unterbrochener Text ist ein plausibler Indikator für begonnene simulierte Ausgabe. Es ist kein Nachweis, dass Pit oder ein Browsernutzer tatsächlich Audio hörte. Audio-/Textausrichtung, Puffer, Stille und Ausgaberennen können abweichen; umgekehrt beweist leerer Text nicht zwingend fehlendes Audio. Auch `BotStartedSpeakingFrame` ist ein technischer Ausgabestart und kein Client-Hörbeginn. Es gibt in dieser Probe keinen Lautsprecher-/Client-Mitschnitt. Quellen: Outputtransport und Ledger-Ereignisbehandlung.

**Empfehlung:** „Unterbrochene Ausgabe mit Transkripttext (Näherung)“ und „ohne unterbrochenen Transkripttext“ verwenden. Für spätere Verifikation pro Antwort nichtstilles ausgegebenes PCM und dessen Zuordnung, später Client-Playout oder einen ausgerichteten Mitschnitt erfassen. Hieraus keinen Nachweis des Barge-in-Kriteriums ≤300 ms ableiten; die Reihe enthält keine entsprechende Start→Verstummen-Messung. Quellen: Plan §4 B, Synthetic Caller und Transport.

### 4.3 „Vollständigkeit der ersten Nachricht“

**Fakt:** `metrics/robustness.py:36–42` berechnet für jedes Referenzwort, ob es **irgendwo** in der Menge der Wörter des ersten Nutzertexts vorkommt. Reihenfolge und Vorkommenszahl des empfangenen Texts werden ignoriert, Wiederholungen in der Referenz mehrfach gutgeschrieben. Ein einziges empfangenes „sie“ erfüllt somit alle „sie“ der Referenz. Zahlen-/Wortvarianten, Beugungen und STT-Fehler werden nicht semantisch normalisiert. Eigenständig mit dieser Formel nachgerechnet: mittlerer Wortanteil je Segmentierung 69,69 %, 70,67 %, 71,97 % (je n=52). Quellen: `robust_index.json` und sämtliche ersten Nutzerzeilen der Transkripte.

**Interpretation:** Als grober lexikalischer Abdeckungsindikator des ersten Fragments brauchbar; als Vollständigkeits-, Informationsverlust- oder Verständnismaß nicht tragfähig. Ein fehlendes „nicht“ oder die korrigierte Zahl wiegt semantisch wesentlich mehr als ein beliebiges fehlendes Wort. Ein hoher Wert kann falsche Bedeutung verbergen. Ein niedriger Wert kann aus Wortvarianten oder bewusst getrennten Turns entstehen. `load_sessions` nimmt die erste Nutzerzeile, ohne gesondert zu beweisen, welcher Antwortkandidat darauf tatsächlich reagiert. Quellen: `robustness.py:66–80`; Beispiele R05/R10/R11 aus Aufnahmeliste/Transkripten.

**Fakt:** Der Kontrolltext ist selbst STT-Ausgabe, keine fehlerfreie Inhaltsreferenz. Index R08 enthält „Wenn ihr nicht ihr Vertrieb“, R18 „SGUVODSGVO“; mehrere Aufnahmen weichen außerdem sachlich vom Drehbuch ab (R07: 200 statt 220 Mitarbeiter; R16: anderer Firmenname; R18: Europa statt Frankfurt; S05: 25 statt 15 Leute). Quelle: `robust_index.json`, Einträge der genannten IDs, gegenüber Aufnahmeliste. Der Index enthält Pausenmaximum, Quellbereich und Kontrolltext, aber keine expliziten Sollgrenzen/Mindestinformationen pro tatsächlich gesprochener Variante.

**Empfehlung:** Wortabdeckung enger benennen; daneben manuell geprüften tatsächlich gesprochenen Referenzinhalt, Sollgrenzen und kritische Slots erfassen (Negation, finale Zahl, Monat, beide Fragen). Erste Eingabe, Vereinigung aller Nutzerfragmente, tatsächlich an das LLM gesendeter Kontext und finale Antwort getrennt prüfen. Texttreue gegebenenfalls mit sequenzbasierter Wortausrichtung bewerten, Verständnis mit Mindestinfo-Annotation. Die vorhandenen `S0x.stt.txt` und der Index sind Kontrollmaterial, kein Ersatz für diese Annotation.

### 4.4 Latenz zerfallener Sitzungen

**Fakt:** `summarize` verbindet das erste Turn-Ende, dessen letzten vorherigen VAD-Anker und das erste Bot-Audio der gesamten Aufnahme. Wenn der erste Kandidat still abbricht, kann dieses Audio zu einer späteren Fortsetzung gehören. Beispiel `turns/20261008T152319Z-azure-eu-R05.jsonl:1`: `first_audio_ms=5182.5`, aber `first_audio_from_clip_ms=1089.7`. Der hohe erste Wert ist nicht die Antwortlatenz nach dem vollständigen Clip. Negative Clip-relative Werte bedeuten dagegen, dass erstes Audio schon vor dem letzten Clip-Sprechende begann. Quelle: `turn_ledger.py`, Funktion `summarize` (ab Z. 106) und genannter Run.

**Interpretation/Empfehlung:** Diese gemischten Werte sind weder erfolgreiche End-to-End-Latenz noch einfach „langsame Antworten“. Für zerfallene Sitzungen Ereignisse je erkannter Teilantwort bilanzieren, vorzeitige Ausgabe als Fehler markieren und Antwortzeit nach dem endgültigen Sollende separat berichten. Nur nicht zerfallene Sitzungen zu vergleichen ist für eine bedingte Geschwindigkeitsdiagnose sinnvoll, aber kein Qualitäts- oder Gesamtbudgetnachweis. Quelle: Summary-Tabelle gegenüber Ledger-Definition und `CLAUDE.md`.

## 5. Kausalität, Default und Aussagegrenzen

**Fakt:** Im Versuch wurde STT-Segmentierung variiert; VAD-Stopp blieb stets 200 ms. Das Skript fährt Blöcke 100→200→300 und 300→200→100, Clips stets in derselben Reihenfolge (`infra/robustheitsreihe.sh`). Es gibt hier weder VAD-Vergleich noch Smart-Turn-Ablation. Die Pipeline entscheidet Turn-Grenzen im Nutzeraggregator, STT liefert davor Audio/Transkripte; die Stop-Strategie berücksichtigt Finalisierung/Timeouts (Projektcode `pipeline.py:124–159`, `stacks.py:88–100`; lokaler Pipecat-Code `turn_analyzer_user_turn_stop_strategy.py`). Die Konfiguration „200 ms VAD-Stopp“ ist daher belegt, die Formulierung „nicht die STT-Segmentierung“ zu absolut.

**Interpretation:** Dass 13 Clips bei jeder Einstellung zerfallen, spricht gegen einen allein durch die 100-ms-Segmentierung ausgelösten Fehler. Die Turn-Erkennung und ihr Zusammenspiel mit STT sind ein plausibler Haupthebel. Gleichwohl zeigen R01 und S04 Segmentierungsabhängigkeit in den beobachteten Ergebnissen. Ein Vergleich von 30/29/28 genügt weder für statistische Unabhängigkeit noch für Nichtunterlegenheit. R19 zeigt außerdem einen Fallback, der nicht einfach als „Smart Turn hält das Fragment für abgeschlossen“ beschrieben werden kann. Die konkrete Smart-Turn-Entscheidung an jeder inneren Pause ist aus den aggregierten Ledgers nicht nachgewiesen. Quellen: §2.2/§3 und genannte Stop-Strategie.

**Empfehlung zum Default:** 100 ms vorläufig als schnellste Referenz behalten; Robustheit offen lassen. Selbst auf gemeinsamer Clipmenge ist es schneller (§2.3), beobachtet aber insgesamt zwei zusätzliche Zerfälle gegenüber 300 ms. Kein belastbarer Beleg, dass das Risiko gleich ist. Entscheidung künftig an gepaarten Clips, kritischer Mindestinfo und vorab definierter tolerierter Fehlerrate treffen; Qualität und Latenz gemeinsam beurteilen. Das entspricht dem Abbruchkriterium im Plan §3.13 und dem Zweck von Schritt C.

**Fakt zu den Grenzen:** Ein Sprecher/ein Mikrofon, gezielt schwierige Aufnahmen, zwei Wiederholungen desselben Materials und ein Modell. Die 156 Sitzungen sind keine 156 unabhängigen Sprecheräußerungen; für Sprachvariation gibt es 26 Aufnahmen, für Sprechervariation eine Person. Gegenbalancierung vermindert einfache Reihenfolgeeffekte, beseitigt weder zeitliche Dienststreuung noch feste Clipreihenfolge. Die Sessions sind frisch und beginnen mit identischem Systemprompt; Aufwärmen läuft im Hintergrund (`synthetic_caller.py`, `pipeline.py:220–231`). Das testet keinen längeren Kontext, keine Browser-/Mikrofonkette, kein Echo und keine spontane Anpassung des Sprechers an Dazwischenreden. Quellen: Skript, Caller, Manifeste, Aufnahmeliste.

**Fakt/Einordnung der Pausen:** Der Index nennt maximal 1680 ms bei R15 und 1530 ms bei S05; R14 1670 ms. Manche vorgesehenen Pausen sind länger aufgenommen, andere kürzer (R06 nur 80 ms). „Pausen länger als im Drehbuch“ gilt also nicht für jeden Clip. Diese Stressfälle bleiben nützlich, erlauben aber keine natürliche Häufigkeitsprognose. Die Maxima wurden hier nur aus dem Index überprüft. Quelle: `robust_index.json` gegenüber Regieanweisungen.

**Interpretation:** Zulässig ist: „Diese Konfiguration zerlegt wiederholt bestimmte vorab als zusammenhängend definierte Aufnahmen; größere STT-Segmentierung löst das Problem nicht durchgehend.“ Unzulässig ist: „Gut die Hälfte realer Verkaufsgespräche zerfällt“, „andere Stimmen/Geräte sind robust“, „die spätere Antwort versteht alles“ oder „100 ms sind allgemein optimal“. Quelle: Stichprobendesign und Nachrechnungen.

**Interpretation zur Sollgrenze:** Nach „Okay.“ mit 1,67 s Pause ist eine Antwort gesprächspragmatisch plausibel. Gegenüber der vorab definierten R14-Sollgrenze bleibt sie trotzdem ein Testfehler; man darf die Vorgabe nicht nachträglich zur Verbesserung der Quote umdefinieren. Künftig beide Bewertungen getrennt annotieren. Auch grammatische Vollständigkeit ist kein sicherer Turn-Ende-Beweis: „Wir starten im März“ kann noch korrigiert werden. Quellen: Aufnahmeliste R06/R14, Index R14, Summary §16.2 Nr. 5.

## 6. Hebel und Reihenfolge

### 6.1 Längerer VAD-Stopp

**Interpretation:** Einfacher, gut isolierbarer Hebel gegen kurze innere Pausen. Ein moderater Anstieg löst Pausen von 0,9–1,7 s nicht generell; so lange zu warten würde kurze echte Turns stark verzögern. Der Zusatzaufwand ist nicht zwangsläufig exakt die Stop-Differenz bei jedem Turn: STT-Finalisierung und Inferenz können überlappen. VAD-basierte Latenzmessung zieht den tatsächlich verwendeten Stop-Wert ab, sodass die reale Wartezeit weiterhin im E2E-Wert enthalten sein muss. Quellen: Index, `config.py:113`, `turn_ledger.py`, `UserBotLatencyObserver`.

**Empfehlung:** Als erster kleiner Architekturvergleich sinnvoll, nach Schließen der Messlücken und mit R19/R20/R21 als Pflichtkontrolle. STT-Fallback und dessen Timeout mit prüfen. Der lokal installierte Pipecat-Code warnt bei verändertem VAD-Stopp vor veränderter P99-/Timeout-Annahme (`turn_analyzer_user_turn_stop_strategy.py:247–264`). Gewinner nur bei nachweislich weniger unerwünschten Antworten und akzeptabler Latenz, sonst zur Referenz zurück (Plan §3.13). Diese Prüfung hat keinen solchen Lauf gestartet.

### 6.2 Vollständigkeitsprüfung am Transkript

**Interpretation:** Inhaltlich am gezieltesten gegen abgebrochene Syntax und offene Beziehungen; vereinbar mit inhalts-/strukturbasiertem Ansatz. Sie kann eine noch nicht gesprochene Korrektur oder Negation jedoch nicht sicher vorhersagen. Ein finalisiertes STT-Segment ist kein garantierter vollständiger Sprecherturn. Ein weiterer LLM-Aufruf kostet Zeit und kann fehlentscheiden. Quellen: R03/R05/R10/R11-Transkripte; lokale Stop-Strategie mit `wait_for_transcript`/Finalisierung.

**Empfehlung:** Zunächst einfache, überprüfbare textbasierte Fortsetzungsindikatoren und Gesprächskontext beurteilen; offene Konstruktionen dürfen warten, kurze eigenständige Antworten müssen enden können. Deadline/Fallback explizit halten. Ein Modell nur als begrenzte Hypothese mit Fehlerraten und Zeitkosten behandeln, nicht als „Vollständigkeitsgarantie“. Sprachdaten und Ableitungen weiterhin nur EU; kein neues Emotions-/Prosodie-Signal. Quellen: `CLAUDE.md`, Aufnahmeliste, Plan §3.13.

### 6.3 Audio bis Mindeststille zurückhalten

**Interpretation:** Kann wahrnehmbares Dazwischenreden verhindern, auch wenn intern vorzeitig gerechnet wird. Es verhindert allein weder Textzerfall noch eine Antwort auf veraltete Teilinformation. Eine Grenze unterhalb der beobachteten Denkpausen lässt Fehler übrig; eine darüber verzögert alle kurzen Antworten. Eine reine Audiofreigabe ist deshalb kein Ersatz für korrigierte Turn-/Kontextlogik. Quellen: Index und gemischte Timing-Fälle in §4.4.

**Empfehlung:** Bei diesem Ansatz Ausgabefreigabe, Kandidaten-ID und gemeinsames Verwerfen von LLM/TTS/Puffern koppeln. Bei Fortsetzung muss die vorläufige Antwort neu bewertet bzw. verworfen werden; verspätete Audiochunks blockieren. Verworfene Kandidaten dürfen den Gesprächskontext nicht verändern. Dies ist bereits im Plan §3.1/§3.14 und §4 B/D vorgesehen. Vorberechnen kann die zusätzliche Wartezeit teilweise überdecken, benötigt aber eine bestätigte Grenze und verifiziertes finales Transkript vor der Freigabe; das ist ein größerer Architekturversuch.

### 6.4 Empfohlene Abfolge und fehlende Ansätze

**Fakt:** §16.2 nennt die drei Hebel als Kandidaten, ohne ausdrücklich einen verbindlichen Versuchsablauf oder Erfolgsschwellen zu definieren. Eine feste Reihenfolge lässt sich daraus nicht als bestehende Entscheidung ableiten. Quelle: Summary §16.2 Nr. 6.

**Empfehlung, abgeleitet aus den Befunden und Plan §4:**

1. Auswertung korrigieren: alle 156 Sitzungen bilanzieren, R19-Messlücke/Fallback sichtbar, gleiche Clipgruppen, Sollgrenzen und Mindestinfo festlegen. „Text-Unterbrechung“ von Audio-Nachweis trennen.
2. Gemeinsamen Abbruch-/Kontextpfad aus Schritt B absichern. Das ist Voraussetzung für Audio-Gating und spekulative Kandidaten, unabhängig von einem späteren Gewinnerhebel.
3. Kleinen isolierten VAD-Stopp-Vergleich vorsehen; dabei Kurzturn-Erkennung und Transkript-Fallback ausdrücklich mit untersuchen. Das R19-Problem ist ein fehlender eigener Hebel in §16.
4. Falls innere Pausen weiter fehlschlagen, text-/kontextbasierte Fortsetzungsprüfung gegen die Referenz beurteilen. Smart-Turn-Schwelle oder Stop-Strategie als weitere isolierte Alternative untersuchen; kein unkritisches kombiniertes Tuning.
5. Audio-Gating mit vorläufiger Berechnung nur als klar abgegrenzten größeren Versuch, sofern die kleinen Hebel den Zielkonflikt nicht lösen. Danach zusammenhängende Gespräche und weitere Sprecher/Geräte, statt allein dieses Korpus weiter zu optimieren.

Abnahmekriterien müssen getrennt vorab feststehen: unerwünschte Ausgabe vor Sollgrenze, kritische Mindestinfo, verlorene/fehlende Antworten, Ausgabelatenz ab echtem Endpunkt einschließlich Kurzturns, spätere Abbruchlatenz. Ein „beantwortet“-Status allein ist kein Qualitätskriterium. Begründung: §§3–5; Plan §3.13, §4 A/B/C.

### 6.5 Smart Turn und Prosodie-Verbot

**Fakt:** Der lokal vorhandene Pipecat-1.8.1-Code `audio/turn/smart_turn/local_smart_turn_v3.py:138–182` berechnet Whisper-artige Log-Mel-Merkmale aus Audio, beschränkt den Ausschnitt auf acht Sekunden und klassifiziert mit ONNX bei Wahrscheinlichkeit >0,5 als abgeschlossen. Er prüft an dieser Stelle nicht das STT-Transkript. Das Ergebnis ist Turn-Vollständigkeit, kein Emotions-/Stress-Score. Die Projektpipeline verwendet die Default-Stop-Strategie des Aggregators; Logs benennen `TurnAnalyzerUserTurnStopStrategy`. Quellen: lokaler Paketcode, `pipeline.py:153–159`, Durchgangslogs. Die installierte Paketversion stimmt mit den Manifesten überein; damit ist nicht zusätzlich die Byteidentität des VM-Pakets bewiesen.

**Interpretation:** Audiobasiertes Endpointing ist nicht automatisch Emotionserkennung. Zugleich kann aus dem Wrapper nicht geschlossen werden, dass das gelernte Modell keine prosodischen Merkmale nutzt. „Semantisch“ im Projektkommentar ist kein Beleg für reine Text-/Inhaltsanalyse. `CLAUDE.md` verbietet Prosodie-/Stimmlagen-/Stressanalyse und nennt zugleich Silero/Smart Turn als Stack. Diese Spannung muss fachlich geklärt werden; weder pauschale Compliance-Freigabe noch pauschales Rechtsurteil ist aus diesen Dateien ableitbar. Eine rechtliche Prüfung wurde hier nicht durchgeführt.

**Empfehlung:** Turn-Erkennung strikt auf Gesprächsstruktur begrenzen, keine Merkmale für Stimme/Emotion exportieren oder scoren. Für eine streng ausgelegte Vorgabe „keine Prosodieanalyse“ Smart Turn nicht ohne dokumentierte Einordnung freigeben; textbasierte Grenze plus Stille/VAD als Alternative erwägen. Lokale Ausführung auf der EU-VM unterstützt die Datenresidenz, sagt aber nichts über die erlaubte Analyseart. Quellen: `CLAUDE.md`, Einwilligung und genannter Modellwrapper. Keine externen Modell-/Rechtsquellen wurden hierfür aufgerufen.

## 7. Konkrete Korrekturen für §16

Die folgenden Formulierungen sind **Empfehlungen**; ihre Belege stehen jeweils in den genannten Prüfungsabschnitten und Quelldateien.

| Bisherige Formulierung | Präzisere Formulierung | Beleg |
|---|---|---|
| „Gut die Hälfte echter … Äußerungen … unabhängig von der Segmentierung“ | „In diesem gezielt schwierigen Korpus zerfallen 30/29/28 von je 52 Sitzungen. Größere Segmentierung beseitigt den Zerfall nicht; Unabhängigkeit ist nicht nachgewiesen.“ | §2; Manifeste/Ledger, insbesondere R01/S04. |
| „Ursache ist … VAD-Stopp 200 ms + Smart Turn … nicht die STT-Segmentierung“ | „Turn-Erkennung im Zusammenspiel mit STT ist der plausible Haupthebel. VAD-Stopp und Smart Turn wurden nicht isoliert verglichen; einzelne Ergebnisse ändern sich mit der Segmentierung.“ | §5; Skript, Pipeline, Stop-Strategie. |
| „hörbar unterbrochen“ / „nur still verworfen“ | „Unterbrochene simulierte Ausgabe mit Transkripttext“ / „ohne unterbrochenen Transkripttext“; Hinweis auf fehlenden Hörnachweis. | §4.2; Synthetic Output, TranscriptRecorder. |
| „In ~9 von 10 Fällen hörbar“ | „76 von 87 zerfallenen Sitzungen enthalten unterbrochenen Assistant-Text (87,36 %); tatsächlicher Client-Hörbeginn wurde nicht gemessen.“ | §2.1/§4.2. |
| „Die Information geht nicht verloren … sieht beide Teile … Schaden … nicht fehlender Inhalt“ | „In den geprüften Beispielen stehen beide Nutzerfragmente im Verlauf; Logs belegen für R03/R10 den zusammengesetzten LLM-Kontext. Vollständige STT-Erfassung, korrekte semantische Zusammenführung und Berücksichtigung der Mindestinfo sind nicht systematisch geprüft.“ | Beispieltranskripte; `durchgang1-seg100.log:254,854` (Generierung mit Kontext); §4.3. |
| „100 ms Segmentierung bestätigt … ohne mehr Zerfall“ | „100 ms bleiben vorläufig die schnelle Referenz. Beobachtet wurden etwas mehr Zerfälle als bei 200/300 ms; Robustheit/Nichtunterlegenheit sind offen.“ | §2.1/§2.3/§5. |
| „nicht zerfallen: erstes Audio“ ohne Nenner | „VAD-relative Latenz nur für 20/21/22 nicht zerfallene Sitzungen mit Zeitbasis; je zwei R19-Fälle fehlen. R19 separat mit Clip-relativen 3,19–3,57 s.“ | §3, R19-Ledger. |
| „Turn-Ende p50/p90“ | „Turn-Ende p50/p90 derselben nicht zerfallenen Teilmenge mit VAD-Zeitbasis.“ | §2.1. |
| R12 „zerfällt dreimal“ | „Vier erkannte Turns, drei zusätzliche Grenzen; zwei abgebrochene Antworten mit Text und eine ohne Text im ersten 100-ms-Beispiel.“ | `20261008T152515Z-azure-eu-R12`, Ledger/Transkript. |
| „Nicht jeder Zerfall ist falsch“ | „Nicht jeder Zerfall wäre in einem freien Gespräch unangemessen; gegenüber der vorab gesetzten Sollgrenze bleibt er eine Abweichung.“ | Aufnahmeliste R14; §5. |

**Abschlussbewertung:** Die Probe ist als erste Diagnose wertvoll und zeigt einen klaren Handlungsbedarf. Schritt C hat belastbare Teilbefunde, aber noch keine vollständige Robustheitsabnahme: Die zugesagte Bewertung vorzeitiger Antwort/fehlender Mindestinfo/unnötiger Wartezeit ist nur teilweise operationalisiert, die Kurzturn-Messlücke ist offen, und das zusammenhängende Gespräch fehlt. Grundlage: Aufnahmeliste „Was danach passiert“, Plan §4 C, Nachrechnung und Codeprüfung dieses Dokuments.
