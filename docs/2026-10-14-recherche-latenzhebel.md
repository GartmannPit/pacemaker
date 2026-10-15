# Weitere Latenzhebel für Pacemaker

**Stand:** 14. Oktober 2026 · **Art:** Codeanalyse, Prüfung vorhandener Messdaten und externe Recherche. Keine neuen Provider-Aufrufe oder Änderungen an der Agent-Pipeline.

## 1. Ergebnis

**Es gibt weitere Hebel. Ein belastbarer Weg zu p90 < 900 ms ist damit noch nicht nachgewiesen.** Am aussichtsreichsten ist ein isolierter Vergleich anderer deutscher TTS-Engines mit EU-Verarbeitung. Danach folgen stabilere spekulative Antwortberechnung und eine kontextabhängige Turn-Erkennung. Kleine Änderungen an Satzlänge, Stimmenwahl und Verbindungen können ergänzen; ihre Gewinne dürfen nicht einfach addiert werden.

Der bestehende Azure-Stack ist bereits gründlich optimiert. Azure-Textstreaming, ein bloßer STT-Wechsel oder ein neueres LLM sollten nach den bisherigen Ergebnissen nicht erneut die ersten Experimente sein. Die größere Architekturfrage ist, wie Verarbeitung während einer noch offenen Sprechergrenze erfolgen kann, ohne veraltete Antworten hörbar auszugeben.

## 2. Untersuchte Grundlage

Arbeitszweig: `stt-vergleich`, Revision `6d72927`. Zusätzlich wurden die lokal vorhandenen Zweige `main` (`ab2ac09`) und `spekulativer-start` (`733a514`) gelesen, ohne den Arbeitszweig zu wechseln. Das ist entscheidend: Die Zusammenfassung im Arbeitszweig endet bei §22; auf `main` enthält dieselbe Datei bereits die Ergebnisse §23–25.

Geprüft wurden insbesondere:

- `agent/src/pacemaker_agent/{pipeline,stacks,config,main}.py`, Persona, Metrik- und Testablauf.
- Lokal installiertes Pipecat, insbesondere Azure TTS und Deepgram Flux STT/TTS; Version laut Messmanifesten 1.8.1.
- `main:experiments/summaries/2026-10-03-llm-modellvergleich-deployment-typen.md`, insbesondere §15 und §19–25.
- `spekulativer-start:agent/src/pacemaker_agent/speculation.py` und dessen Experimentplan.
- Lokale Rohdaten unter `experiments/runs/{latenz-mini-2,spekulation-mini,stt-vergleich,t1-gespraech-mini}/`.

Die jüngeren Manifeste nennen `dirty=true`. Commit-ID und Paketversion dokumentieren daher nicht vollständig den tatsächlich ausgeführten Quellstand. Das Azure-Textstreaming-Probeskript liegt laut §25 auf der VM und wurde hier nicht ausgeführt oder vollständig geprüft. Seine Werte sind dokumentierte Projektbefunde, keine unabhängige Replikation.

## 3. Wo die Zeit entsteht

Der aktuelle Produktkandidat ist Azure STT → `gpt-4.1-mini` → Azure TTS. Die Rollentests sprechen für `mini`; das schnellere `nano` beendet konstruktive Gespräche häufig zu früh. README und `.env.example` empfehlen im Arbeitszweig noch `nano`; das passt nicht mehr zur jüngeren Ergebnisempfehlung.

| Vorhandener Versuch | Ergebnis | Bedeutung |
|---|---|---|
| `mini`, Kontrollmessung, 12.10., §21 | p90 1250–1455 ms je Sitzung | Das Ziel wird bereits ohne Browser verfehlt. |
| Zusammenhängendes Gespräch mit echten Aufnahmen, §21 | p50 1187 / p90 1830 ms, n=31 ohne F1/F2 | Bedingte Latenz; schwierige, fehlerhafte Turns sind separat zu bewerten. |
| Spekulation, §23 | Ohne: 1182/1362 ms; mit: 1056/1298 ms, p50/p90 | Gewinn 126/64 ms; präregistriertes p50-Ziel von 150 ms verfehlt. |
| STT-Vergleich, §24 | Azure 1312/1837; Flux 1362/1718; Gladia 1546/1840 ms | Keine klare Ablösung durch einen schnelleren STT-Anbieter. |
| Azure TextStream, direkte Probe, §25 | Hörbeginn satzweise 704/988; TextStream 871/1254 ms | In dieser Probe langsamer. Kein vollständiger E2E-Lauf. |

Werte dieser Tabelle sind die dokumentierten Auswertungen auf `main`; Bedingungen und Auswertungsmengen unterscheiden sich. Sie sind keine gemeinsame Vergleichsstichprobe.

Die Kontrollrohdaten vom 12.10. enthalten 81 Antworten mit einer gemessenen TTS-TTFB von etwa **270 ms p50 / 353 ms p90**. Der je Antwort berechnete Rest `E2E − Turn-Erkennung − LLM-TTFB − TTS-TTFB` liegt bei **151 ms p50 / 329 ms p90**. Dieser Rest umfasst insbesondere Textaggregation und weitere Übergänge, nicht ausschließlich Rechenaufwand von Pipecat. Die Pipeline-Zerlegung in §25 nennt beispielhaft 86–150 ms bis zum ersten Satzende, 250–390 ms für TTS und etwa 8 ms bis zum Ausgabestart. Das spricht gegen einen großen Gewinn durch bloßes Verschlanken des Python-Codes.

Quantile der Einzelabschnitte lassen sich nicht zum E2E-p90 addieren: Die langsamen Abschnitte müssen nicht in denselben Turns auftreten. Änderungen an Auswertung oder Ausschlüssen verändern ebenfalls die Zahlen.

## 4. Priorisierte offene Hebel

### A. Andere TTS-Engine, STT und LLM unverändert — höchste Experimentpriorität

**Deepgram Aura-2 ist ein konkreter Kandidat.** Die aktuellen Herstellerunterlagen nennen deutsche Stimmen, etwa `aura-2-fabian-de` und `aura-2-julius-de`. Der EU-Endpunkt unterstützt TTS über `wss://api.eu.deepgram.com/v1/speak`; Deepgram beschreibt Verarbeitung und Speicherung innerhalb der EU ohne automatischen regionsfremden Fallback. Das ist eine andere Frage als der bereits durchgeführte Flux-STT-Vergleich. Quellen: [Stimmen](https://developers.deepgram.com/docs/tts-models), [regionale Endpunkte](https://developers.deepgram.com/reference/regional-endpoints), [Datenverarbeitung](https://developers.deepgram.com/trust-security/your-data).

Der installierte `DeepgramTTSService` erlaubt `base_url`, PCM, Stimmenwahl und Unterbrechung per `Clear`. Ein Adapter ausschließlich in `stacks.py` ist deshalb plausibel. Zuerst satzweise senden, damit ein Vergleich nicht gleichzeitig Provider und Textaggregation verändert. Anschließend separat kleinere Textabschnitte und Flush-Verhalten untersuchen. Modellverbesserung explizit abwählen und AVV-Verfügbarkeit vor einem Produktpfad prüfen, entsprechend der vorhandenen Projektvorgabe.

**ElevenLabs Flash ist eine zweite, bedingte Option.** EU-Residency ist ein Enterprise-Angebot mit eigenem API-/WebSocket-Endpunkt und separatem Account. Speicherung in der EU allein garantiert laut Hersteller keine ausschließliche EU-Verarbeitung. Die dokumentierte Kombination aus EU-Umgebung, API und Zero Retention Mode kann diese Beschränkung herstellen; optionale externe Integrationen können sie wieder aufheben. Quellen: [Residency](https://elevenlabs.io/docs/overview/administration/data-residency), [Latenzoptimierung](https://elevenlabs.io/docs/eleven-api/guides/how-to/best-practices/latency-optimization).

**Nutzenhypothese:** Gegenüber etwa 250–350 ms Azure-TTS könnte eine Engine mit tatsächlich gemessenen 100–200 ms bis zum hörbaren PCM grob 50–250 ms pro betroffener Antwort sparen. Das ist eine Rechenannahme, kein Anbieterbenchmark. Beworbene Inferenzzeiten wie 75 ms und erste Pakete sind keine E2E-Hörlatenz. Die deutsche Stimmqualität, die EU-Verfügbarkeit des konkreten Modells sowie das Verstummen bei Unterbrechungen entscheiden mit.

### B. Spekulation stabilisieren statt die Pausenschwelle weiter senken

Dieser Ansatz wurde bereits gebaut: LLM **und TTS** laufen vorzeitig, Audio bleibt hinter einer Schleuse. Eine reine Empfehlung „TTS ebenfalls vorab starten“ wäre daher keine neue Verbesserung.

Eigene Nachrechnung der vorhandenen Spekulationsprotokolle: **181 Starts, 81 Bestätigungen, 100 Verwerfungen; davon 99 wegen neuem Text und eine wegen Weitersprechen.** Von den 99 direkt anschließenden Neustarts ergänzen 69 lediglich Wörter am bisherigen normalisierten Text; 30 ändern auch vorhandene Tokens. Beispiele enthalten nachgereichte Satzenden, Wortvervollständigungen und `gmb h` → `GmbH`. Der dokumentierte Vorsprung bestätigter Kandidaten beträgt im Median nur 73 ms.

Ein enger nächster Versuch wäre ein kurzer Stabilitätsfilter für Zwischentranskripte oder ein Start beim letzten finalen STT-Segment, während die Turn-Erkennung noch offen ist. Dadurch entstehen weniger sinnlose Neustarts. Zu langes Warten verbraucht allerdings genau den gewünschten Vorsprung. Deshalb **Startvorsprung, Bestätigungsquote, verworfene Tokens und Audiofreigabe gemeinsam messen**.

Formatvarianten können kontrolliert normalisiert werden. Inhaltliche Unterschiede bei Negationen, Zahlen, Namen oder Korrekturen dürfen nicht als „ähnlich genug“ akzeptiert werden. Der große Anteil nachgereichter Wörter spricht gegen ein großzügiges semantisches Wiederverwenden alter Entwürfe. Ein Kandidat braucht eine eindeutige ID, und nach Abbruch dürfen weder Audio noch Werkzeuge noch Kontextänderungen durchrutschen; eine bloße Timeout-Öffnung der Schleuse ist dafür kein Nachweis.

**Flux EagerEndOfTurn** kann einen früheren, strukturierten Start liefern; `TurnResumed` ermöglicht Abbruch. Im aktuellen Adapter ist `eager_eot_threshold` nicht gesetzt. Der installierte Pipecat-Code stellt Ereignisse bereit, enthält aber ausdrücklich keine fertige Schleuse zur spekulativen Verarbeitung. Dieser Versuch braucht daher eigene Bestätigung und Stornierung. Die Herstellerangaben zu möglichen Gewinnen sind nicht auf Pacemaker übertragbar. Quelle: [Deepgram Eager EOT](https://developers.deepgram.com/docs/flux/voice-agent-eager-eot).

### C. Turn-Ende und Unterbrechung nach Gesprächskontext steuern

Eine globale geringere VAD-Wartezeit beschleunigt kurze Antworten, erhöht aber das Risiko, Denkpausen oder „Mhm“ als Sprecherwechsel zu behandeln. Die bisherigen VAD- und Barge-in-Versuche zeigen diesen Zielkonflikt.

Ein offener Architekturversuch ist eine **text- und zustandsabhängige Grenze**: Nach einer eindeutigen Ja/Nein-Frage kann ein finalisiertes „Nein“ früher reichen; bei „weil …“, begonnenen Zahlenkorrekturen und offenen zweiteiligen Fragen bleibt die Grenze offen. Ein zusätzlicher entfernter LLM-Aufruf pro Grenze wäre selbst ein Latenzrisiko. Zunächst kleine lokale Regeln oder einen kleinen lokalen Textklassifikator prüfen, mit begrenzter Wartefrist und normalen Fallbacks.

Antwortberechnung und Audiofreigabe sollten getrennte Entscheidungen sein: früh rechnen, nach einer bestätigten Grenze freigeben, bei Fortsetzung verwerfen. Das kann Robustheit und Latenz besser vereinbaren als pauschal längere Stille. Es kann eine künftig gesprochene Korrektur dennoch nicht vorhersagen.

Die vorhandene offene Einordnung von Smart Turn und dem Prosodie-Verbot bleibt bestehen. Dieser Vorschlag benötigt keine neue Stimme-, Emotions- oder Stressanalyse und verändert die Produktvorgabe nicht.

### D. Azure-Stimme, Sprache und ersten Inhaltsabschnitt optimieren — kleine, günstige Versuche

Im Arbeitszweig wird `de-DE-ConradNeural` gewählt, die TTS-Sprache aber nicht explizit gesetzt. Der installierte Azure-Adapter hat `en-US` als Default. Pipecat richtet auch die Satzsegmentierung an der TTS-Sprache aus. `Language.DE` explizit zu setzen ist deshalb ein sinnvoller Konfigurationsvergleich, insbesondere für Abkürzungen und Satzgrenzen; ein Geschwindigkeitsgewinn ist nicht bewiesen. Quelle: [Pipecat TTS](https://docs.pipecat.ai/pipecat/learn/text-to-speech).

Zwei oder drei alternative deutsche Azure-Stimmen mit identischen Texten und vorgewärmten Verbindungen vergleichen. Microsoft weist darauf hin, dass verfügbare Backend-Kapazität von Stimme und Region abhängt. Daraus folgt eine Testhypothese, keine belegte schnellere Stimme. Quelle: [Azure TTS FAQ](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/faq-tts).

Kurze **inhaltliche** erste Sätze oder eine erste Synthese an einer sicheren Teilsatzgrenze können die Aggregationswartezeit senken. Ein kurzer Platzhalter vor der eigentlichen Antwort wurde dagegen bereits verworfen. Kommas blind als Grenze zu verwenden kann Zahlen, Einschübe und Aussprache zerlegen. Potenzial anhand des tatsächlich gemessenen ersten Satzes bestimmen; keine pauschalen 300 ms erwarten.

### E. Prompt-Cache und Startbereitschaft absichern

Der bestehende Warm-up-Aufruf sendet „Hallo“ und einen Token; er wärmt Verbindungen, verwendet jedoch nicht den Persona-Prefix samt Werkzeugen. Das Aufwärmen läuft im Hintergrund, ohne dass der Gesprächsbeginn dessen Abschluss abwartet. Ein früher Nutzerturn kann deshalb mit dem Warm-up konkurrieren.

Offene kleine Versuche: beim Verbindungsaufbau den exakten stabilen Persona-/Werkzeug-Prefix vorwärmen, einen kurzen Readiness-Zustand anbieten und tatsächliche Cache-Treffer erfassen. Dynamische Persona-Zustände hinter den stabilen Prefix setzen. Nicht den Gesprächsverlauf bei jedem Turn verschieben: Der frühere Sliding-Window-Versuch verschlechterte bereits Cache und Latenz. Cache-Treffer sind kein garantiertes Ergebnis jedes Warm-ups. Quelle: [Azure Prompt Caching](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/prompt-caching).

Dieser Hebel betrifft besonders erste Turns und Lastverhalten. Er ist keine Erklärung für sämtliche warmen langsamen Antworten.

### F. Standort und reservierte Kapazität — nach Diagnose, vor Lastskalierung

Agent näher an Speech und LLM platzieren bzw. tatsächlich regionale EU-Deployments vergleichen. Eine Foundry-Ressource in Deutschland mit Data Zone Standard garantiert keinen Inferenzstandort Deutschland. Beim strikten Projektwortlaut „ausschließlich EU“ ist zudem die aktuelle Definition der Azure EU Data Boundary zu beachten: Microsoft nennt auch EFTA-Länder. Ein regionales Deployment in einem EU-Mitgliedstaat kann die Ortsannahme präziser machen. Quelle: [Deployment-Typen](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/deployment-types).

PTU hält Verarbeitungskapazität vor und ist deshalb besonders für geringere Streuung unter Last interessant. Regional Provisioned oder passend eingegrenztes Data Zone Provisioned sind Kandidaten, sofern Modell, Region und Kontingent passen. Mindestkapazität und stundenweise Kosten machen einen kurzen Vergleich sinnvoller als eine sofortige Reservierung. Es ist kein Nachweis für 900 ms. Quelle: [Provisioned Throughput](https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/provisioned-throughput).

**Priority Processing scheidet für den heutigen EU-Pfad aus:** Die aktuelle Verfügbarkeit nennt Global Standard und Data Zone Standard **US**, nicht EU. Allgemeine Angaben zu `DataZoneStandard` in den Voraussetzungen reichen nicht. Quelle: [Priority Processing](https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/priority-processing).

### G. Ein kleiner deterministischer Antwortpfad — größerer Produktumbau

Für eng definierte Fälle wie die explizite Frage nach der KI-Natur kann eine inhaltlich vollständige, vorproduzierte Antwort LLM und TTS umgehen. Das wäre mehr als ein gecachtes „Hm“. Der Pfad muss Gesprächszustand und Transkript korrekt fortführen; frei formulierte Einwände gehören weiter ins LLM. Ein breit nutzbarer Pfad erfordert eine Zustandsmaschine und verändert das Rollenspiel.

Ein TTS-Cache für **erst vom LLM ausgewählte** Sätze spart nur Synthesezeit; er entfernt nicht das Warten aufs LLM. Wie häufig passende vollständige Antworten vorkommen, entscheidet über einen Einfluss auf das Gesamt-p90. Grundlage für die allgemeine Idee: [OpenAI Latenzoptimierung](https://developers.openai.com/api/docs/guides/latency-optimization).

## 5. Was ich aktuell nicht priorisieren würde

| Ansatz | Grund |
|---|---|
| Azure TextStream erneut unverändert integrieren | §25 misst späteren Hörbeginn; außerdem unterstützt TextStream kein SSML, sodass die bisherigen Randstille-Tags nicht unverändert übertragen werden können. [Microsoft](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/how-to-lower-speech-synthesis-latency) |
| TOKEN-Modus am bestehenden Azure-SSML-Service | Er erzeugt einzelne Syntheseaufträge; er ist kein Umbau zu kontinuierlichem Texteingang. |
| Größerer/neuerer LLM-Wechsel | Vorhandene Kurzmessungen liefern keine Verbesserung; `nano` verfehlt Rollenkriterien. |
| Mehr Smart-Turn-CPU-Threads | Bereits ohne relevanten Gewinn getestet. Unter Last separat dimensionieren. |
| Globale Pausenschwelle weiter senken | Kollision mit nachgewiesenen Turn- und Hörersignalproblemen. |
| Python-Pipeline neu schreiben | Beispielhafte Ausgabeübergabe kostet nur etwa 8 ms; Remote-Dienste und Satzaggregation dominieren. |
| LiveKit „Zero Jitter Buffer“ für Audio | Die aktuelle dokumentierte Option betrifft Video; Audio bleibt unbeeinflusst. [LiveKit](https://docs.livekit.io/robotics/media/performance/low-latency/) |

Self-hosting bleibt eine größere Alternative: Es schafft Kontrolle über Standort und Serving, verlangt aber zusätzliche Modelle, GPU-Betrieb und deutsche Qualitätsabnahme. Es ist kein kleiner Schalter am Azure-Stack. Ohne konkreten gemessenen Kandidaten lässt sich daraus keine verlässliche Latenzprognose ableiten.

## 6. Konkreter nächster Versuchsplan

1. **Messgrundlage festlegen.** Einheitliche Fixtures, Persona, Modell, Inhaltsfilter, vollständiger Quellstand und Versionen. STT-/TTS-Schwellen und Provider-Endpunkte ohne Secrets ins Manifest aufnehmen. Warm-up separat ausweisen. Kandidaten, Abbruchgründe und erwartete Gesprächsenden vollständig bilanzieren.
2. **TTS zuerst isolieren.** Azure als Kontrolle; Aura-2 Fabian/Julius über den EU-Endpunkt als Kandidaten. Mindestens 30 verschiedene deutsche Texte mit Zahlen, Firmen-/Personennamen, Fragen und Negationen, mehrere gegenbalancierte Durchgänge. Gleiche PCM-Rate, gleiche vollständige Texte, gleiches Warm-up. Erst danach ganze Gespräche und andere Chunk-Grenzen testen.
3. **Hörlatenz messen.** Anfrage → erstes Paket, erstes nichtstilles PCM und erstes tatsächlich ausgegebenes PCM getrennt erfassen. Satzaggregation separat protokollieren. Als vorgeschlagene Experimenthürde mindestens 100 ms Verbesserung beim TTS-Hörbeginn-p90 sowie keine Verschlechterung bei Aussprache und Unterbrechung festlegen; das ist eine neue Empfehlung, keine bestehende Abnahmegrenze.
4. **Gewinner in echte Gespräche übernehmen.** T1 sowie Kurzantworten, Denkpausen, Zahlenkorrekturen und „Mhm“ abspielen. E2E nach dem tatsächlichen vollständigen Sprechende, vorzeitige Ausgabe, verlorene Information und Verstummen bewerten. Die Stimmen zusätzlich blind anhören.
5. **Erst danach Spekulation variieren.** Stabilitätsfilter oder Flux EagerEOT, jeweils isoliert. Aufrufe, Tokens und verworfenes TTS erfassen. Keine Freigabe allein aufgrund von Textähnlichkeit. Einen eigenen Test auf verspätetes Audio und unbestätigte Werkzeugausführung vorsehen.
6. **Browser und Last prüfen.** WebRTC ist in `main.py` noch nicht implementiert. Bis dahin sind Servermetriken kein Browser-Hörnachweis. Nach Verdrahtung tatsächliche Audioausgabe und Puffer messen; anschließend 1/5/10 gleichzeitige Gespräche mit Fehlerquote und E2E-p90 vergleichen. PTU oder Standortwechsel erst anhand dieser Diagnose entscheiden.

Für jeden Schritt einen Gewinner nur bei gemeinsam erfüllten Qualitäts- und Latenzkriterien bestimmen. Das Hauptsatz-Timing des Ledgers meint das erste Wort nach einem Satzende, nicht automatisch den ersten relevanten Inhalt; bei Chunk- oder Sprachänderungen diese Hilfsmetrik nicht als Inhaltsnachweis benutzen.

**Einschätzung:** Ein anderer TTS-Pfad ist der stärkste noch offene, überschaubare Versuch. Ein dauerhaftes p90 unter 900 ms dürfte zusätzliche Überlappung und verlässliches Turn-Taking benötigen. Die Recherche rechtfertigt gezielte Experimente, aber weder die Aussage „alle Möglichkeiten ausgeschöpft“ noch eine Zusage, das Ziel durch Addition kleiner Gewinne zu erreichen.
