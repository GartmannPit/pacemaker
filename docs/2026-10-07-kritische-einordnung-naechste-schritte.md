# Kritische Einordnung: Claudes nächste Schritte für Phase 0

**Stand: 7. Oktober 2026.** Grundlage: [Nächste Schritte](2026-10-07-naechste-schritte.md), [VM-Ergebnisse, §14](../experiments/summaries/2026-10-03-llm-modellvergleich-deployment-typen.md), [vorige Analyse](2026-10-07-analyse-claude-einordnung.md), ursprünglicher Phase-0-Plan und lokale Infra-Konfiguration. Die VM-Zahlen wurden aus der Ergebnistabelle beurteilt; die zugehörigen Rohdaten vom 7. Oktober liegen lokal nicht vor. Keine Umsetzung oder neuen Messläufe im Rahmen dieser Prüfung.

## 1. Urteil

**Den Plan als Arbeitsrichtung übernehmen, aber noch nicht als vollständigen Abnahmeplan.** Messkette → Browser → realistische Sprachprüfung ist eine gute Priorität. Die Architekturversuche gehören dahinter. Drei Punkte sollten vor Beginn korrigiert werden:

1. Filtersignalbehandlung in den gemeinsamen Abbruchpfad vorziehen.
2. Browserdurchstich mit konkreten Infrastruktur- und Messvoraussetzungen beschreiben.
3. Fehlende Phase-0-Kriterien und einen Abschluss mit Go/No-Go ergänzen.

Außerdem wiederholt der Plan zwei bereits benannte Überdehnungen: „zweiter Satz = Inhalt“ und „TextStream senkt die TTS-Zeit“. Beides ist so noch nicht belegt.

## 2. Die neue Ausgangslage richtig lesen

Die drei dokumentierten `nano`-Läufe mit p90 1103, 1014 und 1206 ms verbessern die Evidenz gegenüber einem einzelnen Laptoplauf. Alle drei liegen weiterhin über 900 ms. Das stärkt die Entscheidung, weiterzuarbeiten; es beweist keine Browserqualität.

Die Spannweite der drei p90 beträgt 192 ms. **Sie ist keine feste Nachweisgrenze:** Effekte unter 150 ms sind nicht prinzipiell unbelegbar. Ihre Nachweisbarkeit hängt von Versuchsanordnung, Stichprobenumfang und Varianz ab. Umgekehrt ist ein Unterschied über 150 ms nicht automatisch kausal.

`nano` liegt in allen drei Wiederholungen beim p50 und p90 vor `mini`. Das ist ein plausibler Kandidatenvorteil unter diesen Bedingungen. Die Reihenfolge bleibt jedoch immer `mini` vor `nano`, und Haupttreiber scheint die unterschiedliche Sprachausgabe zu sein. Für die Empfehlung zählen deshalb Antwortqualität und Zeit bis zur relevanten Antwort mit. Modellwahl und Qualität der erzeugten Einstiege sind nicht unabhängig.

Zwei Aussagen aus §14 brauchen weiterhin Einschränkungen:

- **Stabile RTT vor und nach einem Lauf schließt Netzwerkeffekte innerhalb des Laufs nicht aus.** Dienstlast, Scheduling und Stichprobenstreuung sind mögliche Ursachen; „stammt aus den Diensten, nicht aus dem Netz“ ist zu kategorisch.
- **Unauffällige erste Turns mit Warm-up beweisen dessen kausale Wirkung nicht.** Dafür fehlt ein vergleichbarer Lauf ohne Warm-up auf derselben VM. Das Ergebnis zeigt zunächst, dass die aktuelle Konfiguration keinen auffälligen Erstturn-Nachteil hatte.

## 3. Schritt 1: sinnvoll, aber für einen halben Tag zu breit

Manifest und Lauftrennung sind kleine, klare Aufgaben. Zuverlässige Turn-Zuordnung, Timeouts und Audiofehlerbehandlung greifen dagegen in asynchrone Pipelineabläufe ein. „Zeit bis zum Inhalt“ erfordert Audiomarker oder Annotation. Zusammen mit Dokumentationskorrekturen und Kontrollmessungen wirkt **½ Tag als optimistische Schätzung**, nicht als belastbare Zusage.

Den Schritt in überprüfbare Teile zerlegen:

- **Messhygiene:** Manifest, Dateischema, getrennte RTT-Daten und Tabellen je Lauf.
- **Turn-Bilanz:** `utterance_id` beim Einspeisen; Zuordnung der erkannten Turns und Antworten; genau ein Abschlussstatus je angebotener Äußerung. Zerfall in mehrere Turns und Antwort auf unvollständige Eingabe ebenfalls erfassen. Gleiche Gesamtzahlen allein beweisen keine korrekte Zuordnung.
- **Audiotiming:** erstes Audio, Beginn des Hauptsatzes und zunächst manuell bewerteter Beginn der relevanten Antwort getrennt benennen. Kaltstart in der Gesamtbilanz behalten und zusätzlich separat zeigen.

Ein „Nein“ kann bereits Inhalt sein; ein zweiter Satz kann eine Floskel sein. Der im Plan vorgesehene zweite Satz ist daher nur eine Hilfsmetrik. Bei TextStream bleibt dieselbe semantische Definition erforderlich, auch wenn Request- und Satzgrenzen anders aussehen.

Für die Kontrollmessung vorab festlegen: Anzahl der Sitzungen, Reihenfolge, Konfiguration, Ausschlussregeln und Kriterien für vollständige Antworten. Historische Einstellungen nur anhand belegbarer Logs rekonstruieren; aktuelle Defaults nicht rückwirkend einsetzen.

## 4. Schritt 2: Browser ist richtig priorisiert, Infra-Aufgaben fehlen

Die lokalen Dateien sind ein Entwicklungssetup: `docker-compose.yml` verwendet `--node-ip 127.0.0.1`, `livekit.yaml` setzt `use_external_ip: false` und enthält `devkey: secret`. **Firewall öffnen allein macht daraus keinen erreichbaren VM-Sprachpfad.**

Der Plan sollte ergänzen: Domain beziehungsweise gewählter Zugriffspfad, TLS für den entfernten Browserbetrieb, passende angekündigte Adresse und Medienports, eigene Server-Keys und serverseitig erzeugte, begrenzte Raumtokens. Das API-Secret gehört nicht ins Frontend. TURN/Fallback wird spätestens relevant, wenn die vorgesehenen Testnetze UDP blockieren. LiveKit dokumentiert TLS und Zugriffstokens als Bestandteile des Verbindungsaufbaus. [LiveKit: Deployment](https://docs.livekit.io/transport/self-hosting/deployment/), [Zugriffstokens](https://docs.livekit.io/frontends/reference/tokens-grants/).

Das verlangt keine komplette Nutzerverwaltung. Ein begrenzter Testzugang genügt für den PoC. Die zusätzliche Arbeit sollte aber in der 1–2-Tage-Schätzung sichtbar sein.

**Messdefinition ergänzen:** Server-Audioanfang und tatsächlicher Hörbeginn am Browser getrennt messen. Client- und Serverzeitstempel verschiedener Uhren dürfen nicht unkalibriert subtrahiert werden. Für eine erste Abnahme kann ein gemeinsamer lokaler Audiomitschnitt Nutzerende und Botbeginn zeigen; für automatisierte Werte braucht es eine erläuterte Zeitbasis.

Die pauschalen 50–150 ms Browseraufschlag bleiben eine unbestätigte Größenordnung. Den gemessenen Wert berichten. Barge-in lässt sich auch lokal sinnvoll testen; **der Nachweis am Zielendgerät** ist zusätzlich nötig. Der ursprüngliche Phase-0-Plan nennt die Webansicht unter „Kann“, plant WebRTC aber im Aufbau ausdrücklich ein: Browserrelevanz ist sachlich richtig, die formale Abnahmedefinition sollte konsistent gemacht werden.

## 5. Schritt 3: gute Parallelisierung, Testdesign ergänzen

20–30 Aufnahmen von Pit sind ein sinnvoller Anfang, aber eine Stimme deckt weder deutsche Sprachvariation noch verschiedene Mikrofone ab. Das Korpus als erste Robustheitsprobe kennzeichnen. Regieanweisungen erzeugen gezielte Grenzfälle; einige spontan formulierte Äußerungen ergänzen, damit nicht nur künstlich gesetzte Pausen getestet werden.

Pro Aufnahme sollten Referenztext, tatsächliche interne Pausen, gewollte Turn-Grenze und erwartete Mindestinformationen vorliegen. Besonders wichtig: spätes „nicht“, korrigierte Beträge, mehrere Fragen und „mhm“ während der Botantwort. Diese Fälle prüfen, ob Tempo auf Kosten des Verstehens gewonnen wird.

„Nur für Tests, nicht weitergeben“ ist missverständlich, wenn Audio an Azure zur Verarbeitung übertragen wird. Die Aufnahmeanleitung sollte tatsächlichen Testpfad, verarbeitende Dienste, Speicherort und Löschung klar beschreiben. Das ist eine praktische Klarstellung, keine rechtliche Bewertung.

**VAD-/Segmentierungs-Kurve nach Fertigstellung des Korpus wieder einplanen.** Sie darf nicht nur unter „zurückgestellt“ verschwinden: Gerade der Default von 100 ms benötigt diese Validierung, bevor kompliziertere Architekturhebel sinnvoll beurteilt werden können.

## 6. Schritt 4: Diagnose vor Adapterbau, Gewinne offen lassen

Die Azure-Ressourcenregion zu prüfen ist eine kleine Diagnose und kann sofort parallel stattfinden. Erst danach entscheiden, ob ein neues Deployment einen Versuch rechtfertigt. 28 statt 5 ms RTT lokalisiert keine Inferenz zuverlässig. Bei EU-Data-Zone-Deployments kann Verarbeitung innerhalb der Zone geroutet werden; eine Ressource in Germany West Central garantiert daher nicht allein Inferenz in Frankfurt. [Microsoft: Deployment-Typen](https://learn.microsoft.com/azure/ai-services/openai/how-to/deployment-types).

**TextStream bleibt eine Hypothese.** Der Plan sollte „kann die Latenz senken“ schreiben und identischen Text mit identischer Stimme gegen den bestehenden Adapter prüfen. Beim besten Laptoplauf waren nur rund 14 ms Satzwartezeit dokumentiert. Daraus entsteht keine Zusage, die fehlenden 100–300 ms zu gewinnen. Vorteile für längere natürliche Antworten und Klangkontinuität sind separat zu untersuchen.

Spekulativer LLM-Start ist korrekt zuletzt eingeordnet. Audiofreigabe muss neben der bestätigten Turn-Grenze auch die Verifikation des finalen Transkripts verlangen. Sonst wäre die Persona trotz korrektem Turn-Ende auf einer falschen Textversion unterwegs. Abgebrochene Kandidaten dürfen den Gesprächskontext nicht verändern; verspätete Ergebnisse müssen verworfen werden.

Für jeden Hebel ein vorher festgelegtes Entscheidungskriterium: reproduzierbarer Gewinn bei gleicher Antwortqualität und ohne höhere Fehlerrate. Kein Vorteil oder schlechtere Qualität bedeutet Rückkehr zur Referenz und Abschluss des Versuchs, nicht weitere unbegrenzte Optimierung.

## 7. Schritt 5 gehört früher

Filtersignale, Barge-in und verworfene spekulative Antworten benötigen dieselbe Fähigkeit: laufende Generierung beziehungsweise Synthese stoppen, gepuffertes Audio entfernen und verspätete Chunks einer alten Antwort blockieren. **Diesen gemeinsamen Abbruchpfad beim Browserdurchstich bauen**, statt die Filterbehandlung erst nach neuen Streaming-Adaptern anzuhängen.

Die Aussage „für Messläufe unkritisch“ ist zu pauschal: Ein nachträglicher Filterabbruch muss auch dort als Ergebnisstatus auftauchen. Sobald Menschen die Ausgabe hören, betrifft er bereits das Testgespräch. Ein deterministisch eingespeistes Filtersignal eignet sich zur Funktionsprüfung; problematische Modellantworten sind dafür nicht erforderlich.

## 8. Der Plan endet vor der Phase-0-Abnahme

Im [ursprünglichen Plan](phase-0-proof-of-concept.md) stehen weitere Muss-Kriterien. Sie fehlen als konkrete Aufgaben:

| Kriterium | Ergänzung zum Arbeitsplan |
|---|---|
| Deutsche Sprachqualität | Beide Gründer bewerten unabhängig; definierte Skala und dokumentiertes Ergebnis. |
| Barge-in | Mindestens zehn gezielte Fälle; ≤300 ms in mindestens neun Fällen am relevanten Endgerät prüfen. |
| Rollen-Konsistenz | Zehn vollständige Testgespräche mit Budget- und Geduldprüfungen; Regex allein genügt nicht. |
| EU-Dokumentation | Region, Deployment-Typ und DPA-Verfügbarkeit pro Dienst nachvollziehbar festhalten. |
| Kosten | STT, LLM und TTS je realer Gesprächsminute; Warm-up und verworfene spekulative Anfragen einbeziehen. |
| Reproduzierbarkeit | Dritte Person startet den dokumentierten lokalen Pfad; Browserzugang separat beschreiben. |
| Ergebnisdokument | `phase-0-ergebnisse.md` mit Stackempfehlung, offenen Kriterien und Go/No-Go. |

Lernerfolg als spätere Nutzerprüfung zurückzustellen ist richtig. **Sprachqualität und realistische Gründer-Testgespräche dürfen dadurch nicht ebenfalls in Phase 1 verschoben werden.**

## 9. Empfohlene Reihenfolge

1. Messhygiene und Turn-Bilanz; parallel Aufnahmeliste und Azure-Deployment-Diagnose.
2. Browserdurchstich einschließlich gemeinsamem Abbruchpfad und Audiomessung.
3. Robustheitsprobe, Segmentierungsvergleich und Gründer-Qualitätsprüfung.
4. Nur bei weiter offenem Tempoengpass gezielte Architekturversuche mit festem Abschlusskriterium.
5. Vollständige Phase-0-Ergebnistabelle und bewusste Go/No-Go-Entscheidung.

Die genannten Aufwände eignen sich als erste Orientierung. Für robustes Timing, Browserkonnektivität und Adapter-Abbruchverhalten fehlen noch ausreichend konkrete Annahmen für verlässliche Termine. **Freigeben würde ich den nächsten begrenzten Arbeitsschritt mit klaren Abschlusskriterien; die gesamte Folge nicht als garantierte kurze Umsetzung betrachten.**
