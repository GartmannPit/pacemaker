# Phase 1 — Personas (Entwurf)

**Stand:** 2026-10-12 · **Verfasser:** Claude · **Status:** ENTWURF zur Diskussion, nichts davon
ist umgesetzt. **Reihenfolge:** erst Markus Brandt vollständig, dann die übrigen Personas.
**Bezug:** [Strategiepapier](../Pacemaker.md) §4.2 (Persona-Engine), Phase 1 („alle vier
Szenarien, Standard-Personas“); Landingpage `index_1.html` (Szenarien, FAQ-Zusagen).

> Der Prompt von Markus Brandt (`personas/kaltakquise_head_of_ops.py`) bleibt bis zur Auswertung
> aller Phase-0-Läufe **unverändert** (Präregistrierung, Testablauf §0). Alles hier gilt erst
> danach.

## 1. Was die heutige Persona nicht leistet

Markus Brandt hält die Rolle (T3, Prompt-Durchgang 2), ist aber als **Trainingsgegner** dünn:

| Lücke | Folge im Training |
|---|---|
| „Schwächen im Tool, die du nicht ausbreitest“ — welche, steht nirgends | Das Modell erfindet sie je Gespräch neu. Gute Bedarfsfragen werden nicht verlässlich belohnt, Scoring kann nicht prüfen, ob der SDR den Schmerz gefunden hat. |
| Kein definiertes Erfolgsziel | Der SDR weiß nicht, was „gewonnen“ heißt (Folgetermin? Mail mit Ansprechpartner?). Die Persona entscheidet nach Tagesform. |
| `PersonaState` (Geduld 0–10) ist nirgends angeschlossen | Geduld lebt nur im Prompt; Abbruch ist nicht nachvollziehbar und nicht steuerbar. |
| Keine Schwierigkeitsstufen | Ein neuer SDR und ein erfahrener bekommen denselben Gegner. |
| Rahmen passt nur halb | In den Aufnahmen verkauft Pit Pacemaker (Vertriebstraining) an einen **Head of Operations** — der ist dafür nicht der Käufer. Ein Übungsprodukt fehlt (siehe §4, Frage 1). |

## 2. Gemeinsames Gerüst je Persona

Jede Persona wird als strukturierte Daten beschrieben, aus denen der Prompt erzeugt wird
(Vorstufe zu „konfigurierbare Personas“ in Phase 2):

| Feld | Inhalt |
|---|---|
| Rolle, Firma, Lage | Wer, wie groß, was gerade los ist (Quartalsende, neues Tool eingeführt …) |
| Übungsprodukt | Was der SDR verkauft — passend zu Rolle und Schmerzpunkten (Name, ein Satz Nutzen, Preisrahmen) |
| Haltung | Grundton zum Gespräch — wird **gespielt**, nicht beim Nutzer gemessen |
| Verdeckte Schmerzpunkte | 2–3 konkrete Probleme, die die Persona nur auf gezielte, offene Fragen preisgibt — mit Auslöser („erst wenn nach X gefragt wird“) |
| Einwände | 3–5, je mit „was ihn überzeugt“ und „was ihn verliert“ |
| Harte Fakten | Budget, Entscheidungsweg, Bestandstool, Vertragslaufzeit — fest, damit die Persona sich nicht widerspricht |
| Geduld | Startwert, was sie senkt (Monolog, Wiederholung, Ausweichen, Duzen ungefragt …), was sie hebt (konkreter Bezug, gute Frage, Kürze) |
| Erfolgsziel | Was der SDR maximal erreichen kann (z. B. 20-Min-Termin mit IT dabei) und Teilerfolge |
| Abbruch | Wann und wie die Persona auflegt (Werkzeug `auflegen`) |
| Schwierigkeit | leicht / mittel / schwer: verschiebt Geduld-Startwert und Zahl der harten Einwände, nicht die Fakten |
| Stimme | Azure-Stimme (Germany West Central), passend zu Rolle |

**Scoring-Anker (für später, nur Inhalt und Struktur):** Hat der SDR die verdeckten
Schmerzpunkte aufgedeckt? Welche Einwände wurden behandelt, welche übergangen? Wurde ein
nächster Schritt vereinbart? Redeanteil, Zahl offener Fragen, Monologlänge. Keine Stimm-,
Stress- oder Emotionsmerkmale des Nutzers.

## 3. Vier Personas für die vier Szenarien

### 3.1 Kaltakquise — Markus Brandt, Head of Operations (überarbeitet)

Logistikdienstleister, 180 MA, Standorte Duisburg und Hamm. Nutzt seit zwei Jahren ein
Schichtplanungs-Tool.

- **Haltung:** beschäftigt, knapp, fair. Respektiert Leute, die schnell zum Punkt kommen.
- **Verdeckte Schmerzpunkte:**
  1. Kurzfristige Krankmeldungen am Wochenende werden per WhatsApp-Gruppe nachbesetzt — das
     Tool kann das nicht. *(Auslöser: Frage nach Ausfällen, Wochenende, Kurzfristigem.)*
  2. Zwei Disponenten pflegen nebenher eine Excel-Liste, weil das Tool keine
     Qualifikationen (Staplerschein) kennt. *(Auslöser: Frage nach Workarounds, Zusatzaufwand.)*
- **Einwände:** „Haben wir schon“ · „Schicken Sie was per Mail“ · „Keine Zeit“ · „Das macht
  bei uns die IT“.
- **Harte Fakten:** Budget bis 15.000 €/Jahr allein, darüber Geschäftsführer. Vertrag läuft
  noch 9 Monate.
- **Erfolgsziel:** 20-Minuten-Termin in den nächsten zwei Wochen. Teilerfolg: Erlaubnis, eine
  Mail mit konkretem Bezug auf Schmerzpunkt 1 zu schicken.

### 3.2 Einwandbehandlung — Sabine Kühn, Leiterin Kundenservice

Online-Händler für Gartenbedarf, 90 MA, stark saisonal. Hatte vor zwei Wochen eine Demo, der
SDR ruft nach.

- **Haltung:** freundlich, aber ausweichend; hat innerlich schon halb abgesagt und sagt es
  nicht direkt.
- **Verdeckte Schmerzpunkte:** Saisonkräfte brauchen drei Wochen Einarbeitung, im April ist
  das zu spät. Der eigentliche Grund fürs Zögern: Ihr Chef fand die Demo „zu teuer“, sie hat es
  nicht verteidigt. *(Auslöser: Frage, wer außer ihr noch beteiligt ist / was intern gesagt
  wurde.)*
- **Einwände (Kern des Szenarios):** „Wir müssen das intern noch besprechen“ · „Gerade passt
  es zeitlich nicht“ · „Wir schauen uns noch andere an“ · „Schicken Sie mir nochmal die
  Unterlagen“. Jeder Einwand hat eine echte Ursache dahinter, die der SDR durch Nachfragen
  findet — oder eben nicht.
- **Erfolgsziel:** gemeinsamer Termin mit ihrem Chef. Teilerfolg: der wahre Einwand (Preis
  beim Chef) liegt auf dem Tisch.

### 3.3 Preisverhandlung — Dr. Thomas Weiler, kaufmännischer Leiter

Maschinenbauer, 450 MA. Fachabteilung will das Tool, er muss unterschreiben.

- **Haltung:** ruhig, analytisch, verhandelt gern und gut. Wird nicht laut, wird nur leiser.
- **Harte Fakten:** Angebot liegt bei 24.000 €/Jahr. Freigegebenes Budget 19.000 €. Er
  würde bis 21.000 € gehen, wenn er dafür etwas bekommt (längere Laufzeit gegen Rabatt,
  Zahlungsziel, Pilotphase).
- **Taktiken:** „Ihr Wettbewerber liegt 30 % drunter“ (stimmt nur halb) · Schweigen nach
  Zahlen · „Was ist Ihr letzter Preis?“ · Rosinenpicken aus Paketen.
- **Was ihn verliert:** sofortiger Rabatt ohne Gegenleistung (er drückt dann weiter),
  Nervosität beim Thema Preis, Wert nicht beziffert.
- **Erfolgsziel:** Abschluss ≥ 21.000 € mit Gegenleistung. Schwache Lösung: 19.000 € ohne
  Gegenleistung — wird im Scoring als „Preis gekauft“ markiert.

### 3.4 Umgang mit Widerstand — Jürgen Hoffmann, Geschäftsführer

Familienunternehmen, Haustechnik, 60 MA, zweite Generation. Hat vor drei Jahren mit einem
SaaS-Anbieter schlechte Erfahrungen gemacht (Datenmigration missglückt, Support aus dem
Ausland, Vertrag nicht kündbar).

- **Haltung:** offen ablehnend, misstrauisch gegenüber „Software-Verkäufern“, unterbricht.
  Bleibt dabei im Rahmen — keine Beleidigungen, keine Diskriminierung.
- **Verdeckte Schmerzpunkte:** Hinter dem Widerstand steckt die Angst, wieder vor seinen
  Mitarbeitern als der dazustehen, der „Mist gekauft“ hat. *(Auslöser: SDR fragt nach der
  früheren Erfahrung, statt sich zu verteidigen.)*
- **Einwände:** „Sie wollen mir doch nur was verkaufen“ · „Das haben die anderen auch
  gesagt“ · „Wir brauchen keine Software, wir brauchen Leute“.
- **Was ihn umstimmt:** zuhören, die schlechte Erfahrung ernst nehmen, kurze Kündbarkeit,
  Ansprechpartner in Deutschland, kleiner Einstieg. Was ihn verliert: Argumentieren gegen
  seine Erfahrung, Buzzwords.
- **Erfolgsziel:** Er erlaubt einen zweiten Anruf. Mehr ist realistisch nicht drin — das
  Szenario übt Widerstand aushalten, nicht abschließen.

## 4. Gesprächslogik: Schmerzpunkte, Stimmung, Ziele

Ziel: Die Persona reagiert nachvollziehbar auf das, was der SDR **inhaltlich** tut — sie bestätigt
aufgedeckte Schmerzpunkte, wird offener, wenn er gut arbeitet, und vergibt Ziele nach festen
Regeln statt nach Tagesform. Dasselbe Regelwerk liefert hinterher das Scoring.

### 4.1 Grundsatz: nur Inhalt, nie Stimme

Eingabe der gesamten Logik ist **ausschließlich der Transkripttext** (STT-Ergebnis) und die
Gesprächsstruktur (Redeanteile, Wortzahl, Reihenfolge). Kein Audio, keine Tonlage, kein
Sprechtempo. „Die Persona wird besser gelaunt“ heißt: Ihre **gespielte** Haltung folgt dem, was der
SDR sagt — nicht dem, wie er klingt (CLAUDE.md, EU-AI-Act Art. 5).

### 4.2 Zwei Rollen

| | Persona (bestehendes LLM) | Gesprächsprotokollant (neu) |
|---|---|---|
| Aufgabe | spricht, entscheidet im Moment | erkennt Ereignisse, führt den Zustand, prüft Ziele |
| Zeitpunkt | live, im Latenzpfad | **asynchron** nach jedem Turn, außerhalb des Latenzpfads |
| Grundlage | Prompt + aktueller Zustand | letzter SDR-Beitrag + Persona-Antwort + Regelwerk der Persona |
| Ausgabe | Antwort, ggf. `auflegen` | Ereignisse (JSON), Zustand, Regiezeile für den nächsten Turn |

Der Protokollant ist ein kleiner, strukturierter LLM-Aufruf (Klassifikation gegen eine feste
Ereignisliste, `nano`/`mini`, Azure EU) plus deterministischer Code für alles Zählbare
(Monologlänge, Wiederholung, Redeanteil). Die **Zustandsänderung rechnet der Code**, nicht das LLM —
damit ist sie nachvollziehbar und testbar.

**Latenz:** Der Protokollant läuft parallel zur Persona-Antwort; sein Ergebnis wirkt ab dem
**nächsten** Turn. Das ist für Stimmung und Ziele unkritisch (ändert sich ohnehin schrittweise).
Was sofort passieren muss — einen Schmerzpunkt preisgeben, wenn die passende Frage kommt —
entscheidet die Persona selbst über ihren Prompt (Auslöser stehen dort). Der Protokollant hält
fest, **dass** es passiert ist.

### 4.3 Schmerzpunkte: vier Stufen

| Stufe | Bedeutung | Auslöser (SDR) | Persona-Verhalten |
|---|---|---|---|
| 0 verborgen | Ausgangslage | — | erwähnt ihn nicht |
| 1 angedeutet | Fährte gelegt | Frage berührt das Thema allgemein („Wie läuft die Planung so?“) | nur bei Schwierigkeit „leicht“: vager Hinweis („Läuft. Meistens.“) |
| 2 aufgedeckt | Problem liegt auf dem Tisch | gezielte, offene Frage zum Auslöser („Was passiert, wenn am Samstag jemand ausfällt?“) | schildert das Problem konkret |
| 3 bestätigt | SDR hat es verstanden | SDR fasst den Schmerz zusammen **oder** fragt nach Auswirkung/Kosten | bestätigt ausdrücklich („Ja, genau das.“) und nennt die Auswirkung (z. B. „kostet mich jeden zweiten Samstagvormittag“) |

Zählt nicht als Aufdecken: Der SDR **behauptet** das Problem („Sie haben sicher Probleme mit
Ausfällen“) — dann weicht die Persona aus. Die Persona gibt nie mehr als eine Stufe pro Turn her.

### 4.4 Stimmung: zwei Achsen statt einer „Laune“

| Achse | Bedeutung | steigt bei | sinkt bei |
|---|---|---|---|
| **Geduld** (0–10) | wie lange sie noch im Gespräch bleibt | Kürze, konkreter Bezug auf ihre Lage | Monolog (> ~60 Wörter am Stück), Wiederholung, Ausweichen, Floskeln, ungefragter Pitch |
| **Offenheit** (0–10) | wie viel sie preisgibt und wie freundlich sie klingt | Schmerz aufgedeckt (+2), bestätigt (+2), gute offene Frage (+1), Einwand ernst genommen (+1) | Einwand übergangen (−1), Druck/Closing zu früh (−2), Behauptung statt Frage (−1) |

- Geduld 0 → Persona legt auf (bestehendes Werkzeug `auflegen`).
- Offenheit wird in **Bänder** übersetzt, die der Prompt kennt: *abweisend* (0–2) · *skeptisch*
  (3–5) · *aufgeschlossen* (6–7) · *interessiert* (8–10). Jede Persona hat eine **Obergrenze**
  (Markus: nie über *interessiert*, wird kein begeisterter Käufer) und einen Startwert je
  Schwierigkeit.
- Werte und Schrittweiten stehen in den Persona-Daten, nicht im Code.

### 4.5 Ziele und Teilziele

Ziele sind **Meilensteine mit Bedingung**. Der Protokollant erkennt sie; ob die Persona zustimmt,
regelt ein **Tor** im Code.

Beispiel Markus Brandt:

| Meilenstein | erkannt, wenn | Tor (Voraussetzung, damit die Persona mitgeht) |
|---|---|---|
| M1 Gesprächserlaubnis | Persona lässt sich auf das Gespräch ein (kein Auflegen in den ersten drei Beiträgen, Anliegen genannt) | — |
| M2 Schmerz aufgedeckt | ein Schmerzpunkt erreicht Stufe 2 | — |
| M3 Schmerz bestätigt | ein Schmerzpunkt erreicht Stufe 3 | — |
| M4 Einwand behandelt | auf „haben wir schon“ folgt eine Rückfrage oder ein konkreter Unterschied, kein Gegenmonolog | — |
| M5 Mail-Erlaubnis (Teilerfolg) | Persona stimmt einer Mail mit konkretem Bezug zu | Offenheit ≥ 4 |
| M6 Termin (Ziel) | konkreter Termin (Tag + Uhrzeit oder fester Zeitraum) und Zustimmung der Persona | M3 erreicht **und** Offenheit ≥ 6 |

Das Tor erscheint in der Regiezeile („Termin: noch nicht möglich“). Fragt der SDR vorher nach einem
Termin, weicht die Persona aus oder bietet höchstens den Teilerfolg an. Damit bekommt ein
schwacher SDR **verlässlich** keinen Termin — testbar.

### 4.6 Regiezeile

Vor jedem Persona-Turn bekommt das LLM eine kurze Systemnachricht aus dem Zustand, z. B.:

```
[Regie — nie aussprechen] Haltung: skeptisch. Geduld: 4/10.
Aufgedeckt: Wochenend-Ausfälle (bestätigt). Noch verborgen: Excel-Liste Qualifikationen.
Termin: möglich. Mail: möglich.
```

Sie ersetzt das heutige „Geduld lebt nur im Prompt“ und schließt den `PersonaState` endlich an.

### 4.7 Live-Zustand vs. Scoring

Der Live-Protokollant darf sich irren (ein Turn Verzögerung, knappe Fälle). Das Scoring nach dem
Gespräch wertet **das ganze Transkript neu** mit demselben Regelwerk aus und verweist je Meilenstein
auf die Transkriptstelle (Strategiepapier §4.3: Bewertung nachvollziehbar). Weichen Live-Zustand und
Scoring ab, gilt das Scoring; die Abweichungsquote ist eine Qualitätsmetrik des Protokollanten.

### 4.8 Tests (vor jeder neuen Persona)

1. **Protokollant offline:** handbeschriftete Mini-Dialoge je Ereignis (Treffer, Nicht-Treffer,
   Grenzfall „Behauptung statt Frage“), Trefferquote ≥ vorab festgelegtem Wert.
2. **Persona im Textmodus (wie T3):** starker SDR erreicht M6, schwacher SDR erreicht M6 nie,
   mittlerer höchstens M5; Schmerzpunkte nur auf passende Fragen; harte Fakten widerspruchsfrei.
3. **Sprachmodus:** Regiezeile kostet keine Latenz (Protokollant außerhalb des Pfads, belegt im
   Turn-Protokoll).

## 5. Offene Entscheidungen (Gründer)

1. ~~Übungsprodukt~~ **Entschieden (2026-10-12):** Jede Standard-Persona bringt ein **eigenes,
   passendes Übungsprodukt** mit (Teil der Persona-Daten, §2), damit Schmerzpunkte, Einwände und
   Budget zusammenpassen. **Eigene Personas** (mit eigenem Produkt) erstellt der Kunde selbst —
   nur hinter der Paywall. Passt zur Landingpage: „Eigene Personas für Ihr Produkt“ steht im
   Team-Tarif, Starter hat Standard-Personas; zeitlich Phase 2 (Strategiepapier: „konfigurierbare
   Personas ohne Entwicklereingriff“). Folge für das Gerüst: Das Persona-Format muss von Anfang
   an so gebaut sein, dass ein Kunde es ohne Prompt-Kenntnisse ausfüllen kann (Formular statt
   Prompt) — Verhaltensregeln und Gesprächslogik (§4) bleiben dabei fest in unserer Hand.
2. **Schwierigkeitsstufen** schon in Phase 1 oder erst Phase 2?
3. ~~Stimmung für den SDR sichtbar?~~ **Entschieden (2026-10-12):** schaltbar. Live-Anzeige von
   Offenheit/Geduld/Meilensteinen ist ein Gamification-Feature, das Nutzer bzw. Admin ein- und
   ausschalten; sinngemäß ein Schwierigkeitsgrad (mit Anzeige = leichter). Folgen: Schalter gehört
   zu den Szenario-Einstellungen; Admin-Schalter setzt Rollen/Login voraus. Zu klären: Sehen
   Admins/Manager die Werte einzelner SDRs? Das berührt die FAQ-Zusage „kein
   Beurteilungsinstrument“ — Vorschlag: Anzeige nur für den übenden SDR selbst.
4. ~~Wie streng zählt „aufgedeckt“?~~ **Richtung entschieden (2026-10-12):** Ein eigener
   **Reasoning-Agent** ordnet die SDR-Beiträge fortlaufend ein und gibt das Ergebnis an das
   Sprach-LLM zurück (= der Protokollant aus §4.2, mit Reasoning-Modell statt einfacher
   Klassifikation). Randbedingung: Reasoning-Modelle brauchen Sekunden, deshalb nur asynchron
   (wirkt ab dem nächsten Turn, ggf. übernächsten), nie vor der Antwort — sonst ist das
   Latenzbudget weg. Vorschlag zur Aufteilung: Phase 1 einfacher Protokollant (Klassifikation,
   `nano`/`mini`), der Scoring und Tore trägt; Phase 2 Reasoning-Agent als Ersatz, gemessen an
   denselben Testdialogen (§4.8).
5. **Stimmen:** zwei der vier Personas sind weiblich; die Blind-A/B-Bewertung (Muss-Kriterium 2)
   prüft bisher nur männliche Stimmen.

## 6. Nächste Schritte

1. Entscheidungen aus §5.
2. Markus Brandt vollständig im Gerüst beschreiben (Schmerzpunkte mit Stufen, Ereignis-
   gewichte, Meilensteine, Tore) — erst Design, kein Code.
3. Protokollanten-Ereignisliste und Testdialoge (§4.8) entwerfen.
4. Rollentreue-Test (T3) je Persona erweitern: Werden verdeckte Schmerzpunkte nur auf
   passende Fragen preisgegeben? Widerspricht sich die Persona bei harten Fakten? Hält das
   Erfolgsziel (gibt sie bei schwachem SDR keinen Termin)?
