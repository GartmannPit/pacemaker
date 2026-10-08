# Phase 0 — EU-Compliance-Faktenblatt (Entwurf)

**Stand:** 2026-10-08 · **Status:** Entwurf von Claude, **Prüfung der AVVs durch Pit offen**
**Bezug:** Muss-Kriterium „EU-Compliance dokumentiert" ([Phase-0-Plan](./phase-0-proof-of-concept.md) §2)

> Keine Rechtsberatung. Angaben stammen aus Herstellerdokumentation und eigenen Messungen;
> Stellen mit „prüfen" sind nicht abschließend belegt.

## 1. Empfohlener Stack und Datenfluss

Stack `azure-eu` (Kaskade), gemessen von der EU-Mess-VM:

```
Browser/Mikrofon ──► Agent (Hetzner, DE) ──► Azure AI Speech STT (Germany West Central)
                                        ├──► Azure OpenAI (Ressource Sweden Central, Data Zone EU)
                                        └──► Azure AI Speech TTS (Germany West Central)
```

Verarbeitet werden Sprachaudio des Nutzers, Transkripte, Persona-Antworten (Text und Audio),
Zeitstempel. Keine Emotions- oder Prosodieanalyse (`CLAUDE.md`).

## 2. Je Subdienstleister

| Dienst | Zweck | Region / Verarbeitungsort | Beleg | AVV/DPA | US-Mutter (CLOUD Act) |
|---|---|---|---|---|---|
| **Azure AI Speech** (STT, TTS) | Spracherkennung, Sprachausgabe | Germany West Central (Frankfurt) | Endpoint löst auf `…germanywestcentral.cloudapp.azure.com` auf (DNS, 2026-10-07) | Microsoft Products and Services DPA, Teil der Vertragsbedingungen — **prüfen**, dass er für die Subscription gilt | **ja** (Microsoft Corp.) |
| **Azure OpenAI** (`gpt-4.1-nano`, `gpt-4.1-mini`) | Persona-Antworten | Ressource **Sweden Central**; Deployments **Data Zone Standard (EU)**: Verarbeitung innerhalb der EU-Datenzone | DNS: `…swedencentral.cloudapp.azure.com`; Deployment-Typ im Portal (Pit, 2026-10-03) | wie oben — **prüfen** | **ja** (Microsoft Corp.) |
| **Hetzner Cloud** | Agent-Server (Mess-VM, später Produktivserver) | Deutschland (Nürnberg/Falkenstein) | Serverstandort im Hetzner-Projekt | AVV im Kundenkonto abschließbar — **prüfen/abschließen** | nein (Hetzner Online GmbH, DE) |
| Pipecat, LiveKit | Pipeline, WebRTC | selbst betrieben auf Hetzner | Open Source, kein externer Dienst | entfällt | entfällt |

**Nicht im Produktpfad (nur Referenzmessung, synthetische Clips):** Stack A (Deepgram,
OpenAI direkt, ElevenLabs — USA), `gpt-realtime-2.1` (Rohaudio-Frage offen, siehe §4).

## 3. Besonderheiten Azure OpenAI

- **Data Zone Standard (EU):** Laut Microsoft finden Verarbeitung und eine etwaige menschliche
  Prüfung innerhalb der EU/des EWR statt. **Global Standard ist ausgeschlossen** (Verarbeitung
  ggf. außerhalb der EU) — am 2026-10-03 versehentlich für einen Messlauf genutzt und verworfen.
- **Missbrauchsüberwachung:** Prompts und Antworten können bis zu **30 Tage** in einem
  ressourcenbezogenen Speicher in der Region der Ressource (hier Schweden) vorgehalten und bei
  Verdacht von Microsoft-Mitarbeitenden im EWR geprüft werden. Eine Abschaltung („modified abuse
  monitoring") erfordert einen Antrag bei Microsoft. **Für Trainingsgespräche mit
  Personenbezug bewerten.**
- **Inhaltsfilter „Asynchronous Filter":** Für die Latenz aktiv (`Asynchronus_Filtering`).
  Text wird vor Abschluss der Filterprüfung ausgeliefert; das Filtersignal kommt verzögert.
  Abbruch der Audioausgabe bei Filtersignal ist Pflicht vor dem Produktpfad
  ([Plan](./2026-10-07-pruefung-kritik-naechste-schritte.md) §4 B).

## 4. Offene Punkte

| # | Punkt | Wer |
|---|---|---|
| 1 | Microsoft-DPA für die Subscription bestätigen (Vertragsbedingungen im Azure-Portal) | Pit |
| 2 | Hetzner-AVV im Kundenkonto abschließen | Pit |
| 3 | Ist Azure AI Speech vom **EU Data Boundary** erfasst? **Recherche 2026-10-08:** Weder Azure AI Speech noch Azure OpenAI stehen auf der Microsoft-Liste der vom EU Data Boundary ausgenommenen Dienste (Stand der Seite 2026-04-13; dort ausgenommen u. a. Azure Front Door/CDN und Sicherheitsdienste). Microsoft nennt die Product Terms als maßgebliche Quelle — **Bestätigung dort ausstehend** | Pit bestätigt in den Product Terms |
| 4 | Missbrauchsüberwachung (30 Tage) für personenbezogene Trainingsgespräche bewerten; ggf. Antrag auf modifizierte Überwachung | Pit |
| 5 | Ressource von Sweden Central nach Germany West Central? Compliance-neutral (beides EU), Latenz-Hebel ~20–25 ms je Anfrage (RTT von der VM 28 vs. ~5 ms) | Entscheidung nach Schritt D |
| 6 | Realtime-Modell: Verarbeitung von Rohaudio gegen „keine Prosodieanalyse" abwägen | vor jedem Produkteinsatz |
| 8 | **Smart Turn** (Turn-Ende-Erkennung) wertet laut Hersteller Prosodie/Intonation aus — Konflikt mit dem Wortlaut von `CLAUDE.md`; Einordnung und Optionen: [`2026-10-08-einordnung-smart-turn-prosodie.md`](./2026-10-08-einordnung-smart-turn-prosodie.md) | Pit entscheidet |
| 7 | Löschkonzept für Audio, Transkripte, Messdaten (`experiments/runs/` auf VM und lokal) | Phase 1 |

## 5. Latenzunterschied EU-Stack gegenüber US-Referenz

Beobachteter Unterschied zweier ganzer Stacks, **kein isolierter Effekt der Datenresidenz**
(STT, TTS, Routing und Einstellungen unterscheiden sich zugleich):

| Stack | E2E p90 | Bedingungen |
|---|--:|---|
| US-Referenz (Stack A) | 1501 ms | 2026-10-04, Laptop, nicht optimiert |
| `azure-eu`, `gpt-4.1-nano`, optimiert | 1014–1206 ms | 2026-10-07, EU-Mess-VM, 3 Läufe |

Der optimierte EU-Stack ist schneller als die (nicht optimierte) US-Referenz. Ein fairer
Vergleich bräuchte beide optimiert und von der VM gemessen.

## Quellen

- Microsoft Learn: [Data Zone / Deployment-Typen](https://learn.microsoft.com/azure/ai-services/openai/how-to/deployment-types),
  [Content Streaming / Asynchronous Filter](https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/content-streaming),
  [EU Data Boundary](https://learn.microsoft.com/privacy/eudb/eu-data-boundary-learn),
  [vom EU Data Boundary ausgenommene Dienste](https://learn.microsoft.com/et-ee/privacy/eudb/eu-data-boundary-excluded-services)
- [Vom EU Data Boundary ausgenommene Dienste (englisch, Stand 2026-04-13)](https://learn.microsoft.com/en-us/privacy/eudb/eu-data-boundary-excluded-services)
- Microsoft Q&A zur Missbrauchsüberwachung: [Abuse Monitoring and data storage](https://learn.microsoft.com/en-us/answers/questions/5780766/question-regarding-azure-direct-models-abuse-monit)
- Eigene Messungen: DNS-Auflösung und RTT (`infra/rtt-check.sh`), 2026-10-07
