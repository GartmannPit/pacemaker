# Prüfung der Phase-0-Ergebnisse

**Stand:** 14. Oktober 2026 · **Geprüfter Stand:** `main`, `6cf5636`.
**Umfang:** Ergebnisbericht, Phase-0-Plan, Summary bis §26, Vorverbindungs-Präregistrierung, aktuelle Mess-/Auswertungspfade sowie lokal verfügbare Rohdaten. Keine neuen Provider-Messungen, keine Änderung der Abnahmekriterien oder der Agent-Pipeline.

## Gesamtbewertung

**„Phase 0 ist nach den ursprünglichen Kriterien nicht bestanden“ ist weiterhin richtig.** Der Bericht enthält belastbare Fortschritte: Die Vorverbindung vermeidet den wiederholten Verbindungsaufbau, und die Probleme beim Turn-Taking sind in den T1-Daten reproduzierbar.

Für eine Go/No-Go-Entscheidung sind jedoch vier Korrekturen nötig: die Latenz-Auswahl offenlegen, das ursprüngliche Rollentreue-Kriterium als teilweise erfüllt führen, aus fehlendem Zielerfolg keine allgemeine technische Unmöglichkeit ableiten und die Schlussfolgerung zur TTS-Serverzeit enger formulieren.

## 1. [P1] Die aktuelle E2E-Referenz schließt gesprochene Werkzeugantworten aus

**Fundstellen:** `docs/phase-0-ergebnisse.md:61` und `:159`; `docs/2026-10-14-tts-vorverbindung.md:48`; Summary §26.

Die veröffentlichten Werte 1201/1442 ms ohne und 1106/1335 ms mit Vorverbindung lassen sich exakt reproduzieren, wenn nur Turn-Ledger-Zeilen mit **sowohl `first_text_ms` als auch `first_audio_ms`** verwendet werden. Damit bleiben je Bedingung 70 normale Textantworten übrig.

Je Bedingung liegen daneben **neun beantwortete Turns ohne normales LLM-Textdelta** vor. Das sind gesprochene Abschiede über `auflegen`; sie besitzen einen gültigen Audiobeginn. Für „erster Text → Audio“ fehlen ihnen die nötigen Textzeitpunkte. Für E2E „Sprechende → erstes Audio“ sind sie dagegen verwertbar und sollten nicht wegen des fehlenden Textdeltas entfallen.

Nachrechnung mit linear interpolierten Quantilen, wie im Projekt-Aggregator:

| Auswahl | Ohne Vorverbindung n | p50 / p90 | Mit Vorverbindung n | p50 / p90 |
|---|--:|--:|--:|--:|
| Normale Textantworten mit Text- und Audiozeitpunkt | 70 | 1200,8 / 1441,5 ms | 70 | 1105,8 / 1335,3 ms |
| Alle als beantwortet klassifizierten Turns mit gültigem Audiobeginn | 79 | 1226,5 / 1520,9 ms | 79 | 1118,0 / 1389,2 ms |

Der Collector bestätigt die zweite Zeile bis auf Rundungs-/Beobachterdifferenzen: 1226,4/1520,7 gegenüber 1117,7/1389,0 ms.

**Folge:** Der Nutzen der Vorverbindung bleibt bestehen. Für die vollständigere E2E-Auswahl beträgt die Differenz ungefähr **−109 ms p50 / −132 ms p90**. Das präregistrierte Primärkriterium bleibt auch so verfehlt. Die neue Rechnung ersetzt die präregistrierte Auswahl nicht stillschweigend; sie ergänzt die Aussage über die aktuelle E2E-Referenz.

Die vollständige Bilanz je Bedingung lautet: **90 angebotene Clip-Fenster = 70 normale Antworten + 9 Werkzeugabschiede + 1 Turn ohne Antwort + 10 Fenster ohne Turn-Erkennung.** Alle zehn letztgenannten Fenster beginnen nach einem bereits protokollierten `aufgelegt`; sie sind damit ein Testablauf-Artefakt und nicht zehn verpasste Antworten eines laufenden Gesprächs. Der eine Turn ohne Antwort liegt dagegen vor dem Gesprächsende und muss gesondert berichtet werden. Er kommt in beiden Bedingungen vor; daraus folgt kein Nachweis eines zusätzlichen Fehlers durch Vorverbindung.

**Empfohlene Korrektur:** E2E und Text→Audio mit getrennten Nennern zeigen. Die Tabelle ausdrücklich als gepoolte Antworten über mehrere Sitzungen kennzeichnen; „3 × 30“ beschreibt die angebotenen Clipfolgen, nicht drei ununterbrochene Gespräche mit je 30 Antworten. Fehlende Antworten und End-Artefakte daneben ausweisen. Nicht sämtliche Fälle mit fehlendem LLM-Text als fehlgeschlagene Antworten behandeln.

## 2. [P2] Rollentreue ist gegenüber dem ursprünglichen Muss nur teilweise belegt

**Fundstellen:** `docs/phase-0-ergebnisse.md:40` und `:163`; ursprüngliches Kriterium `docs/phase-0-proof-of-concept.md:98`; Summary §20.1.

Der Plan fordert Rollen-Konsistenz in zehn vollständigen Gesprächen von ungefähr fünf Minuten. §20 belegt einen sinnvollen Texttest mit zehn Anrufertypen und einem nachgebesserten Prompt. Die Summary benennt selbst als Grenze: konstruktive Gespräche umfassen meist vier bis fünf Persona-Beiträge bzw. etwa 1,5–2 Minuten statt fünf Minuten. Der engere Test „mindestens vier Beiträge bei konstruktiven Anrufern“ wurde bestanden; das ursprüngliche Dauerkriterium damit nicht vollständig geprüft.

**Empfohlener Status:** „Teilweise erfüllt: kurzer Textmodus bestanden; längere Sprachgespräche und ursprüngliche Gesprächsdauer noch offen.“ Das ist kein Nachweis eines Rollenbruchs und kein Grund, `nano` wieder zu empfehlen. Es verhindert lediglich, dass ein engerer Test das ursprüngliche Muss ersetzt.

Die Kurzfassung „zwei Muss-Kriterien verfehlt, drei Gründer-Bewertungen offen“ sollte diese zusätzliche technische Nachweislücke nennen. Auch Option A braucht entweder den ausstehenden Nachweis oder eine ausdrücklich beschlossene Änderung des Kriteriums.

## 3. [P1] Fehlender Zielerfolg beweist keine allgemeine Unerreichbarkeit mit EU-Diensten

**Fundstelle:** `docs/phase-0-ergebnisse.md:146–162`, insbesondere „900 ms p90 sind mit heutigen EU-Diensten nicht erreichbar“ und „Ungemessen bleiben nur kleine Hebel“.

Geprüft wurde eine umfangreiche, aber endliche Menge von Konfigurationen. Der souveräne Stack fehlt ausdrücklich; spekulativer Start und Vorverbindung sind nicht gemeinsam vermessen. Auch andere Betriebs- oder Architekturvarianten sind durch die vorhandenen Versuche nicht ausgeschlossen.

Die Schätzung von etwa 1,27 s p90 für die Kombination ist als Schätzung markiert, sollte aber nicht als Nachweis einer technischen Untergrenze dienen. Effekte aus verschiedenen Messreihen können sich überlappen, untereinander verändern und zu unterschiedlichen Zeitpunkten von Dienststreuung betroffen sein. Quantile lassen sich nicht durch schlichtes Addieren oder Subtrahieren von Einsparungen kombinieren.

**Tragfähige Formulierung:** „Keine bislang getestete Konfiguration hat das Ziel erreicht. Für den geprüften Azure-Pfad ist derzeit kein ausreichend großer, nachgewiesener weiterer Gewinn vorhanden. Weitere Architekturversuche würden zusätzliche Zeit und gegebenenfalls andere Betriebsbedingungen erfordern.“

Das erlaubt eine begründete Entscheidung, die Optimierung vorläufig zu beenden. Es rechtfertigt weder eine allgemeine Unmöglichkeitsaussage noch die Behauptung, ein anderer EU-Pfad sei sicher schnell genug.

## 4. [P2] TTS-Serverzeit: zeitliche Schwankung ist plausibel, als alleinige Ursache nicht bewiesen

**Fundstellen:** `docs/2026-10-14-tts-vorverbindung.md:75–84`; Summary §26, letzte drei Zeilen; Ergebnisbericht §6.1.

Die 2×2-Tabelle zeigt im zweiten Lauf für alle Varianten niedrige Serverzeiten. Das stützt eine starke zeitliche oder verbindungsbezogene Schwankung. Im ersten Lauf liegt aber **16 kHz mit Wortmarken** bereits durchgehend bei 24–47 ms, während mehrere andere Varianten zunächst etwa 200 ms aufweisen. Die Varianten schwanken in dieser Tabelle also nicht durchgehend „gleichzeitig“.

Ohne Rohdaten mit eindeutiger Zuordnung von Anfragezeit, Verbindung und Variante sowie ohne das auf der VM liegende Probeskript kann die Ursache dieses Musters hier nicht unabhängig aufgelöst werden. Die lokale Prüfung bestätigt daher nicht die stärkeren Sätze „ist damit Messzeitpunkt, keine Konfiguration“ und „kein weiterer Hebel auf unserer Seite“.

**Empfohlene Formulierung:** „In diesen Kurzversuchen zeigte sich kein über beide Läufe konsistenter Vorteil von Abtastrate oder Wortmarken. Erhebliche zeitliche bzw. verbindungsbezogene Streuung ist eine plausible Erklärung der früheren Differenz; die alleinige Ursache ist nicht isoliert nachgewiesen.“

Daraus folgt keine Pflicht zu einer weiteren Messrunde. Die begrenzte Aussage reicht für die Entscheidung, diese beiden Einstellungen aktuell nicht zu ändern.

## Was durch die Prüfung bestätigt wurde

- **Vorverbindung:** Bei Auswahl erster Synthesen je Turn anhand `idle_s` (erste Anfrage oder mehr als eine Sekunde Abstand) reproduzieren die Diagnose-Rohdaten 79/80 Neuaufbauten ohne und 0/80 mit Vorverbindung. Die mediane Neuaufbauzeit beträgt 79 bzw. 0 ms, die mediane SDK-Serverzeit in beiden Bedingungen 193 ms. Der technische Mechanismus und ein relevanter Nutzen sind belegt.
- **T1-Turn-Taking:** Aus sechs Sitzungen mit 63 angebotenen Äußerungen lassen sich F1=3, F2=29 und F3=23 reproduzieren. Für die 31 Fälle ohne F1/F2 ergeben sich p50 1186,9 und p90 1830,3 ms. Diese Latenz ist ausdrücklich bedingt auf die ausgewählte Teilmenge und keine Erfolgsquote aller 63 Äußerungen.
- **Transkript/Export:** Aufzeichnungs- und Exportpfade für Text sowie Beginn-/Endzeitpunkte sind vorhanden. Das sind serverseitige Ereigniszeitpunkte; ein Browser-Hörnachweis folgt daraus nicht.
- **Tests:** Die aktuelle lokale Offline-Suite besteht mit **24 bestandenen Tests**. Sie belegt nicht die deutsche Sprachqualität, Provider-Latenzen oder Fehlerfreiheit unter Last.
- **Offene Gründerprüfungen:** Stimmqualität, Reproduzierbarkeit durch Dritte und vertragliche Prüfungen sind weiterhin offen markiert. Eine rechtliche Freigabe wurde in dieser Prüfung nicht durchgeführt.

Die Detailangaben zu Barge-in aus §19 konnten mangels lokaler T2-Rohdaten nicht neu nachgerechnet werden. Die isolierten Aura-/Azure- und 2×2-Probeskripte werden in den Dokumenten als Dateien auf der VM genannt; sie lagen für diese lokale Prüfung nicht vor. Die F4-Angabe 3/53 enthält eine manuelle Bewertung durch Claude; geprüft wurden die protokollierte Auswertung und die Einschränkungen, nicht sämtliche inhaltlichen Urteile erneut.

## Empfehlung für die Entscheidung

**Phase 0 weiterhin als nicht bestanden führen.** Den aktuellen Stand als funktionierenden, noch nicht produktreifen Voice-PoC beschreiben. Die Vorverbindung beibehalten; ihre dokumentierte Ausnahme vom Primärkriterium ist nachvollziehbar. „Kein zusätzliches Risiko“ dabei durch „keine zusätzlichen Fehler im Versuch beobachtet“ ersetzen.

Ein begrenzter Einstieg in Phase 1 ist eine vertretbare Gründerentscheidung, wenn das Latenzziel bewusst angepasst wird und die offenen Nachweise eingeplant sind. Der nächste technische Schwerpunkt sollte das Turn-Taking sein. Für dessen Verbesserung vorab eigene Erfolgskriterien festlegen: unerwünschte Antworten während Denkpausen, verpasste Kurzantworten, Unterbrechung durch Hörersignale und Erhalt kritischer Inhalte. Eine bloße Änderung von 900 auf 1500 ms löst diese Probleme nicht.

Eine Produktfreigabe oder ein Nachweis eines akzeptierten Nutzererlebnisses ergibt sich daraus noch nicht. Dafür fehlen insbesondere die tatsächliche Hörbewertung, der Browserpfad und Tests mit echten Nutzern.
