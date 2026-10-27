# Phase 1 — MVP für Pilotkunden (Entwurf)

**Stand:** 2026-10-27 · **Verfasser:** Claude · **Status:** ENTWURF zur Freigabe durch die
Gründer; nichts davon ist umgesetzt. Offene Entscheidungen sind mit **[offen]** markiert.
**Bezug:** [Strategiepapier](../Pacemaker.md) §5 (Phase 1) ·
[Phase-0-Ergebnisse](./phase-0-ergebnisse.md) §8 · [Personas-Entwurf](./phase-1-personas-entwurf.md) ·
[Lasttest](./phase-1-lasttest.md)

## 0. Ziel und Abgrenzung

Laut Strategiepapier: alle vier Szenarien, Standard-Personas, Transkript und einfaches Scoring,
Self-Service-Login, Löschkonzept technisch umgesetzt, ein AVV-fähiger Anbieter-Stack festgezurrt.
Ziel ist ein Stand, mit dem Pilotkunden selbstständig üben können.

**Nicht in Phase 1** (Strategiepapier Phase 2/3): Manager-Dashboard, konfigurierbare Personas,
Mandantentrennung über das Nötigste hinaus, CRM-/LMS-Anbindung, SLA.

**Gesetzt aus Phase 0:** Sprachpfad GPT-Live (`gpt-live-1`), Kaskade als Rückfall; Latenz
akzeptiert; Web-only; keine Emotionserkennung, Scoring nur nach Inhalt und Struktur;
KI-Natur jederzeit erkennbar.

## 1. Voraussetzung für den Pilotstart (nicht für die Entwicklung)

| Voraussetzung | Wer | Stand |
|---|---|---|
| EU-Freigabe des OpenAI-Projekts (`eu.api.openai.com`) | Pit / OpenAI | beantragt |
| OpenAI-DPA geprüft und abgeschlossen | Pit | [offen] |
| Hetzner-AVV (falls Architektur B oder Hybrid, §3) | Pit | [offen] |
| Lasttest bestanden (Stufe passend zur Pilotgröße) | Claude/Codex | läuft |

Bis dahin: nur synthetische Daten und Pits eigene Stimme, Region `referenz` (CLAUDE.md).

## 2. Reihenfolge

| Schritt | Inhalt | Ergebnis |
|---|---|---|
| 0 | Lasttest gleichzeitiger Gespräche (Prio 0) | trägt / trägt nicht, Token-Verbrauch je Gespräch |
| 1 | Architekturversuch Browser-Anbindung (§3) | Entscheidung A / B / Hybrid |
| 2 | `web/`: Verbinden, Sprechen, Hören, Transkript, KI-Hinweis | erstes Gespräch im Browser über die gewählte Architektur |
| 3 | Persona-Gerüst und Markus Brandt überarbeitet ([Entwurf](./phase-1-personas-entwurf.md)) | Persona mit Gesprächslogik |
| 4 | Übrige drei Personas / Szenarien | vier Szenarien |
| 5 | Transkript speichern, einfaches Scoring (§4) | Auswertung nach dem Gespräch |
| 6 | Login, Löschkonzept (§5) | Pilotkunden können sich selbst anmelden; Daten werden automatisch gelöscht |
| 7 | Pilot-Vorbereitung: EU-Endpunkt umstellen, Messlauf mit `eu`, README | Pilotstart nach §1 |

Schritt 1 entscheidet über Aufbau von 2–5 und kommt deshalb vor jedem Frontend-Code.

## 3. Architekturentscheidung: Wie kommt der Browser an GPT-Live?

| | A: Browser direkt zu OpenAI (WebRTC) | B: Browser → LiveKit → Pipecat-Agent → OpenAI |
|---|---|---|
| Latenz | ~250–300 ms schneller (kleine Stichprobe, Summary §28) | zusätzlicher Zwischenschritt |
| Transkript fürs Scoring | kommt im Browser an; vom Nutzer manipulierbar | entsteht serverseitig |
| Persona-Logik (Personas-Entwurf §4) | im Browser oder über Zusatzverbindung | im Agent |
| Gesprächsende, Zeitlimits | hängen am Browser | serverseitig erzwungen |
| Rückfall Azure-Kaskade | nicht möglich | per Konfiguration |
| Messkette aus Phase 0 | entfällt, im Browser neu bauen | bleibt |
| Betrieb | kein LiveKit, keine Agent-Prozesse | LiveKit, CPU je Gespräch (Lasttest) |
| Datenfluss | Browser → OpenAI | Browser → Hetzner → OpenAI |

**Hybrid:** Audio direkt wie A, unser Server verbindet sich zusätzlich mit derselben Sitzung
und erhält Transkript und Werkzeugaufrufe serverseitig. Ob `gpt-live-1` eine solche
serverseitige Zusatzverbindung anbietet, ist **[offen]**.

**Versuch (Schritt 1), zeitlich begrenzt:**

1. Offizielle Doku `gpt-live-1` prüfen: serverseitige Verbindung zu einer WebRTC-Sitzung,
   Transkript- und Werkzeug-Ereignisse, Sitzungsende durch den Server.
2. Falls vorhanden: Prototyp auf Basis von `agent/tools/gptlive_browser` mit serverseitigem
   Transkript und `auflegen`.
3. Latenz A vs. B auf gleicher Basis messen (präregistriert, abwechselnd A/B, Browser-Messpunkt).
4. Entscheidung durch die Gründer; Ergebnis hier eintragen.

## 4. Scoring (einfach)

Nur Gesprächsinhalt und -struktur aus dem Transkript, keine Auswertung von Stimme oder
Prosodie (CLAUDE.md). Kriterien je Szenario aus dem Strategiepapier ableiten **[offen]**.
Die Judge-Werkzeuge aus Phase 0 (`tests/judge.py`, `metrics/conversation.py`) sind ein
möglicher Ausgangspunkt. Voraussetzung: Das Transkript ist nicht vom Nutzer manipulierbar (§3).

## 5. Login und Löschkonzept

- Self-Service-Login für Pilotkunden; Anbieter und Datenhaltung in der EU **[offen]**.
- Löschkonzept technisch: automatische Aufbewahrungsfristen für Transkripte und Auswertungen
  (Strategiepapier: Rohaudio nach X Tagen, Transkript nach Y Monaten). Ob überhaupt Rohaudio
  gespeichert wird, ist **[offen]**; ohne Speicherung entfällt die Frist.
- Persistenz über Flatfiles hinaus wird damit nötig; Auswahl **[offen]**.

## 6. Offene Entscheidungen (Gründer)

1. Architektur A / B / Hybrid (nach Versuch, §3)
2. Neue Latenz-Zielwerte für Phase 1, falls gewünscht
3. Pilotgröße (Anzahl gleichzeitiger Nutzer) als Maßstab für den Lasttest
4. Scoring-Kriterien je Szenario
5. Login-Anbieter und Datenhaltung
6. Rohaudio speichern ja/nein, Aufbewahrungsfristen
7. Umgang mit den Aufnahmen der Robustheitsprobe (löschen oder Einwilligung verlängern)
