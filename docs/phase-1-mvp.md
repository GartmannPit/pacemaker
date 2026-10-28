# Phase 1 — MVP für Pilotkunden (OneTry, vormals Pacemaker)

**Stand:** 2026-10-27 · **Verfasser:** Claude, geprüft von Codex · **Status:** **FREIGEGEBEN**
(Pit, 2026-10-27) mit den Entscheidungen in §6; Umsetzung beginnt mit Schritt 1. Offene Punkte
sind mit **[offen]** markiert.
**Bezug:** [Strategiepapier](../Pacemaker.md) §5 · [Phase-0-Ergebnisse](./phase-0-ergebnisse.md) §8 ·
[Architekturversuch Hybrid](./phase-1-architekturversuch-hybrid.md) ·
[Lasttest](./phase-1-lasttest.md) · [Personas-Entwurf](./phase-1-personas-entwurf.md)

## 0. Ziel und Abgrenzung

Laut Strategiepapier: alle vier Szenarien, Standard-Personas, Transkript und einfaches Scoring,
Self-Service-Login, Löschkonzept technisch umgesetzt, ein AVV-fähiger Anbieter-Stack festgezurrt.
Ziel ist ein Stand, mit dem Pilotkunden selbstständig üben können.

**Nicht in Phase 1** (Strategiepapier Phase 2/3): Manager-Dashboard, konfigurierbare Personas,
CRM-/LMS-Anbindung, SLA, Mandantentrennung über die Mindestanforderung in §5 hinaus.

**Gesetzt (Gründerentscheidungen bis 2026-10-27):** Sprachpfad GPT-Live (`gpt-live-1`), kein
Kaskaden-Rückfall; gemessene Latenz akzeptiert; Architektur **Hybrid** (§3); erster Kunde mit
20 Nutzern; kein Rohaudio, so wenig wie möglich speichern; Schlüsselmomente aus dem Transkript;
Web-only; keine Emotionserkennung, Scoring nur nach Inhalt und Struktur; KI-Natur jederzeit
erkennbar.

## 1. Voraussetzungen für den Pilotstart (nicht für die Entwicklung)

Vor dem ersten Gespräch mit realen Nutzern sind **für alle beteiligten Dienste** EU-Verarbeitung
und -Speicherung sowie AVV/DPA nachgewiesen: GPT-Live und delegierte Responses,
Persona-Hilfsmodelle (z. B. Protokollant, Personas-Entwurf §4.2), Scoring/Schlüsselmomente,
Login, Datenbank, Hosting, Logs und Backups. Rohaudio wird weder bei uns noch bei Dienstleistern
dauerhaft gespeichert; zulässig sind nur notwendige flüchtige Verarbeitungspuffer.

| Voraussetzung | Wer | Stand |
|---|---|---|
| EU-Freigabe des OpenAI-Projekts; Erzeugung und Sideband über `eu.api.openai.com` geprüft (K6) | Pit / Claude | beantragt |
| OpenAI-DPA, inkl. Aufbewahrung delegierter Responses (`store` in der Delegation nicht setzbar; Speicherung damit ungeklärt, nicht widerlegt) | Pit | [offen] — **Pilotblocker** |
| AVV Hosting (Hetzner) und weitere Dienste aus §2 | Pit | [offen] |
| Abnahme nach §7 bestanden | Claude / Codex | [offen] |
| Täglicher API-Wächter eingerichtet (siehe unten) | Claude | [offen] — Gründervorgabe Pit, 2026-10-28 |

**API-Wächter (Pre-Go-Live-Todo).** Anlass: Am 2026-10-28 lehnte die Live-API
`allowed_server_events` als Stringliste plötzlich mit `400 invalid_type` ab; Gespräche waren
unmöglich, bis der Code angepasst war (`15e687a`). Das darf im Live-Betrieb nicht passieren.
Ein täglich laufender Agent:

1. **Recherchiert** Änderungen und angekündigte Änderungen der genutzten Schnittstellen
   (GPT-Live, Sideband, delegierte Responses, später weitere Dienste aus §2): API-Referenz,
   Changelog, Deprecations, Modell- und Preisseiten.
2. **Prüft aktiv**, weil Änderungen auch unangekündigt kommen: täglicher synthetischer Start mit
   unserem echten Sitzungs-Payload und synthetischem SDP, sofort geschlossen (≈ 1 Cent je Lauf,
   ≈ 0,30 $/Monat; ohne Personenbezug, ohne Audio).
3. **Ändert den Code automatisch**, wenn eine Anpassung nötig ist: eigener Branch, Tests,
   Cross-Review nach CLAUDE.md; Ergebnis und Befund gehen an Pit.
4. Meldet Fehlschläge sofort, bevor Nutzer sie bemerken.

Offen vor Umsetzung: ob ein geprüfter Fix ohne Pits Einzelfreigabe in den Live-Betrieb gehen
darf (Empfehlung Claude: nein, Live-Deployment nur nach Review und grünen Tests mit Pits
Freigabe, bis ein Bereitschaftsprozess steht); Ausführungsort (VM oder Cloud-Routine) und
Zugriff auf den Key nur für den synthetischen Startcheck.

Bis dahin entwickeln wir mit Region `referenz`, aber nur in ausdrücklich beauftragten und
gekennzeichneten Läufen mit synthetischen Daten oder Pits freigegebener Stimme; keine
automatische Referenzkonfiguration (CLAUDE.md).

## 2. Reihenfolge

Jeder Schritt hat eigene Abnahmekriterien, wird von Claude geplant, von Codex geprüft und von
beiden umgesetzt (CLAUDE.md, Zusammenarbeit).

| Schritt | Inhalt | Abnahme (Kurzform) |
|---|---|---|
| 1 | **Hybrid-Server und Sitzungslebenszyklus** (§3), mit minimaler Anmeldung und Nutzerzuordnung | Sitzungen nur für angemeldete Nutzer; Parallelitäts- und Kostenlimits atomar; Zeitlimit; Aufräumen bei Abbruch und Neustart; Logs ohne Inhalte; Debug-/Unlock serverseitig ausgeschlossen |
| 2 | **`web/`** mit einer Persona: Verbinden, Sprechen, Hören, Transkript, KI-Hinweis, Beenden | Gespräch im Browser über den Server aus Schritt 1; manuelle Prüfung nach CLAUDE.md |
| 3 | **Persona-Gerüst** und Markus Brandt überarbeitet, inkl. Protokollant ([Entwurf](./phase-1-personas-entwurf.md)), aufbauend auf Branch `persona-extension` (§4a); Stimmen-/Anbieterangaben (Azure) auf GPT-Live umstellen | Regressionen für Rollentreue, Rollenwechsel und Echo; Regel für Turn-Zuordnung verspäteter Protokollant-Ergebnisse und für Ausfall |
| 4 | Übrige drei Personas / Szenarien | dieselben Regressionen je Persona |
| 5 | **Self-Service-Login und vollständiger Zugriffsschutz** | Mindesttrennung nach §5 nachgewiesen |
| 6 | **Persistenz, Scoring, Schlüsselmomente, Löschung** (§4, §5) | erst nach beschlossenen Fristen und Löschwegen inkl. Dienstleistern und Backups |
| 7 | **Pilot-Abnahme** (§7): EU-Umstellung, Last, Latenz im Browser, README | alle Punkte aus §1 und §7 |

Erledigt vorab: Lasttest (Pipecat-Referenzpfad) und Architekturversuch (Hybrid), beide 2026-10-27.

## 3. Architektur: Hybrid (entschieden)

**Entschieden (Pit, 2026-10-27)** nach dem [Architekturversuch](./phase-1-architekturversuch-hybrid.md):
Browser ↔ OpenAI per WebRTC, ergänzt um einen serverseitigen **Sideband**. Der Datenkanal des
Browsers ist gesperrt (`allowed_client_events: []`); Transkript, Werkzeuge, Gesprächsende und
Scoring-Grundlage entstehen serverseitig. Ergebnis: K1, K2, K3, K5 erfüllt, K6 offen bis zur
EU-Freigabe.

- **Manipulationsschutz** heißt: serverseitige Auswertungsgrundlage mit geprüfter
  Datenkanalsperre. **Nicht** abgedeckt sind Angriffe über das gesprochene Wort (z. B. „Ignorieren
  Sie Ihre Anweisungen“); dafür Regressionen in Schritt 3.
- LiveKit und die Pipecat-Audiopipeline gehören zum bisherigen Mess- und Testpfad
  (`synthetic_caller`, Lasttest), nicht zum Produktpfad. Die Hybrid-Latenz wird neu
  instrumentiert (§7); ein vergleichbarer Browser-Latenznachweis steht aus.
- Ausgangspunkt für Schritt 1 ist der Prototyp `agent/tools/gptlive_browser` (Sideband,
  Notschluss, Zeitlimit, Beacon beim Tab-Schließen). Nicht übernehmen: browserseitige
  `debug`/`unlocked`-Schalter, lokale Bindung ohne Anmeldung.
- Kein Kaskaden-Rückfall (Pit, 2026-10-27); der B-Pfad wird nicht als zweiter Weg gepflegt.

**Server-Schritt (1) im Einzelnen:** EU-Hosting; authentisierte Sitzungszuordnung; atomare
Start- und Parallelitätslimits; maximale Gesprächsdauer; Kostenbudget mit Guthabenwarnung und
Startverweigerung vor Erschöpfung (Lasttest: leeres Guthaben bricht laufende Gespräche beim
Auflegen und neue Sitzungen ab); Aufräumen bei Abbruch und Serverneustart; strukturierte
Betriebslogs ohne Gesprächsinhalte; Debug-Funktionen im Pilotbetrieb serverseitig
ausgeschlossen.

## 4. Scoring (einfach) und Schlüsselmomente

Nur Gesprächsinhalt und -struktur aus dem serverseitigen Transkript, keine Auswertung von
Stimme oder Prosodie (CLAUDE.md). Unvollständige oder technisch gestörte Gespräche
(z. B. `unvollstaendig`, Abbruch durch Dienstfehler) erhalten **keinen regulären Score**.

**Schlüsselmomente (Idee Pit, 2026-10-27):** Nach dem Gespräch zieht ein eigenes Modell aus dem
**Transkript** die Stellen heraus, an denen sich das Gespräch entschieden hat, mit kurzer
Begründung. Grundlage ist ausschließlich Text. Gespeichert werden nur diese Ausschnitte und
die Auswertung. Ziel: später Muster über viele Gespräche erkennen.

- Grundprinzipien des Scorings (entschieden, §6); Kriterien je Szenario **[offen]** bis Schritt 6.
- Modell und Anbieter **[offen]**; Modellanbindung erst nach Datenflussprüfung (§1).
- Ausgangspunkt: Judge-Werkzeuge aus Phase 0 (`tests/judge.py`, `metrics/conversation.py`).
- **Gamification (Pit, 2026-10-28):** Meilensteine, Live-Ereignisse und Punkte im Gespräch;
  Hilfen (Tipps, Transkript) gegen Punktabzug – Skizze und offene Punkte in
  [Schritt 2 §9](./phase-1-schritt-2-web.md).

## 4a. Persona-Logik: Branch `persona-extension`

Stand 2026-10-12, drei Commits auf Basis `7781ac8`, **42 Tests grün** (geprüft 2026-10-27).
Umgesetzt nach Personas-Entwurf §2–§4:

- `personas/model.py`: Persona als reine Daten (Rolle, Übungsprodukt, Fakten, verdeckte
  Schmerzpunkte, Einwände, Stimmungsparameter, Meilensteine mit Toren)
- `personas/state.py`: deterministischer Gesprächszustand ohne LLM (Schmerzpunkt-Stufen,
  Geduld, Offenheit, Meilensteine), Eingabe nur Ereignisse aus Transkripttext
- `personas/protocol.py`: Protokollant, ordnet je Turn Ereignisse zu (Zählbares per Code,
  Inhaltliches per kleinem LLM-Aufruf), wirkt ab dem nächsten Turn als Regiezeile; inkl.
  „geleakte“ Schmerzpunkte und Zusage-Werkzeug
- `personas/prompt.py`: Systemprompt und Werkzeuge aus den Daten; Verhaltensregeln
  (KI-Transparenz, kurze Antworten, Auflegen) zentral und nicht wegkonfigurierbar
- `personas/markus_brandt.py`: Brandt im neuen Format (Prompt-Durchgang 3, **noch nicht im
  Gespräch getestet**)
- `tests/test_personas.py`, erweiterter `role_test.py`

**Übernahme in Schritt 3:** Die neuen Module konfliktfrei übernehmen. Nicht übernehmen: die
Anbindung an die Pipecat-Pipeline (`pipeline.py`, `stacks.py`; Merge-Konflikte mit `gpt-live`).
Stattdessen im Hybrid: Protokollant auf dem Server, gespeist aus dem Sideband-Transkript; die
Regiezeile geht über den Sideband (`session.instructions.append` bzw. `session.thinking.append`,
höchstens 500 Tokens). Der LLM-Aufruf des Protokollanten nutzt derzeit Azure OpenAI EU;
Anbieter für Phase 1 **[offen]** (Azure EU mit AVV oder OpenAI nach EU-Freigabe, §1).

## 5. Login, Zugriffsschutz und Löschkonzept

- **Mindesttrennung (entschieden):** Nutzer können ausschließlich eigene Sitzungen und
  Ergebnisse lesen oder verändern. Kundenübergreifender Zugriff ist ausgeschlossen.
  Kunden-Admins sehen in Phase 1 keine Ergebnisse ihrer Nutzer (Manager-Dashboard: Phase 2).
- Self-Service-Login; Anbieter und Datenhaltung in der EU **[offen]** bis Schritt 5.
- **Datensparsamkeit (Pit, 2026-10-27):**
  - **Kein Rohaudio**, weder Nutzer- noch Persona-Audio.
  - Vollständiges Transkript nur so lange wie für Anzeige und Auswertung nötig; Frist **[offen]**.
  - Länger aufbewahrt: Schlüsselmomente und Scoring-Ergebnis; Frist **[offen]**.
  - Löschung automatisch, auch bei Dienstleistern und in Backups.
- Persistenz über Flatfiles hinaus erst nach beschlossenen Fristen und Löschwegen; Auswahl
  **[offen]** bis Schritt 6.

## 6. Entscheidungen

**Entschieden mit der Freigabe (Pit, 2026-10-27):**

1. **Sichtbarkeit:** Jeder Nutzer sieht nur eigene Sitzungen und Ergebnisse; Kunden-Admins
   sehen in Phase 1 nichts (§5).
2. **Scoring-Grundprinzip:** Bewertet wird nur, was gesagt wurde und wie das Gespräch
   aufgebaut war. Technisch abgebrochene oder unvollständige Gespräche erhalten keinen Score,
   nur einen Hinweis (§4).
3. **Persona-Logik:** Zuerst Markus Brandt mit Stimmung, Schmerzpunkten und Meilensteinen auf
   Basis von `persona-extension` (§4a), danach die übrigen drei Personas nach demselben Muster.
4. **Grenzen:** höchstens 1 laufendes Gespräch je Nutzer, Gesprächsdauer höchstens 10 Minuten,
   Monatsbudget **25 $** (Pit, 2026-10-27) mit Warnung bei 80 % und Startverweigerung vor Erreichen.

**Darf bis zum jeweiligen Schritt offen bleiben** (Verantwortliche: Pit für Verträge, Claude
für technische Auswahl): Hosting-, Login-, Datenbank- und Scoring-Anbieter, Scoring-Kriterien je
Szenario, Aufbewahrungsfristen, neue absolute Latenzziele (Regressionen werden in jedem Fall
gemessen).

## 7. Abnahme vor dem Pilot und bekannte Risiken

| Punkt | Abnahme |
|---|---|
| Last | Hybrid unter der vereinbarten Parallelität (bis 20) prüfen. Der Lasttest vom 2026-10-27 lief über den Pipecat-Referenzpfad und ist orientierend (formal L5/L10 „unklar“, L20 „nicht bestanden“ wegen Guthaben), keine Hybrid- oder EU-Freigabe. |
| Latenz | Browser-Messung auf der EU-Mess-VM mit dokumentiertem Messpunkt, Kaltstarts, Fehlern, Unterbrechungen und Verzögerung bis zum Antwortinhalt; Vergleichsläufe präregistriert und abwechselnd. |
| Rollenbruch | Im Hybrid-Versuch 1 von 20 Sitzungen (Persona sprach den Pitch des Anrufers). Regressionen für Rollenwechsel, Echo und Angriffe per Sprache je Persona; Akzeptanzkriterium vorab festlegen. |
| Tab-Abbruch | Ohne Gegenmaßnahme 21–27 s Nachlauf. Beacon-Korrektur live nachmessen; Grenzwert und serverseitige Erkennung auch ohne Beacon (z. B. ausbleibendes Nutzer-Audio) festlegen. |
| Guthaben | Warnschwelle, Startverweigerung vor Erschöpfung, verständlicher Fehlerstatus; technische Abbrüche nicht als Nutzerleistung werten. |
| EU (K6) | Erzeugung und Sideband mit freigegebenem EU-Projekt erneut prüfen. |
