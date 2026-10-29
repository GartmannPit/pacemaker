# Phase 1, Schritt 2b — Gesprächsablauf neu (Plan)

Stand: 2026-10-29 · Status: **FREIGEGEBEN (Pit, 2026-10-29)** nach Codex-Review (Runde 3, §9); Vorab-Probe V1
bestanden (Nachtrag am Ende: Begrüßung über `session.commentary.append`); Wortlaut
Meldung/Aufgaben und Timer-Frage (§8) offen ·
Anlass: Rückmeldung Pit 2026-10-29 zur Seite aus [Schritt 2](./phase-1-schritt-2-web.md) ·
Bezug: [Phase-1-Plan](./phase-1-mvp.md) §2, [Schritt 1](./phase-1-schritt-1-server.md) A6

## 1. Ziel

Der Ablauf wird ein Anruf mit klarer Dramaturgie: Start → Briefing mit Countdown → Anwählen →
Gespräch → Ausfüllen → Scoreboard. Jede Ansicht ist reduziert auf das, was in diesem Moment
gebraucht wird. Die Persona nimmt den Anruf an und spricht zuerst.

**Entscheidungen Pit (2026-10-29):**
- Meilenstein-Leiste oben im Gespräch **bleibt**.
- Framework-Auswahl wird gebaut; **aktiv nur BANT**, weitere folgen mit der Charakterkarte
  (Schritt 3).
- Scoreboard-Ablauf jetzt, **Punkte erst mit dem Scoring**; bis dahin nur echte Daten.

**Nicht Teil dieses Schritts:** Punkte, Abgleich der Notizen, Werte weiterer Frameworks,
Hilfen gegen Punktabzug, Speicherung (Schritt 3/6).

**Durchgehend in allen Ansichten A–E2:** sichtbarer, nicht ausblendbarer Hinweis
„KI-Gesprächspartner“ im Kopf (CLAUDE.md, KI-Transparenz), unabhängig vom Ladezustand des
Briefings.

## 2. Vorab-Probe (vor der Umsetzung)

**V1 – Begrüßung per Sideband.** Das gebundene SDK beschreibt `response.create` als Start bzw.
Fortsetzung delegierter Arbeit; dass es ohne vorherigen Nutzerbeitrag eine **gesprochene**
Begrüßung erzeugt, ist nicht belegt. Kleinlauf (Region `referenz`, kein Audio vom Nutzer,
höchstens 2 Sitzungen à ≤ 30 s, Schätzung ≈ 0,05 $, Ist-Kosten dokumentiert): Sitzung
erzeugen, Browser verbindet, Freigabe nach §4, dann `response.create`; Ergebnis: kommt
Persona-Audio? Falls nein, Alternative im selben Lauf: `conversation.item.create` mit einer
Systemnotiz („Das Telefon klingelt, Sie nehmen ab.“) plus `response.create`. Der Plan wird
mit dem Ergebnis als Nachtrag ergänzt, bevor Schritt 2b umgesetzt wird.

## 3. Ablauf und Ansichten

### A. Start
- Anmeldung unverändert (eigene Ansicht davor).
- Ein großer Hauptknopf **„Anruf starten“**, darüber die **Framework-Auswahl**: BANT
  vorausgewählt; weitere (z. B. MEDDIC, SPICED) sichtbar, deaktiviert, „in Vorbereitung“.
  Kontingent-Hinweis wie heute; KI-Hinweis im Kopf.
- **Klick auf „Anruf starten“** (synchron, vor dem ersten `await`): `AudioContext` erzeugen und
  `resume()` aufrufen; danach Mikrofon anfragen. Während die Berechtigungsanfrage offen ist,
  Phase `mikrofon_anfrage` mit „Abbrechen“. Ablehnung: Hinweis, zurück zu A, keine Sitzung,
  kein Provider-Aufruf. Ein spät eintreffender Stream nach Abbruch wird sofort gestoppt
  (bestehender Schutz in `gespraech.ts`).

### B. Briefing mit Countdown
- Inhalt: Persona (Name, Rolle, Unternehmen, öffentlicher Hinweis), **Ihre Aufgaben**,
  Kriterien des gewählten Frameworks mit Leitfrage, maximale Gesprächsdauer. Daten aus
  `GET /api/briefing`, nur öffentliche Angaben.
- **Countdown 20 s, groß.** Knöpfe: „Überspringen“ (→ C), „Anhalten“/„Fortsetzen“,
  „Abbrechen“ (→ A, Mikrofon frei).
- **Mikrofon:** Der Track aus A bleibt lokal offen und wird in C wiederverwendet (kein zweiter
  Dialog). Es besteht noch keine Verbindung; nichts verlässt den Browser. In C wird er
  **stummgeschaltet** (`enabled = false`) zum Peer hinzugefügt und erst beim Eintritt in D
  freigegeben (auch über den Fristpfad); Geräusche während des Wähltons erreichen den Provider
  so nicht. Ist der Countdown
  länger als 5 min angehalten, wird der Track gestoppt und die Seite kehrt mit Hinweis zu A
  zurück.
- Noch keine Sitzung: Die OpenAI-Sitzung entsteht erst in C (keine Kosten, kein Zeitlimit
  während des Lesens).

### C. Anwählen
- Beim Eintritt: `POST /api/session` startet; parallel **Wählton**: kurze Tastentöne, danach
  Freizeichen (425 Hz, 1 s Ton / 4 s Pause). Synthetisch per Web Audio, **keine Audiodatei**.
  Der Wählton hat einen eigenen Audiograph und wird nie in die Erkennung des Persona-Audios
  eingespeist.
- Herzschlag startet, sobald die `session_ref` vorliegt (wie heute), unabhängig vom Wählton.
- Der Browser sendet **`POST /api/session/bereit`** (§4) erst, wenn die WebRTC-Verbindung
  `connected` ist **und** die Wiedergabe freigegeben ist (`AudioContext` `running`, `play()`
  des `<audio>`-Elements erfolgreich). Erst dann löst der Server die Begrüßung aus.
- **Ende des Wähltons:** sofort beim ersten erkannten Persona-Audio (§5), ohne
  Mindestdauer und ohne Überlagerung; dann Wechsel zu D.
- **Ton blockiert:** Ist der `AudioContext` nicht `running` oder schlägt `play()` fehl, zeigt C
  sofort „Ton aktivieren“ und sendet `bereit` erst nach erfolgreicher Freigabe. Ohne Freigabe
  binnen 30 s: Sitzung beenden (Endgrund `nutzer`), zurück zu A mit Hinweis.
- **Fristen** (getrennt): HTTP-Start 50 s (unverändert, `api.ts`); Verbindungsaufbau wie heute;
  **erstes Persona-Audio 15 s nach `bereit`**. Läuft diese Frist ab, endet der Wählton und D
  öffnet mit dem Hinweis „Ihr Gegenüber ist verbunden, aber still – Sie können sprechen.“
  Die Sitzung läuft weiter.
- **Übergänge bei Fehlern** (Wählton aus, Timer und Medien sofort freigeben, verspätete
  erfolgreiche Startantwort gezielt beenden wie heute):
  - **401 in jeder Phase** → Anmeldung; Transkript, Notizen und Abschlussdaten aus DOM und
    Speicher löschen (Schritt 2, wie heute).
  - Andere Fehler oder Abbruch **vor Gesprächsbeginn** (Abbrechen, Startfehler, 404,
    ICE-Abbruch, Herzschlagfrist, fehlende Tonfreigabe) → A mit Meldung, nicht E1.
  - Ende **nach Gesprächsbeginn** → E1.

### D. Anrufseite (clean)
- Oben: **Meilenstein-Leiste** wie heute (Inhalt „folgt“ bis Schritt 3).
- Mitte: **Sprechblase/Bühne** mit Sprecheranzeige (heutige Ringe).
- Links: **Aufgaben** und **Framework-Kriterien** kompakt (Status „angesprochen“ ab Schritt 3).
- Bei der Persona: Name und Hinweis „KI-Gesprächspartner“. **Restzeit** klein neben „Auflegen“
  (ersetzt die Anzeige der entfallenden Cue-Leiste; Durchsetzung bleibt beim Server).
- Entfällt: Persona-Beschreibung, Produktfußzeile, Cue-Leiste. Bleibt: Auflegen,
  Transkript-Schublade (standardmäßig zu), Ton aktivieren.

### E1. Ausfüllen (clean)
- Nur nach Eintritt in D (erstes Persona-Audio, Transkript-Ersatzsignal oder Frist aus C).
- Je Framework-Kriterium ein Feld („Was haben Sie erfahren?“), ein Knopf „Fertig“.
- Notizen bleiben **im Browser** (Schritt 2 §10), werden nicht gesendet.

### E2. Scoreboard
- **Abschlussdatensatz** (strukturiert, lokal): Gesprächsbeginn (erstes Persona-Audio,
  Transkript-Ersatzsignal oder Fristablauf), Ende, und **getrennt typisiert** entweder ein
  Server-Endgrund (`EndReason` aus `hybrid/contracts.py`) oder eine lokale Fehlerart
  (z. B. Verbindung verloren, Herzschlagfrist, Steuerungsfehler); unbekannte Server-Gründe als
  „unbekannt“. 401 erzeugt keinen Abschlussdatensatz (Anmeldung, Daten gelöscht).
  Ein lokal ausgelöstes Ende wird nicht als bestätigter Abschluss beim Provider dargestellt.
- Anzeige: Gesprächsdauer (ab Gesprächsbeginn, nicht ab HTTP-Antwort), Endgrund im Klartext,
  ausgefüllte Felder (z. B. 3 von 4). Punkte: „folgen mit der Auswertung“, **keine erfundenen
  Werte**.
- **Schließt nach 10 s** → A; „Überspringen“ schließt sofort; „Anhalten“/„Fortsetzen“.

### Timer-Regeln (B und E2)
- Einziger Pausengrund ist der Knopf „Anhalten“ (keine Pause durch Hover oder Fokus; so
  pausiert der Fokus auf dem Scoreboard den Timer nicht unbemerkt).
- Fokus beim Ansichtswechsel auf die Überschrift der neuen Ansicht; ausgeblendete Ansichten
  sind `hidden`/`inert`; Rückkehr zu A fokussiert „Anruf starten“.
- Ansage per `aria-live`: zu Beginn („Briefing, Anruf startet in 20 Sekunden“ bzw.
  „Ergebnis, schließt in 10 Sekunden“) und bei 5 s; nicht sekündlich.
- `prefers-reduced-motion`: Zahlen ohne Animation.
- Alle Timer, Track, Wählton und `AudioContext` werden bei Abbruch, Fehler, Abmelden und
  `pagehide` sofort freigegeben; ein alter Timer kann C nie nachträglich auslösen
  (Generationszähler wie in `gespraech.ts`).

## 4. Server

- **Begrüßung nach Browser-Bereitschaft:** neuer Endpunkt `POST /api/session/bereit
  {session_ref}`; authentisiert, nur eigene laufende Sitzung, idempotent (zweiter Aufruf
  ohne Wirkung, 200), Same-Origin wie die übrigen Endpunkte. Er löst im Register genau einmal
  die **initiale Begrüßungsanforderung** aus; spätere `response.create` für Werkzeugergebnisse
  bleiben unberührt.
- Der Sideband sendet die Begrüßung über den bestehenden `_send`-Pfad mit Sendesperre,
  Close-Prüfung und Zeitlimit. Sendefehler oder Provider-Ablehnung: Betriebslog
  `begruessung_fehlgeschlagen`, Sitzung läuft weiter (Browser-Frist aus C greift). Usage der
  Begrüßung fließt wie jede Response in die Abrechnung; Reserve und Ersatzabrechnung
  unverändert. Kommt `bereit` nicht, bevor die Sitzung endet, wird nichts gesendet.
- Persona-Prompt (Markus Brandt): Er nimmt einen Anruf an und meldet sich knapp
  (Vorschlag „Brandt, ja?“; Freigabe Pit), keine Begrüßungsrede; Abstimmung mit Schritt 3.
  Kein Firmenname: Das Briefing nennt nur „Logistikdienstleister“; ein realer Firmenname
  ist ausgeschlossen.
- `POST /api/session` akzeptiert neben `sdp` optional `framework_id` (String, Default `bant`);
  nur verfügbare IDs, sonst `400` ohne Provider-Aufruf. Alle anderen Felder werden weiter
  abgewiesen (u. a. Debug-/Unlock, A6). Kein Einfluss auf die Persona bis Schritt 3.
- `GET /api/briefing` ergänzt `frameworks: [{id, name, verfuegbar}]` und `aufgaben: [str]`;
  `framework` beschreibt weiter das aktive Framework (rückwärtskompatibel).
- `POST /api/session/messung` und optionales `messung` in der Ende-Anfrage nach §5.
- Der Browser-Datenkanal bleibt gesperrt; die Allowlist der Serverereignisse an den Browser
  ändert sich nicht.

## 5. Erkennung des ersten Persona-Audios und Messung

- **Detektor:** eigener `AnalyserNode` am entfernten Persona-Track (MediaStreamSource), immer
  aktiv und unabhängig vom Schalter der Pegelanzeige. Persona-Audio gilt als erkannt, wenn der
  RMS-Pegel 60 ms lang über einer festen Schwelle liegt (Werte in der Umsetzung kalibriert und
  dokumentiert). Die Wiedergabe läuft weiter über das bestehende `<audio>`-Element;
  der Wiedergabepfad ändert sich nicht.
- **Ausfallpfad:** Ist der Detektor nicht verfügbar (Context blockiert, Analyse fehlerhaft),
  darf das erste Transkript-Delta der Persona (`session.output_transcript.delta`, bereits in der
  Allowlist) den Wechsel nach D auslösen. Es wird als **eigener Zeitpunkt** `t_transkript`
  erfasst und belegt **kein** erstes Audio: `t_audio` und die Audio-Kennzahlen bleiben dann
  leer. Ohne beides greift die 15-s-Frist.
- **Messpunkte (nur Browseruhr):** `t_c` (Eintritt C), `t_bereit` (Senden von `bereit`),
  `t_audio` (erstes Persona-Audio), `t_transkript` (erstes Persona-Transkript-Delta).
  Kennzahlen: `c_bis_audio_ms`, `bereit_bis_audio_ms`, `c_bis_transkript_ms` (jeweils leer,
  wenn der Punkt fehlt), Status `ok`/`frist`/`abbruch`/`fehler`. Die Briefingzeit ist nicht
  enthalten.
  Messpunkt laut Messvertrag: **Erkennung im Browser am empfangenen Persona-Track** (nahe am
  Wiedergabebeginn, nicht identisch).
- **Erfassung** (einmaliger Versuch, blockiert nie das Schließen):
  - Beim Eintritt in D (Sitzung läuft sicher): `POST /api/session/messung {session_ref,
    messung}`, authentisiert, nur eigene laufende Sitzung, idempotent (erste Messung zählt),
    nur Ganzzahlen bzw. leer und feste Werte; Server schreibt per Allowlist `anruf_messung`
    ins Betriebslog, ohne den Endgrund oder das Register zu verändern.
  - Bei eigenem Abbruch in C: Kennzahlen mit Status `abbruch` als optionales Feld `messung` in
    der bestehenden Ende-Anfrage; das Ende wird davon nie abhängig.
  - Endet die Sitzung serverseitig vor D (Persona-Ende, Zeitlimit, Fehler, Beacon), wird nichts
    nachgesendet. Die fehlende Messung bleibt im Betriebslog erkennbar (Sitzung ohne
    `anruf_messung`); sie zählt als Ausfall, nicht als stiller Ausschluss.
  - Serverseitig separat: Dauer von `bereit` bis `response.created` (Serveruhr). Keine
    Subtraktion zwischen Browser- und Serveruhr.
- **Regression:** Der Turn-Pfad (Provider, Wiedergabe über `<audio>`) bleibt unverändert;
  neu sind nur Eröffnung, Wählton und eine passive Analyse. Ein präregistrierter
  Vergleichslauf der Antwortlatenz im Gespräch wird daher **nicht** für 2b angesetzt (siehe
  §9, begründete Ablehnung); er gehört zur Browser-Latenzmessung in Schritt 7. **Ein
  Latenzeinfluss auf die Gesprächsantworten wurde nicht gemessen.** Änderungen am tatsächlichen
  Wiedergabepfad wären von dieser Begründung nicht gedeckt. Die neuen Eröffnungszeiten werden in
  B10 erhoben, ohne Zielwert.

## 6. Umsetzung und Aufteilung

- Reihenfolge: V1 (Claude) → Nachtrag → Freigabe Pit → Umsetzung.
- Worktree je Aufgabe (CLAUDE.md). **Codex:** Seite (`web/`): Ansichten A–E2, Zustandsautomat,
  Timer, Wählton, Detektor, Abschlussdatensatz, Tests. **Claude:** Server (`bereit`-Endpunkt,
  Begrüßung im Register/Sideband, Persona-Regel, `framework_id`, Briefing-Felder,
  `messung`-Endpunkt und `anruf_messung` im Betriebslog), Tests; Cross-Review.
- Design-Skills nach `.claude/skills/HERKUNFT.md`; Farbwelt Ultramarin, Entwurf C bleibt
  Grundlage.
- Logik getrennt vom DOM testbar (injizierte Uhr, Fakes für Medien, Audio und API).

## 7. Abnahme

| # | Kriterium |
|---|---|
| B1 | Ablauf A → B → C → D → E1 → E2 → A; Abbrechen in A (Berechtigungsanfrage), B und C → A ohne E1; 401 in jeder Phase → Anmeldung mit gelöschten Daten; Fehler vor Gesprächsbeginn → A, nach Gesprächsbeginn → E1; fehlende Tonfreigabe 30 s → A; Überspringen in B und E2; Anhalten/Fortsetzen in B und E2; 5-min-Grenze in B; Fokusziele und Ansagen nach §3. |
| B2 | Mikrofonablehnung in A: Hinweis, keine Sitzung, kein Provider-Aufruf; spät eintreffender Stream wird gestoppt. |
| B3 | Wählton startet mit C, endet bei erstem Persona-Audio, Frist, Fehler und Abbruch; keine Audiodatei im Build; Wählton löst den Detektor nicht aus. |
| B4 | `bereit`: genau eine initiale Begrüßung, auch bei doppeltem Aufruf; keine Begrüßung ohne `bereit`, bei fremder `session_ref`, nach Ende oder bei Attach-Fehler; Sendefehler/Ablehnung → Betriebslog, Sitzung läuft; `bereit` erst nach Verbindung und Wiedergabefreigabe; Mikrofon in C stumm (Nutzergeräusche während C erreichen den Peer nicht), frei ab D; Werkzeug-Fortsetzungen unverändert; Datenkanal weiter gesperrt (bestehende Tests grün). |
| B5 | `framework_id`: fehlend (→ `bant`), gültig, unbekannt, nicht verfügbar, falscher Typ; Zusatzfelder einschließlich Debug/Unlock weiter abgewiesen; Abweisung ohne Provider-Aufruf. |
| B6 | Abschlussdatensatz mit festen Eingaben: Dauer ab Gesprächsbeginn, alle Server-Endgründe einschließlich „unbekannt“ und lokale Fehlerarten getrennt, lokales Ende nicht als bestätigt; keine Punkte; Schließen nach 10 s außer angehalten. |
| B7 | KI-Hinweis in A, B, C, D, E1, E2 sichtbar, auch vor geladenem Briefing; Restzeit in D. |
| B8 | Detektor: anfängliche Stille, blockierte Wiedergabe, deaktivierte Pegelanzeige, Ausfall → Transkript-Ersatzsignal mit leerem `t_audio`; `messung`-Endpunkt: nur eigene laufende Sitzung, idempotent, nur erlaubte Felder, Endgrund unverändert; Abbruch-Messung in der Ende-Anfrage optional, Ende nie davon abhängig; serverseitiges Ende vor D ohne Messung im Betriebslog erkennbar. |
| B9 | Prüfungen: Agent `pytest`, `ruff check`, `ruff format --check`; Web `pnpm typecheck`, `lint`, `format:check`, `test`, `build`. |
| B10 | Manuell (W8 erweitert, Region `referenz`, Pits Stimme): Ablauf, Wählton, Persona meldet sich hörbar zuerst, „Ton aktivieren“ nach automatischem Countdown, langem Anhalten und Hintergrundwechsel in Chrome/Edge und Firefox; Eröffnungszeiten aus §5 erhoben und dokumentiert; Kostenschätzung ≈ 0,30 $ zusätzlich zu W8. |

## 8. Offen

- Wortlaut der Aufgaben und der Meldung von Brandt (Vorschlag Claude, Freigabe Pit).
- Ob Pit die Timer ohne „Anhalten“ möchte: Das wäre eine bewusste Abweichung von WCAG 2.2.1,
  keine Erfüllung.

## 9. Reviews Codex (2026-10-29)

**Runde 3** (gezielte Nachprüfung) – Votum: **freigabefähig**. P3 übernommen (E1 nennt alle
Wege nach D). In Umsetzung und Code-Review: Die 30-s-Frist begrenzt auch eine ausstehende
Wiedergabefreigabe; Messanfrage und serverseitiges Ende können zusammentreffen, eine
fehlgeschlagene Übermittlung zählt als fehlende Messung.

**Runde 2** – Votum: nicht freigabefähig, kein P1. Übernommen: P2 Mikrofon in C stumm bis D
(§3 B, B4) · P2 `bereit` erst nach Wiedergabefreigabe, 30-s-Frist, Transkript-Ersatzsignal als
eigener Zeitpunkt ohne Audiowert (§3 C, §5, B4/B8) · P2 Messung über eigenen Endpunkt bei
Eintritt D, Abbruch in der Ende-Anfrage, fehlende Messung erkennbar (§5, B8) · P2 401 →
Anmeldung, lokale Fehlerarten getrennt von Server-Endgründen (§3 C/E2, B1/B6) · P3 Verweis
B10. Teilablehnung zur Messung von Codex als vertretbar bewertet; Satz „Latenzeinfluss nicht
gemessen“ ergänzt (§5). In Umsetzung und Code-Review: Erweiterung `SidebandHandle`, atomare
Begrüßungsmarkierung im Register, Close-Rennen, Fehlerkorrelation, Detektorkalibrierung.

**Runde 1** – Votum: nicht freigabefähig. Übernommen:
P1 `attach` ≠ Browser bereit → `bereit`-Endpunkt (§4), B4 · P2 `response.create` unklar und
Fehlerpfade → Vorab-Probe V1 (§2), `_send`-Pfad, nur initiale Begrüßung, B4 · P2 Audio-Freigabe
→ §3 A/C („Ton aktivieren“ schon in C), B10 · P2 Ressourcen und Abbruch in B → §3 A/B/Timer,
B1/B2 · P2 Erkennung erstes Audio → §5, B3/B8 · P2 Fristen → §3 C · P2 KI-Hinweis und Restzeit
→ §1, §3 D, B7 · P2 Abschlussdatensatz → §3 E2, B6 · P2 Endpunkt `/api/session`,
`framework_id` → §4, B5 · P3 Timer → §3 Timer-Regeln, §8.

**Begründet abgelehnt (teilweise):** P2 Messung, Forderung nach präregistriertem
Regressionsvergleich der Gesprächsantworten. Browserlokale Messpunkte, Uhrentrennung,
Format und Status sind übernommen (§5). Ein Vergleichslauf der Antwortlatenz ist nicht
angesetzt, weil Turn-Pfad und Wiedergabe (`<audio>`) unverändert bleiben; der Analyser greift
nur passiv ab. Eine Browser-Latenzmessung im Gespräch ist ohnehin Teil von Schritt 7
(Phase-1-Plan §7). Entscheidet Pit anders, wird sie präregistriert ergänzt.

## Nachtrag: Vorab-Probe V1 (2026-10-29)

Referenzlauf (`OPENAI_LIVE_REGION=referenz`), Prompt `system_prompt(short_opener=False)` wie im
Server, Browser (Chromium über Playwright) als WebRTC-Gegenstelle mit **Stille statt
Mikrofon** (kein Nutzer-Audio). Probenskript außerhalb des Repos (Scratchpad), nutzt
`LiveStarter.create` und `HybridSideband.attach` des Servers. Messpunkt: erstes hörbares
gespiegeltes Persona-Audio **am Sideband (Serveruhr)**, nicht Wiedergabe im Browser.
2 Sitzungen, je 15 s Live-Zeit laut Usage; Kosten ≈ 0,03 $ (Budgetpreise 0,05 $/min Live, dazu
wenige Backend-Tokens in Sitzung 1). Schätzung vorab ≈ 0,05 $.

| Sitzung | Gesendet nach `bereit` | Erstes hörbares Audio | Gesagt |
|---|---|---|---|
| 1 | `response.create` | 1008 ms | „Mhm. Einen Moment, ich steig ein. Ja, also, ich bin grad echt ziemlich eingespannt. Worum geht's denn konkret? Wir haben für den Bereich …“ |
| 2 | `session.commentary.append` („Telefon klingelt, melde dich knapp mit Nachnamen, etwa ‚Brandt, ja?‘“) | 1129 ms | „Brandt, ja?“ |

**Folgerungen (ersetzen die betroffenen Teile von §2–§4):**
- Die Begrüßung nutzt **`session.commentary.append`** (`delegation_id: null`), nicht
  `response.create`. `response.create` startet eine delegierte Backend-Antwort
  (`session.delegation.created`, Backend-Textausgabe), erzeugt inhaltlich unpassende Sprache,
  kostet Backend-Tokens und würde sich mit der Werkzeug-Fortsetzungslogik des Sidebands
  (`_pending`) überschneiden. `session.commentary.append` wird mit
  `session.commentary.appended` bestätigt; diese Bestätigung kann nach dem ersten Audio
  eintreffen (Sitzung 2: 1430 ms).
- B4 entsprechend: genau ein `session.commentary.append` als initiale Begrüßung, keine
  Delegation; Fehlerpfad wie beschrieben.
- Hinweis für die Umsetzung: Der Sideband kann laut Architekturversuch auch
  `session.input_audio.mute`/`unmute` senden. Die Stummschaltung in C bleibt im Browser
  (`enabled = false`, §3 B); serverseitiges Stummschalten ist eine mögliche Ergänzung, keine
  Planänderung.
- Einzelwerte aus 2 Sitzungen, Serveruhr; **keine Browser-E2E-Latenz** und keine
  belastbare Aussage über Verteilung. Erhebung im Browser in B10.
- Wortlaut der Meldung: Vorschlag „Brandt, ja?“ (siehe §4); Freigabe Pit offen.

## Nachtrag: Umsetzung (2026-10-29)

- **Server (Claude, `70a2c2a`):** `bereit`-Endpunkt mit Begrüßung über
  `session.commentary.append` (Text `GREETING_COMMENTARY` in der Persona; der Persona-Prompt
  bleibt unverändert, weil er auch im Pipecat-Messpfad gilt), `messung`-Endpunkt und optionale
  Abbruchmessung in `/api/end`, `framework_id`, Briefing mit `frameworks`/`aufgaben`,
  Betriebslog `begruessung_*`/`anruf_messung`. Codex-Review: 3 × P2 (Typprüfung
  `framework_id`/Messstatus, Ende darf nie an der Messung scheitern, asynchrone Ablehnung der
  Begrüßung über `client_event_id`), behoben; Nachprüfung ohne Befund.
- **Seite (Codex, `4de0439`):** Ansichten A–E2, Countdown, Wählton, Detektor
  (RMS > 0,01 für 60 ms, Abtastung alle 20 ms; vorläufig, Kalibrierung in B10), Messung,
  Fehlerübergänge. Review Claude: Ablauf, Stummschaltung, `bereit`-Bedingung, Fristen und
  getrennte Audiographen geprüft. Hinweise: In gedrosselten Hintergrund-Tabs erkennt der
  Detektor kein Audio (Wechsel dann über das Transkript-Ersatzsignal); Persona-Audio vor
  `bereit` verfällt für die Erkennung. Der Codex-Lauf hing nach der letzten Prüfung
  (Laptop im Ruhezustand) und lieferte keinen Abschlussbericht; die Einschätzung zum
  Nachtrag V1 steht damit aus.
- **Prüfungen auf `gpt-live` nach Merge:** Agent `pytest` 283 grün, `ruff check`/`format`
  grün; Web `typecheck`, `lint`, `format:check`, 52 Tests, `build` grün.
- **Nicht ausgeführt:** B10 (manuelle Browser-Abnahme mit Pit), Eröffnungszeiten im Browser,
  Firefox/Edge, Hintergrund-Tab. Wortlaut von Meldung und Aufgaben vorläufig (§8).
