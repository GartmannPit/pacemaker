# Phase 0 — Robustheitsprobe: Aufnahmeliste und Anleitung

**Stand:** 2026-10-07 · **Sprecher:** Pit · **Bezug:** [überarbeiteter Plan](./2026-10-07-pruefung-kritik-naechste-schritte.md) §4 Schritt C

## Zweck

Die bisherigen Test-Clips sind synthetisch (Azure-TTS) und bewusst „sauber": Pausen innerhalb
eines Clips liegen unter 200 ms. Das macht Messungen reproduzierbar, verdeckt aber genau die
schwierigen Fälle des Sprecherwechsels. Diese Probe prüft mit echter Sprache:

- Antwortet die Persona **zu früh** (mitten in einer Denkpause)?
- Kommen **alle Satzteile** an (spätes „nicht", korrigierte Zahlen, zweite Frage)?
- Wartet die Persona **unnötig lange**?
- Hält der 100-ms-Default der STT-Segmentierung (gegenüber 200/300 ms) echter Sprache stand?

Ausgewertet werden **nur Inhalt und Timing** — keine Stimmlage, keine Emotion, keine Prosodie
(`CLAUDE.md`). Es ist eine **erste** Robustheitsprobe: eine Stimme, ein Mikrofon. Sie deckt weder
deutsche Sprachvariation noch verschiedene Geräte ab.

## Einwilligung (vor der Aufnahme unterschreiben bzw. per Mail bestätigen)

> Ich, Pit Gartmann, nehme die unten aufgeführten Äußerungen mit meiner eigenen Stimme auf und
> willige ein, dass sie für technische Tests des Pacemaker-Prototyps (Phase 0) verwendet werden.
>
> - **Verarbeitung:** Die Aufnahmen werden im Testlauf an **Microsoft Azure AI Speech**
>   (Region Germany West Central, Deutschland) zur Spracherkennung übertragen. Die erkannten
>   Texte gehen an **Azure OpenAI** (Data Zone EU). Andere Dienste werden mit diesen Aufnahmen
>   nicht verwendet — ausdrücklich **nicht** Stack A (US-Anbieter).
> - **Speicherort:** lokal auf dem Entwicklungsrechner und auf der EU-Mess-VM (Hetzner,
>   Deutschland) im Ordner `agent/fixtures/robust/`. **Nicht** im Git-Repository (Ordner ist
>   ausgeschlossen), nicht in Cloud-Speichern.
> - **Auswertung:** nur Transkript-Inhalt und Zeitpunkte. Keine Analyse von Stimmlage,
>   Emotion oder Stress.
> - **Löschung:** spätestens mit Abschluss von Phase 0 auf allen Geräten; vorher jederzeit auf
>   Wunsch.
>
> Datum, Unterschrift: Pit Gartmann, 08.10.2026

Das ist eine praktische Klarstellung, keine rechtliche Bewertung.

## Aufnahme

- **Umgebung:** ruhiger Raum, gleiches Headset/Mikrofon wie später bei den Barge-in-Tests.
- **Format:** WAV, mono, möglichst 16 kHz / 16 Bit (andere Raten rechne ich um).
  Werkzeug z. B. Audacity oder die Windows-Sprachaufzeichnung.
- **Je Äußerung eine Datei**, Dateiname = ID, z. B. `R07.wav`.
- Vor und nach jeder Äußerung ca. **1 Sekunde Stille** lassen, nichts wegschneiden.
- **Regieanweisungen** in eckigen Klammern umsetzen, nicht vorlesen: `[Pause ~0,6 s]` heißt
  kurz innehalten, ungefähr so lange. Exaktheit ist nicht nötig — die tatsächlichen Pausen
  messe ich aus der Aufnahme.
- Natürlich sprechen, wie im echten Kaltakquise-Gespräch. Versprecher sind willkommen.
- Dauer insgesamt: ca. 30–45 Minuten.

## Teil 1 — Gesteuerte Äußerungen

Spalten: **Grenze** = wo der Turn enden soll (die Persona soll erst danach antworten).
**Mindestinfo** = was in der Antwort der Persona berücksichtigt sein muss, damit die Äußerung als
„vollständig verstanden" gilt.

### Denkpausen innerhalb eines Satzes

| ID | Text mit Regie | Grenze | Mindestinfo |
|---|---|---|---|
| R01 | Guten Tag Herr Brandt, hier ist Pit von der Pacemaker GmbH [Pause ~0,6 s] und ich wollte Sie kurz fragen, ob Sie zwei Minuten haben. | nach „haben" | Frage nach zwei Minuten |
| R02 | Wie lange brauchen bei Ihnen [Pause ~0,8 s] neue Leute im Vertrieb, bis sie wirklich selbstständig telefonieren? | nach „telefonieren" | Frage nach Einarbeitungsdauer |
| R03 | Das hängt bei uns [Pause ~1,0 s] ehrlich gesagt davon ab, wer gerade Zeit fürs Coaching hat. | nach „hat" | ganzer Satz, keine Antwort nach „bei uns" |
| R04 | Wir haben das bei einem Logistiker [Pause ~0,5 s] ähm [Pause ~0,5 s] mit ungefähr zweihundert Leuten schon umgesetzt. | nach „umgesetzt" | Referenz Logistiker, ~200 Mitarbeiter |

### Selbstkorrekturen und korrigierte Zahlen

| ID | Text mit Regie | Grenze | Mindestinfo |
|---|---|---|---|
| R05 | Das kostet im Jahr zwölf [Pause ~0,4 s] nein, Entschuldigung, fünfzehntausend Euro für das ganze Team. | nach „Team" | **15.000 €**, nicht 12.000 |
| R06 | Wir starten im März [Pause ~0,3 s] äh, im April mit den ersten Kunden. | nach „Kunden" | **April** |
| R07 | Bei Ihnen sind das doch etwa hundertachtzig [Pause ~0,3 s] oder waren es zweihundertzwanzig Mitarbeiter? | nach „Mitarbeiter" | Rückfrage zur Mitarbeiterzahl, beide Zahlen |
| R08 | Ich meinte nicht den Vertrieb [Pause ~0,4 s] sondern Ihr Operations-Team. | nach „Operations-Team" | Operations-Team, nicht Vertrieb |

### Spätes „nicht" und Bedeutungsumkehr am Satzende

| ID | Text mit Regie | Grenze | Mindestinfo |
|---|---|---|---|
| R09 | Ich will Ihnen heute ausdrücklich [Pause ~0,6 s] nichts verkaufen. | nach „verkaufen" | **nichts** verkaufen |
| R10 | Das müssen Sie mit Ihrem Chef [Pause ~0,5 s] nicht abstimmen, das liegt in Ihrem Budget. | nach „Budget" | **nicht** abstimmen, im Budget |
| R11 | Die Mail habe ich Ihnen schon geschickt [Pause ~0,7 s] oder doch noch nicht, das prüfe ich gleich. | nach „gleich" | Unsicherheit, ob Mail verschickt |

### Mehrere Sätze oder Fragen in einem Turn

| ID | Text mit Regie | Grenze | Mindestinfo |
|---|---|---|---|
| R12 | Verstehe ich. [Pause ~0,7 s] Darf ich trotzdem eine Frage stellen? [Pause ~0,5 s] Wie üben Ihre Leute heute Preisgespräche? | nach „Preisgespräche" | Frage nach Preisgesprächen (nicht nur „Verstehe ich") |
| R13 | Wer entscheidet das bei Ihnen? [Pause ~0,6 s] Und bis wann müsste das stehen? | nach „stehen" | **beide** Fragen |
| R14 | Okay. [Pause ~0,8 s] Dann schicke ich Ihnen die Unterlagen. [Pause ~0,5 s] Passt Ihnen Donnerstag für ein kurzes Telefonat? | nach „Telefonat" | Unterlagen + Terminvorschlag Donnerstag |
| R15 | Das ist ein guter Punkt. [Pause ~1,0 s] Aber genau deshalb rufe ich an, weil Ihr jetziges Tool das nicht abdeckt. | nach „abdeckt" | Einwand gegen jetziges Tool |

### Zahlen, Namen, Fachbegriffe

| ID | Text mit Regie | Grenze | Mindestinfo |
|---|---|---|---|
| R16 | Wir sind die Pacemaker GmbH aus Köln und arbeiten mit Firmen wie der Müller Logistik und der Hansa Spedition. | nach „Spedition" | Firmenname, Referenzkunden |
| R17 | Die Einarbeitung sinkt im Schnitt von zwölf auf sieben Wochen, das sind gut vierzig Prozent. | nach „Prozent" | 12 → 7 Wochen, ~40 % |
| R18 | Das läuft über SSO, DSGVO-konform, gehostet in Frankfurt. | nach „Frankfurt" | SSO, DSGVO, Frankfurt |

### Kurze Äußerungen (sollen sofort beantwortet werden)

| ID | Text mit Regie | Grenze | Mindestinfo |
|---|---|---|---|
| R19 | Okay. | sofort | — (kurze Reaktion erwartet) |
| R20 | Verstehe. | sofort | — |
| R21 | Darf ich fragen, warum? | sofort | Rückfrage „warum" |

### Zwischenrufe während die Persona spricht (für Barge-in, Schritt B)

Diese werden später **live** eingesprochen, während die Persona redet, nicht als Datei
abgespielt. Hier nur zur Vorbereitung:

| ID | Text | Erwartung |
|---|---|---|
| R22 | Mhm. | Persona spricht weiter (Hörersignal, keine Unterbrechung) |
| R23 | Moment, darf ich kurz unterbrechen? | Persona verstummt (≤ 300 ms) und reagiert |
| R24 | Nein, nein, das meinte ich nicht. | Persona verstummt und reagiert auf die Korrektur |

## Teil 2 — Spontane Äußerungen

Ohne Vorlage frei formulieren, wie im echten Gespräch. Je eine Aufnahme, Dateiname `S01.wav` …
Danach kurz den gemeinten Inhalt in eine Textdatei `S01.txt` schreiben (Referenz für die
Auswertung).

| ID | Situation |
|---|---|
| S01 | Erklären Sie in zwei, drei Sätzen, was Pacemaker macht — so, wie Sie es am Telefon sagen würden. |
| S02 | Reagieren Sie auf „Schicken Sie mir einfach was per Mail." und versuchen Sie, trotzdem einen Termin zu bekommen. |
| S03 | Reagieren Sie auf „Das ist uns zu teuer." mit einer Rückfrage. |
| S04 | Fassen Sie das Gespräch zum Schluss zusammen und schlagen Sie den nächsten Schritt vor. |
| S05 | Eine Frage, bei der Sie selbst nach Worten suchen müssen (z. B. nach dem ROI für ein Team mit 15 Leuten). |

## Was danach passiert

1. Ich messe pro Aufnahme die tatsächlichen Pausen und lege sie mit Referenztext, Grenze und
   Mindestinfo als Fixture ab (`agent/fixtures/robust/`, gitignored).
2. Abspielen über den Synthetic Caller auf der EU-Mess-VM, je einzeln in frischer Sitzung,
   mit STT-Segmentierung 100 / 200 / 300 ms.
3. Auswertung je Aufnahme: vorzeitige Antwort, fehlende Mindestinfo, unnötige Wartezeit; dazu
   die Latenzwerte aus dem Turn-Protokoll.
4. Ergebnis als Kurve „Latenz gegen Fehler" je Segmentierungswert; danach Entscheidung über den
   Default.
