# Dokumentierte Referenzen für Sprachagenten mit niedriger Latenz

**Recherchestand:** 14. Oktober 2026. Primärquellen: Herstellerdokumentation und Quellrepositories. Keine Referenz wurde hier neu betrieben oder nachgemessen.

## Ergebnis

Es gibt dokumentierte vollständige Sprachagenten, Framework-Funktionen und Betriebskonzepte für niedrige Antwortlatenz. Die bisherigen Pacemaker-Messungen sind kein Beleg, dass diese Aufgabenstellung grundsätzlich ungelöst wäre. Die Recherche muss neben einzelnen Providerwechseln auch vollständige Referenzpipelines einbeziehen.

Am nächsten am bestehenden Projekt liegen **Azure Voice Live mit dem bisherigen Persona-Modell** und **LiveKit Agents mit direkt konfigurierten Azure-Diensten**. Eine vollständige, dokumentierte GPU-Alternative bietet NVIDIA auf Basis von Pipecat. Deepgram Flux dokumentiert einen eigenen frühen Generierungsstart, den der bisherige reine STT-Vergleich nicht vollständig abdeckt.

## 1. Azure Voice Live — bisher fehlender verwalteter Vergleichspfad

Microsoft integriert Spracherkennung, LLM, TTS und Gesprächssteuerung hinter einer API. Zu den unterstützten Konfigurationen zählt `gpt-4.1-mini` mit Azure STT/TTS. Das erlaubt einen Vergleich mit demselben grundlegenden Persona-Modell, während Microsoft die Orchestrierung übernimmt. Quelle: [Voice Live Überblick](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/voice-live).

Die Anleitung dokumentiert semantische Turn-Erkennung inklusive `azure_semantic_vad_multilingual` mit Deutsch sowie konfigurierbare Unterbrechungen und Füllwortbehandlung. Das adressiert sowohl Antwortbeginn als auch unerwünschte Unterbrechungen. Quelle: [Voice Live Anleitung](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/voice-live-how-to).

**Unterschied zum bisherigen Projektversuch:** `s2s` in Pacemaker verwendet Azure OpenAI Realtime mit lokalem Turn-Ende und abgeschalteter serverseitiger Turn-Erkennung. Das ist kein Versuch dieser verwalteten Voice-Live-Konfiguration mit `gpt-4.1-mini`. Der ungünstige Realtime-p90 verwirft sie daher nicht automatisch.

**EU-Abgrenzung:** Microsoft dokumentiert für Voice Live unterschiedliche Verarbeitungsbereiche für LLM, Spracherkennung und HD-Stimmen. Germany West Central führt unter anderem Data-Zone-Verarbeitung auf. Ein EU-Ressourcenstandort allein genügt nicht zur Freigabe jeder Modell-/Stimmenkombination. Die konkrete Konfiguration muss anhand beider Tabellen und der Projektvorgabe gewählt werden. Quelle: [Voice Live Regionen und Verarbeitungsbereiche](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/regions?tabs=voice-live).

**Evidenzgrenze:** Die geprüften Seiten garantieren für Pacemaker keinen E2E-p90 unter 900 ms. Voice Live ist ein konkreter, dokumentierter Vergleichskandidat, kein bereits bewiesener Gewinner. Auch die bestehende offene Einordnung audiobasierter Turn-Erkennung gegenüber dem projektinternen Prosodie-Verbot bleibt erforderlich.

## 2. LiveKit Agents — vorgezogene Generierung als Framework-Funktion

LiveKit dokumentiert `preemptive_generation`: Antwortberechnung beginnt vor der endgültigen Bestätigung der Sprechergrenze. `preemptive_tts` erweitert dies auf die Synthese. Die Dokumentation behandelt Abbruch bei geändertem Kontext, begrenzte Wiederholungen und zusätzlichen Verbrauch verworfener Entwürfe. Quelle: [Sprachausgabe und vorgezogene Generierung](https://docs.livekit.io/agents/multimodality/audio/).

Die Einstellungen für Sprechergrenzen und Unterbrechungen werden gemeinsam dokumentiert. Dazu gehören dynamische Wartefristen und die Unterscheidung kurzer Hörersignale von echten Unterbrechungen. Die Dokumentation weist selbst darauf hin, dass vorgezogene Berechnung nicht in jeder Situation Latenz spart. Quelle: [Turn-Taking-Tuning](https://docs.livekit.io/agents/logic/turns/tuning/).

Es gibt ein vollständiges [Python-Starterprojekt](https://github.com/livekit-examples/agent-starter-python), dokumentierte [Azure-Integrationen](https://docs.livekit.io/agents/integrations/azure/) und [Self-Hosting für Server und Agents](https://docs.livekit.io/transport/self-hosting/).

**Einordnung für Pacemaker:** Pipecat plus LiveKit als geplantem Transport und LiveKit Agents als Pipeline-Framework sind unterschiedliche Aufbauten. Der zweite wurde im Projekt bisher nicht als vollständige Referenz vermessen. Zugleich ist die Grundidee der Spekulation in Pacemaker bereits vorhanden; sie wird durch einen Frameworkwechsel nicht zu einem neuen physikalischen Hebel. Ein Vergleich kann zeigen, ob Scheduling, Finalisierung und Abbruch im Framework besser zusammenarbeiten.

**Sinnvoller Vergleich:** Ein kleiner LiveKit-Agent mit derselben Persona, denselben Azure-Modellen, direkt festgelegten EU-Endpunkten und denselben Testclips. Zuerst Frameworkeffekt isolieren. Erst anschließend Provider oder Turn-Modelle wechseln. Den Starter nicht unverändert mit seinen Cloud-/Modelldefaults als EU-Produktpfad übernehmen.

## 3. NVIDIA Nemotron Voice Agent — vollständiger Pipecat-Aufbau mit Benchmark

NVIDIA veröffentlicht einen [vollständigen Voice-Agent-Blueprint](https://github.com/NVIDIA-AI-Blueprints/nemotron-voice-agent) mit ASR, LLM, TTS, Unterbrechungssteuerung, Browseranwendung und Deployment-Rezepten.

Die [Performance-Dokumentation](https://github.com/NVIDIA-AI-Blueprints/nemotron-voice-agent/blob/main/docs/04-evaluation-and-performance.md) nennt **0,86–0,93 Sekunden Server-E2E-Latenz** über 1–64 parallele Streams. Der Referenzaufbau nutzt **vier B200-GPUs**, englische Streaming-ASR, Magpie-TTS und ein Nemotron-LLM. Die Tabelle weist diese Werte nicht als Pacemaker-kompatibles p90 aus.

**Einordnung:** Das ist eine konkrete technische Referenz für eine komplette Kaskade mit niedriger Latenz. Sie beweist weder dieselbe Leistung auf einer kleinen CPU-VM noch auf Deutsch oder mit der Pacemaker-Persona. Selbstbetrieb ermöglicht die Kontrolle des Standorts; die Modelllizenzen, ausgehenden Dienste und Betriebskosten müssen für einen tatsächlichen EU-Aufbau gesondert beurteilt werden.

Ein weiteres [Pipecat-Referenzprojekt](https://github.com/pipecat-ai/nemotron-january-2026/blob/main/docs/streaming-pipeline-architecture.md) dokumentiert konkrete Eingriffe: korrekte Reihenfolge von finalem Transkript und Turn-Ende, um einen Aggregations-Timeout zu vermeiden; begrenzte erste Textsegmente; Wiederverwendung des LLM-KV-Caches; unterschiedliche TTS-Verarbeitung für ersten und weitere Abschnitte. Seine Zeitdefinition basiert auf VAD-Ereignissen und ist ebenfalls vor einem Zahlenvergleich abzugleichen.

Diese Mechanismen sind prüfbare Referenzen. Sie sind keine Belege, dass derselbe Timeout oder derselbe Cache-Vorteil aktuell in Pacemaker vorliegt.

## 4. Deepgram Flux Eager EOT — Anbieterereignis statt selbst gewählter Frühpause

Deepgram dokumentiert den vollständigen Ablauf: `EagerEndOfTurn` startet einen Entwurf; `TurnResumed` verwirft ihn; `EndOfTurn` bestätigt die Ausgabe. Dazu existieren Codebeispiele. Quelle: [Eager EOT](https://developers.deepgram.com/docs/flux/voice-agent-eager-eot).

**Einordnung:** Der getestete Flux-STT-Wechsel allein deckt diesen Ablauf nicht ab. Im früher geprüften Projektadapter war `eager_eot_threshold` nicht konfiguriert. Pacemakers eigene Spekulation wird von einer zweiten schnellen VAD und nachgereichten Transkripten ausgelöst. Ein Anbieterereignis könnte einen anderen Startzeitpunkt und eine andere Stabilität liefern; das ist zu messen. Ein allgemeiner Beweis höherer Geschwindigkeit folgt daraus nicht.

Die Hersteller-[Agentenanleitung](https://developers.deepgram.com/docs/flux/agent) enthält außerdem eine vollständige Pipeline mit dokumentierter Ausrichtung auf Antworten unter einer Sekunde. Das Beispiel verwendet Englisch und andere Komponenten; es ist kein deutscher EU-p90-Nachweis.

## 5. Weitere dokumentierte Wege und ihre Grenzen

**Gradium:** Dokumentierte deutsche STT-/TTS-Integration, etwa über [LiveKit TTS](https://docs.livekit.io/agents/models/tts/gradium/). Die [Residency-Anleitung](https://docs.gradium.ai/guides/data-residency) verlangt eine aktivierte Residency-Einstellung für garantierte EU-Verarbeitung; der EU-Hostname allein reicht nicht. AVV-Verfügbarkeit ist dort über den Support genannt. Ein veröffentlichter [TTS-Benchmark](https://gradium.ai/blog/time-to-first-audio) meldet 258 ms p50 und 274 ms p95, mit eigener Definition und eigenen Testbedingungen. Das rechtfertigt keine Annahme, dass Gradium die aktuelle Azure-TTS sicher beschleunigt. Interessant ist die komplette Streaming-Integration, nicht eine ungeprüfte niedrige Werbezahl.

**Kyutai Unmute:** Ein [vollständiges offenes System](https://github.com/kyutai-labs/unmute), das Text-LLMs Sprachfähigkeiten gibt. Die [STT-Dokumentation](https://kyutai.org/stt/) beschreibt die beschleunigte Finalisierung ausstehender Audiokontexte nach Sprachende. Der Mechanismus setzt Kontrolle über den STT-Server voraus und lässt sich nicht einfach als Azure-API-Schalter übernehmen. Die dort beschriebenen STT-Modelle sind englisch bzw. englisch-französisch; daraus folgt keine direkte deutsche Alternative.

**OpenAI:** Die [offizielle Voice-Agent-Dokumentation](https://developers.openai.com/api/docs/guides/voice-agents) unterscheidet kontinuierliche Sprachsysteme, Realtime-Sitzungen und kontrollierbare STT→LLM→TTS-Kaskaden. Sie empfiehlt, tatsächlich nützliche gesprochene Antworten getrennt von Bestätigungsfloskeln zu messen. Das ist eine Architektur- und Evaluationsreferenz; EU-Verfügbarkeit und der bereits im Projekt getestete Realtime-Pfad dürfen nicht pauschal gleichgesetzt werden.

## Konkrete Folgerung für Pacemaker

Ein sinnvoller nächster Vergleich ist ein **dokumentierter Referenzagent mit möglichst gleichen Bedingungen**:

1. Azure Voice Live mit `gpt-4.1-mini`, deutscher Ausgabe und einer zuvor eingegrenzten EU-Konfiguration. Gleiche Persona und dieselben Aufgaben wie bisher. Prüft einen verwalteten Gesamtpfad.
2. LiveKit Agents selbst betrieben, zunächst mit denselben Azure-Diensten und Einstellungen. Prüft den Frameworkpfad, ohne zugleich Modellqualität zu verändern.
3. NVIDIA als gesonderte Alternative, wenn eigener GPU-Betrieb in Betracht kommt. Nicht denselben Ressourcenbedarf wie die heutige VM unterstellen.

Je Vergleich zuerst Quellstand, Modelle, Region, Outputformat und Antwortdefinition festhalten. Dasselbe Ende der vollständigen Nutzeräußerung und erstes nichtstilles ausgegebenes Audio verwenden; Werkzeugabschiede einbeziehen. Neben p50/p90 Antwortausfälle, Denkpausen, Kurzantworten und Korrekturen bewerten.

Die zusätzlichen Referenzen ändern den Befund „Phase 0 nach dem bisherigen Plan nicht bestanden“ nicht. Sie ändern die Aussage über verbleibende Möglichkeiten: Es fehlen konkrete vollständige Vergleichspfade. Vor ihrer Prüfung ist „vertretbare Latenz mit EU-Diensten technisch nicht erreichbar“ keine gerechtfertigte Schlussfolgerung.
