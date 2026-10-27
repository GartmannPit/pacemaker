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
| Lasttest bestanden für **20 Nutzer** beim ersten Kunden (Pit, 2026-10-27) | Claude/Codex | läuft (bisher bis 10 geplant) |

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

**Richtung (Pit, 2026-10-27): Hybrid.** Anforderungen:

- Keine Manipulation durch den Nutzer: Transkript, Werkzeugaufrufe, Gesprächsende und
  Scoring-Grundlage entstehen serverseitig; der Browser liefert nur Audio.
- Die Vorteile von B behalten (Persona-Logik und Zeitlimits serverseitig, Messkette),
  die Nachteile von A vermeiden.
- Einschränkung: Ein Rückfall auf die Azure-Kaskade ist im Hybrid nur möglich, wenn der
  B-Pfad (LiveKit + Pipecat) als zweiter Weg weiter gepflegt wird. Ob das nötig ist,
  **[offen]**.
- Bietet `gpt-live-1` keine serverseitige Zusatzverbindung, ist B die Lösung, die diese
  Anforderungen erfüllt.

**Versuch (Schritt 1), zeitlich begrenzt:**

1. Offizielle Doku `gpt-live-1` prüfen: serverseitige Verbindung zu einer WebRTC-Sitzung,
   Transkript- und Werkzeug-Ereignisse, Sitzungsende durch den Server.
2. Falls vorhanden: Prototyp auf Basis von `agent/tools/gptlive_browser` mit serverseitigem
   Transkript und `auflegen`.
3. Latenz A vs. B auf gleicher Basis messen (präregistriert, abwechselnd A/B, Browser-Messpunkt).
4. Entscheidung durch die Gründer; Ergebnis hier eintragen.

## 4. Scoring (einfach) und Schlüsselmomente

Nur Gesprächsinhalt und -struktur aus dem Transkript, keine Auswertung von Stimme oder
Prosodie (CLAUDE.md).

**Schlüsselmomente (Idee Pit, 2026-10-27):** Nach dem Gespräch zieht ein eigenes Modell
(„Sub-Agent“) aus dem **Transkript** die Stellen heraus, an denen sich das Gespräch
entschieden hat (z. B. der Satz, der den Pitch getragen oder gekippt hat), mit kurzer
Begründung. Grundlage ist ausschließlich Text, kein Audio. Gespeichert werden nur diese
Ausschnitte und die Auswertung, nicht das Gesprächsaudio (§5). Ziel: später Muster über
viele Gespräche erkennen. Modell, Anbieter und EU-Verarbeitung **[offen]**. Kriterien je Szenario aus dem Strategiepapier ableiten **[offen]**.
Die Judge-Werkzeuge aus Phase 0 (`tests/judge.py`, `metrics/conversation.py`) sind ein
möglicher Ausgangspunkt. Voraussetzung: Das Transkript ist nicht vom Nutzer manipulierbar (§3).

## 5. Login und Löschkonzept

- Self-Service-Login für Pilotkunden; Anbieter und Datenhaltung in der EU **[offen]**.
- **Datensparsamkeit (Pit, 2026-10-27): so wenig wie möglich speichern.**
  - **Kein Rohaudio.** Weder Nutzer- noch Persona-Audio wird gespeichert.
  - Vollständiges Transkript nur so lange wie für Anzeige und Auswertung nötig; Frist **[offen]**.
  - Länger aufbewahrt: Schlüsselmomente (§4) und Scoring-Ergebnis; Frist **[offen]**.
  - Löschung automatisch (Aufbewahrungsfristen), nicht manuell.
- Persistenz über Flatfiles hinaus wird damit nötig; Auswahl **[offen]**.

## 6. Offene Entscheidungen (Gründer)

Entschieden (Pit, 2026-10-27): Richtung Hybrid (§3), erster Kunde mit 20 Nutzern (§1),
kein Rohaudio, möglichst wenig speichern, Schlüsselmomente aus dem Transkript (§4, §5).

Offen:

1. Hybrid oder B, nach dem Versuch (§3); Kaskaden-Rückfall weiter pflegen?
2. Neue Latenz-Zielwerte für Phase 1, falls gewünscht
3. Wie viele der 20 Nutzer gleichzeitig sprechen sollen (z. B. Teamtraining) → Laststufe
4. Scoring-Kriterien je Szenario
5. Login-Anbieter und Datenhaltung
6. Aufbewahrungsfristen für Transkript, Schlüsselmomente, Scoring
