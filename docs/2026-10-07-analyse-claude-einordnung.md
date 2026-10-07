# Analyse von Claudes Einordnung der Projektbewertung

**Stand: 7. Oktober 2026.** Bezug: [Claudes Einordnung](2026-10-07-einordnung-projektbewertung.md) und [ursprüngliche Bewertung](2026-10-07-unabhaengige-projektbewertung.md). Geprüft wurden zusätzlich der aktuelle Skript-Diff, Aggregator, Transkript-Recorder und installierte Pipecat-LLM-Code. Neue VM-Messdaten lagen lokal bei dieser Prüfung nicht vor; die genannten RTT-Werte von 4,5–5 ms wurden deshalb nicht unabhängig bestätigt. Keine neuen Provider-Aufrufe oder Codeänderungen durch diese Analyse.

## 1. Ergebnis

**Claudes Antwort ist fachlich weitgehend überzeugend. Den angepassten Plan würde ich mit den Präzisierungen unten übernehmen.** Er unterscheidet inzwischen zwischen beobachtetem Ergebnis und allgemeiner Behauptung, korrigiert die Azure-Streaming-Aussage und priorisiert vollständige Gespräche vor weiteren Tempoexperimenten.

Es gibt keine neue Evidenz, die die ursprüngliche Gesamtbewertung umkehrt: Weiterarbeiten ist sinnvoll; Phase 0 ist noch nicht bestanden. Zustimmung zwischen zwei Bewertungen ersetzt die ausstehenden Messungen nicht.

Der größte Fortschritt der Antwort ist der konkrete Arbeitsplan. Dafür braucht es jetzt überprüfbare Ergebnisse je Schritt, damit aus der Einigkeit keine weitere Dokumentationsrunde ohne bessere Messdaten entsteht.

## 2. Was ich übernehme

| Claudes Punkt | Bewertung |
|---|---|
| Messkette zuerst reparieren | Richtig. Konfigurationsvermischung und fehlende Fehlerzeilen betreffen alle weiteren Vergleiche. |
| Bereits laufende VM-Reihe anschließend je Lauf auswerten | Sinnvoll; eine laufende Reihe muss nicht wegen eines verbesserten Plans verworfen werden. Ihre nachträglich rekonstruierbaren Einstellungen und Grenzen müssen sichtbar bleiben. |
| Browserdurchstich vor neuen Architekturversuchen | Richtig. Der Produktpfad enthält bislang ungemessene Audio- und Transporteffekte. |
| Leistungskorpus plus menschliches Robustheitskorpus | Richtig. Saubere Clips und schwierige Sprecherwechsel beantworten unterschiedliche Fragen. |
| Kurze Einstiege vorerst behalten und offen ausweisen | Vertretbar. Die ursprüngliche Bewertung verlangt ihre Qualitätsprüfung, nicht ihre pauschale Entfernung. |
| Vorgefertigte Einstiege zurückstellen | Sinnvoll, solange Antwortinhalt und Gesprächswirkung nicht sauber gemessen werden. |
| Realtime niedriger priorisieren | Angemessen angesichts der bisherigen langsamen Ausreißer und zusätzlichen offenen Produktfragen. |

## 3. Präzisierungen und verbleibende Widersprüche

### 3.1 „Zeit bis zum Inhalt“ ist nicht einfach „Audio des zweiten Satzes“

Claudes Plan definiert die zweite Metrik als erstes Audio des Satzes nach dem Einstieg. Das ist ein brauchbarer **technischer Marker**, aber keine allgemeine Definition von Inhalt:

- „Nein.“ kann bereits die vollständige inhaltliche Antwort sein.
- „Moment mal.“ kann eine relevante Aufforderung zum Gesprächsablauf sein.
- Auch ein zweiter Satz kann ausweichen oder nur eine Floskel enthalten.
- TextStream kann Inhalte ohne dieselben Satz- und Requestgrenzen ausgeben.

**Empfehlung:** Zwei Begriffe trennen: „Beginn des Hauptsatzes“ als automatisierbare Hilfsmetrik und „Beginn der relevanten Antwort“ als zunächst manuell annotierte Qualitätsmetrik. Für die Annotation vorher Beispiele festlegen: Reagiert die Passage auf die aktuelle Frage oder den Einwand? Ein angemessenes Nein zählt; eine beliebige Einleitungsfloskel nicht automatisch.

Wichtig ist die Audioposition. `TranscriptRecorder.ts` wird beim Aggregator-Ereignis geschrieben; das ist kein Wortzeitstempel des tatsächlichen Hörbeginns. Für eine kleine Stichprobe reicht ein ausgerichteter Audiomitschnitt mit manueller Markierung. Für den Browser zusätzlich tatsächliche Wiedergabe statt nur ausgehender Serverframes betrachten.

### 3.2 TextStream ist eine gute Versuchsidee, kein belegter Gewinn

Claude schreibt, TextStream „senkt die TTS-Zeit“. Das sollte **„könnte die Antwortlatenz senken“** heißen. Die dokumentierte Fähigkeit ist belegt, ihre Wirkung mit eurer deutschen Stimme und Konfiguration noch nicht.

Im besten Lauf beträgt die dokumentierte Wartezeit bis zum ersten Satz bereits nur rund 14 ms. Das bloße Entfernen dieser Wartezeit kann die fehlenden 253 ms bis zum p90-Ziel nicht erklären. TextStream könnte größere Vorteile bei natürlichen längeren Satzanfängen und beim Verzicht auf erzwungene Kurzsätze haben. Synthesebeginn, Pufferung und Klangqualität bleiben zu messen.

Microsoft dokumentiert Python-TextStream über WebSocket v2; SSML ist dabei nicht unterstützt. Derselbe Artikel nennt getrennte SDK-Metriken für Netzwerk-, Service- und Clientlatenz. Diese bieten eine zusätzliche Möglichkeit, den TTS-Block besser zu erklären. [Microsoft: Speech-Synthese-Latenz](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/how-to-lower-speech-synthesis-latency).

**Fairer Versuch:** Erst derselbe Text und dieselbe Stimme mit beiden Adaptern; danach eine zweite Gegenüberstellung mit natürlichem Prompt ohne erzwungenen Einstieg. Adapter- und Promptänderung getrennt ausweisen.

### 3.3 Eine frühere Widerlegung des spekulativen Starts steht tatsächlich im Repository

In §3.5 schreibt Claude: „Habe ich so auch nicht behauptet.“ Die [Plausibilitätsprüfung vom September](../experiments/summaries/2026-09-07-latenz-ansaetze-plausibilitaetspruefung.md), §1, setzt den vorzeitigen LLM-Start jedoch ausdrücklich mit `wait_for_transcript=False` gleich und nennt die Kernidee widerlegt. Die Zusammenfassung wiederholt, beide Kernhebel seien negativ getestet worden. Beim TOKEN-TTS-Modus fand außerdem nur eine Codeanalyse statt.

Die aktuelle technische Einigung ist richtig: Ein vorab gestarteter, später verifizierter LLM-Aufruf wurde damit nicht getestet. **Die ältere Dokumentation muss genau diesen Punkt ebenfalls korrigieren**, sonst bleibt eine falsche Ausschlussbegründung für spätere Leser stehen. Das ist eine sachliche Dokumentationskorrektur, keine relevante Meinungsverschiedenheit über den nächsten Versuch.

### 3.4 Direktmessungen tragen den Mechanismus, nicht einen universellen Millisekundenwert

Claudes Hinweis auf den Wert der bisherigen Filtermessungen ist berechtigt. Microsoft beschreibt den Unterschied zwischen gepufferten Textblöcken und asynchroner Ausgabe ausdrücklich. Im installierten Pipecat-Code endet die TTFB-Messung nach einem Chunk mit `choices`, **bevor** geprüft wird, ob `delta.content` Text enthält. Eine leere Rollendelta kann diese Metrik also beenden. [Microsoft: Content Streaming](https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/content-streaming).

Damit sind der Filtermechanismus und die mögliche Differenz zwischen Paket-TTFB und erstem Text gut abgesichert. Die ungefähr 265 ms aus wenigen Direktanfragen sind weiterhin ein beobachteter Effekt dieser Stichprobe. Für neue Tabellen explizit **erstes verwertbares Textdelta** zusätzlich zum ersten Paket erfassen.

### 3.5 Filtersignalbehandlung gehört in den gemeinsamen Audiopfad

Das Stoppen bei `finish_reason: content_filter` ist eine konkrete sinnvolle Aufgabe. Sie sollte vor neuen Streaming-Adaptern eingeplant werden oder deren gemeinsame Voraussetzung sein. Sonst wird die Abbruchlogik zweimal gebaut oder funktioniert nur mit einem Adapter.

Zum Nachweis gehört: laufende Synthese abbrechen, wartendes Audio verwerfen, Ausgabe am Browser stoppen und verhindern, dass verspätete Chunks der verworfenen Antwort erneut abgespielt werden. Ein Status im Transkript muss den abgebrochenen Turn erkennbar machen. Die Behandlung kann bereits gehörte Inhalte nicht zurücknehmen und garantiert keine Vorabmoderation.

## 4. Geplant und umgesetzt auseinanderhalten

Der aktuelle Diff von `infra/messreihe.sh` verschiebt neue RTT-Dateien nach `experiments/runs/rtt/`. **Dieser Teil ist lokal umgesetzt.** Der Aggregator liest weiterhin alle obersten JSONL-Dateien und gruppiert ausschließlich nach Stack und Modell.

Damit bleiben offen:

- bereits vorhandene RTT-Dateien im alten Verzeichnis;
- eine auf der VM schon laufende Skriptinstanz, die durch eine lokale Dateiänderung nicht nachweislich aktualisiert wurde;
- Run-Manifeste, validiertes Dateischema, Ergebnisstatus und Gruppierung je Lauf;
- die angekündigten Korrekturen in alten Auswertungen und Metrikdefinitionen.

Neue Messungen sollten ein Manifest direkt schreiben. Bei bestehenden Läufen Informationen aus Logs rekonstruieren und fehlende Werte als **unbekannt** kennzeichnen. Aktuelle Defaults sind kein Beweis für historische Einstellungen. Insbesondere eine im Portal zugeordnete Filterkonfiguration beweist laut eigener Versuchsgeschichte noch nicht, dass sie im Lauf bereits wirksam war.

## 5. Konkrete Abschlusskriterien für den nächsten Arbeitsschritt

| Schritt | Reviewbares Ergebnis |
|---|---|
| Messkette | Pro angebotener Äußerung ID und Endstatus; Summe aller Status entspricht der Zahl angebotener Äußerungen. Fehler werden nicht aus der Gesamtbilanz entfernt. |
| Lauftrennung | Eine Tabelle je `run_id`; Manifest mit belegten Einstellungen; RTT-Dateien werden explizit ausgeschlossen. Unbekannte historische Einstellungen bleiben sichtbar. |
| VM-Auswertung | Sechs Läufe einzeln mit p50/p90/p95, Maximum, Fehlerquote und erstem Turn. Keine allgemeine Aussage allein aus gepoolten 180 Turns. |
| Browserdurchstich | Ein vollständiges Gespräch im Browser und gezielte Barge-in-Fälle; tatsächlicher Audio-Stopp am Endgerät überprüft. |
| Qualitätsprobe | Zusammenhängendes Skript ohne erneuten Opener; Stichprobe mit Pausen und Korrekturen; bewertete Vollständigkeit und Angemessenheit der Antworten. |
| Architekturversuch | Identische Vergleichsbedingungen, nur ein geänderter Hebel; Qualitäts- und Fehlerraten neben Latenz. |

Für die nächste Messreihe Reihenfolge randomisieren oder gegenbalancieren. Drei Sitzungen je Modell sind ein sinnvoller Anfang, aber noch kein starker Nachweis für stabile Produktions-p90 oder seltene Fehler.

## 6. Empfehlung

**Den Plan übernehmen, mit präziseren Metriken und überprüfbaren Abschlusskriterien.** Die laufende VM-Reihe zuerst unter ihren tatsächlichen Bedingungen auswerten. Danach Browsergespräch und Robustheitsprobe; erst auf dieser Basis entscheiden, ob TextStream den nächsten Entwicklungsaufwand rechtfertigt.

Eine erneute Grundsatzentscheidung über Weiterarbeiten ist fachlich nicht nötig. Die tatsächliche Nutzbarkeit und das unveränderte 900-ms-Abnahmekriterium bleiben getrennte offene Fragen. Als nächstes sollte das Repository belastbar zeigen können: **Welche Konfiguration hat welches vollständige Gespräch mit welcher Qualität und welchen Fehlern geliefert?**
