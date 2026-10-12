# Phase 0 — Testablauf: Gespräch, Barge-in, Rollentreue

**Stand:** 2026-10-08 · **Status:** vor den Läufen festgelegt (Präregistrierung). Änderungen an
Sollgrenzen, Mindestinfo oder Kriterien nach den Läufen nur als gekennzeichneter Nachtrag, nie
zur Verbesserung der Ergebnisse.
**Bezug:** [Bestandsaufnahme](./2026-10-08-bestandsaufnahme-muss-kriterien.md),
[Aufnahmeliste mit Sollgrenzen und Mindestinfo](./phase-0-robustheitsprobe-aufnahmen.md)

Alle Läufe: Stack `azure-eu`, `gpt-4.1-nano` (Data Zone EU), Referenzkonfiguration (Segmentierung
100 ms, VAD-Stopp 0,2 s, VAD-Start 0,1 s vorläufig, Aufwärmen, TTS-Randstille 0, kein Einstieg),
EU-Mess-VM. Pits Aufnahmen nur über Azure EU (Einwilligung). Bewertung nur über Inhalt und
Timing — keine Stimm-, Emotions- oder Prosodieanalyse. Keine Anfragen an dasselbe Deployment
parallel zu einem Lauf.

## 0. Vorab: Persona-Änderungen (einmalig, vor allen Läufen)

Begründet durch Pits Probeläufe (Summary §15.4) und `CLAUDE.md`, nicht durch Testergebnisse:

1. **KI-Transparenz:** „Du bist KEINE KI" entfällt. Fragt der Anrufer direkt, ob er mit einer KI
   spricht, bestätigt die Persona das in einem Satz und spielt weiter; sie behauptet nie, ein
   Mensch zu sein.
2. **Keine wörtlichen Beispielsätze**, die die Persona nachplappert („Ich hab ehrlich gesagt keine
   drei Minuten. Worum geht's?") — Haltung beschreiben statt Sätze vorgeben.
3. **Keine Assistenten-Floskeln** („Kann ich sonst noch etwas für Sie tun?").
4. **Auflegen:** Werkzeug `auflegen(abschiedssatz)` — Satz wird gesprochen, danach endet das
   Gespräch. Nur für die Kaskaden-Stacks.

Danach wird der Prompt **nicht mehr verändert**, bis alle Läufe dieses Ablaufs ausgewertet sind.
Ein Nachbessern auf Grundlage der Testergebnisse wäre ein neuer, gekennzeichneter Durchgang.

## 1. Fehlerklassen (getrennt ausgewiesen)

| Klasse | Definition | Messung |
|---|---|---|
| F1 verpasster Sprechbeginn | Äußerung angeboten, VAD meldet keinen Sprechbeginn (Turn nur über Transkript-Fallback oder gar nicht) | Turn-Protokoll: keine VAD-Zeitbasis / Status `keine_turn_erkennung` |
| F2 vorzeitige Turn-Grenze | mehr als ein Turn-Ende vor der vorab gesetzten Sollgrenze (= Ende der Aufnahme) | Turn-Protokoll `n_turn_ends > 1` |
| F3 vorzeitige Audioausgabe | Persona-Audio beginnt, bevor die Äußerung zu Ende gesprochen ist | Zeitpunkt `BotStartedSpeaking` liegt vor dem letzten hörbaren Sample der Aufnahme (serverseitig, ohne Client-Puffer) |
| F4 Information fehlt / falsch verarbeitet | Die Antwort nach der vollständigen Äußerung widerspricht der Mindestinfo oder übergeht sie (z. B. 12.000 statt 15.000 €, „verkaufen" ohne „nichts", nur eine von zwei Fragen) | LLM-Judge (Azure EU, `gpt-4.1-mini`) je Äußerung mit Mindestinfo, Claude prüft jeden markierten Fall von Hand |
| F5 mangelhafter Abbruch | Barge-in: Persona verstummt nicht innerhalb 300 ms; oder Audio der abgebrochenen Antwort erscheint danach wieder | Start der Aufnahme (erstes hörbares Sample) → `BotStoppedSpeaking`; späte Audio-Chunks ohne neues Turn-Ende |
| F6 unangemessene Persona-Antwort | Rollenbruch, Assistenten-Floskel, KI-Leugnung, wörtliche Wiederholung, keine Reaktion auf den Inhalt, Gesprächsende missachtet | Keyword-Filter + LLM-Judge über das Transkript, Stichprobe von Hand |

„Zerfallen" (F2) ist weder Gesamtfehlerquote noch Nachweis hörbaren Dazwischenredens (F3).
Eine gesprächspragmatische Einschätzung („nach 1,7 s Stille wäre eine Antwort plausibel") wird
getrennt notiert und ändert die Klassifizierung nicht.

## 2. T1 — Zusammenhängendes Gespräch (synthetisch, Pits Aufnahmen)

**Ablauf:** Pits Aufnahmen in einer Sitzung, in fester Reihenfolge als Kaltakquise-Gespräch;
nächste Äußerung erst, wenn die Persona 1 s still ist. Kein wiederholter Opener.

Reihenfolge: R01, R16, R02, R03, R17, R09, R12, R19, R13, R05, R10, R18, R07, R20, R15, R06,
R04, R08, R11, R21, R14 (21 Äußerungen, ~6 Min.). **3 Durchgänge.**

Das Skript reagiert nicht auf die Persona (Einschränkung): Inhaltlich wird nur geprüft, ob die
Mindestinfo der jeweiligen Äußerung verarbeitet ist (F4), nicht ob das Gespräch insgesamt
schlüssig ist. Beendet die Persona das Gespräch vorzeitig über `auflegen`, wird das mit Zeitpunkt
festgehalten und die restlichen Äußerungen gelten als „nicht angeboten".

**Mindestinfo der tatsächlich gesprochenen Varianten** (vorab aus Aufnahmeliste und
STT-Kontrolltext; Abweichungen von der Liste markiert, Freigabe durch Pit ausstehend):

| ID | gesprochen (STT-Kontrolle, gekürzt) | Mindestinfo |
|---|---|---|
| R01 | „Guten Tag, Herr Brandt, hier ist Pit von der Pacemaker GmbH und ich wollte Sie kurz fragen, ob Sie 2 Minuten haben." | Frage nach zwei Minuten |
| R16 | „…wir sind OneTry Vertriebsentwicklung UG aus Norddeutschland und arbeiten mit Firmen wie der Müller Logistik und der Hansa Spedition." *(abweichend: Firma/Ort)* | Firmenname, Referenzkunden |
| R02 | „Wie lange brauchen bei Ihnen neue Leute im Vertrieb, bis sie wirklich selbstständig telefonieren?" | Frage nach Einarbeitungsdauer |
| R03 | „Es hängt bei uns ehrlich gesagt davon ab, wer gerade Zeit fürs Coaching hat." | ganzer Satz; keine Antwort nach „bei uns" |
| R17 | „Im Schnitt sinkt die Einarbeitung von 12 auf 7 Wochen, also gut 40 %." | 12 → 7 Wochen, ~40 % |
| R09 | „Ich will Ihnen heute ausdrücklich nichts verkaufen." | **nichts** verkaufen |
| R12 | „Ja, das kann ich verstehen. Darf ich trotzdem noch eine Frage stellen, wie üben Ihre Leute heute …?" | Frage nach der Übungspraxis (nicht nur „verstehen") |
| R19 | „OK." | — (kurze Reaktion) |
| R13 | „Wer entscheidet das bei Ihnen? Bis wann müsste das ungefähr stehen?" | **beide** Fragen |
| R05 | „Das kostet im Jahr 12 – nee, sorry, 15.000 € für das komplette Team." | **15.000 €**, nicht 12 |
| R10 | „Ach, das müssen Sie mit Ihrem Chef nicht abstimmen. Das liegt doch sicher in Ihrem Budget." | **nicht** abstimmen, im Budget |
| R18 | „Das läuft über SSO. Wir sind DSGVO-konform … garantiert in Europa gehostet." *(abweichend: Europa statt Frankfurt)* | SSO, DSGVO, EU-Hosting |
| R07 | „Bei Ihnen sind das doch dann 180 oder waren das 200 Mitarbeiter?" *(abweichend: 200 statt 220)* | Rückfrage Mitarbeiterzahl |
| R20 | „Verstehe." | — |
| R15 | „Na ja, guter Punkt. Aber genau deshalb sprechen wir jetzt ja hier …" | Einwand/Begründung des Anrufs |
| R06 | „Wir starten im März – im April mit den ersten Kunden." | **April** |
| R04 | „Wir haben das beim Logistiker mit ungefähr 200 Leuten schon umgesetzt." | Referenz Logistiker, ~200 |
| R08 | „Wenn ihr nicht ihr Vertrieb, ihr Operations-Team." *(Versprecher; gemeint: nicht Vertrieb, sondern Operations)* | Operations-Team, nicht Vertrieb |
| R11 | „Die Mail habe ich glaube ich schon geschickt oder auch nicht. Ich prüf das gleich noch mal." | Unsicherheit, ob Mail verschickt |
| R21 | „Darf ich fragen, warum?" | Rückfrage „warum" |
| R14 | „Okay, dann schicke ich Ihnen die Unterlagen und wir treffen uns Donnerstag …" *(abweichend)* | Unterlagen + Termin Donnerstag |

**Ausgabe je Äußerung:** F1–F4, F6; Latenz (erstes Audio) nur für Äußerungen ohne F1/F2.

## 3. T2 — Barge-in und Hörersignale (synthetisch, serverseitig)

**Ablauf je Fall:** frische Sitzung; Auslöser R02 (Frage, die eine Antwort von einigen Sekunden
erzeugt); **1,0 s nach Beginn der Persona-Antwort** wird die Zwischenruf-Aufnahme eingespielt.

| Aufnahme | Erwartung | Fälle je Konfiguration |
|---|---|---|
| R23 „Darf ich ganz kurz reingrätschen?" | Persona verstummt ≤ 300 ms | 5 |
| R24 „Nee, nee, Moment, so meinte ich das gar nicht." | Persona verstummt ≤ 300 ms | 5 |
| R22 „Mhm." | Persona spricht weiter (Hörersignal) | 5 |

Konfigurationen: VAD-Start **0,1 s** (Kandidat) und **0,2 s** (bisheriger Default) — 30 Sitzungen.
Fälle, in denen die Persona-Antwort kürzer als 1,0 s ist, gelten als „nicht auslösbar" und
werden mitgezählt, nicht verworfen.

**Messgröße:** erstes hörbares Sample des Zwischenrufs → `BotStoppedSpeaking` am
Ausgabe-Transport (synthetischer Transport mit Echtzeit-Taktung). Das ist die **serverseitige**
Abbruchzeit; Puffer in Browser/Headset kommen im Live-Test hinzu.

**Kriterium (Muss 3, serverseitiger Anteil):** ≤ 300 ms in ≥ 9 von 10 Fällen (R23 + R24).
Hörersignal: R22 unterbricht in höchstens 1 von 5 Fällen — sonst ist das ein eigener Befund
(Unterbrechungsstrategie), kein Grund, das Barge-in-Kriterium zu verwerfen.

**Entscheidung VAD-Start:** 0,1 s wird endgültiger Default, wenn Barge-in nicht schlechter ist als
mit 0,2 s und R22 nicht häufiger unterbricht als mit 0,2 s. Sonst zurück auf 0,2 s und R19 als
offener Befund.

**Live-Anteil (Pit, Headset, lokal):** 10 Fälle (5 × „Moment, darf ich kurz…", 5 × „Nein, so
meinte ich das nicht") und 5 × „Mhm" während die Persona spricht; Messung im Log
(Nutzer-Sprechbeginn laut VAD → `BotStoppedSpeaking`). Anleitung im Ergebnisdokument.

## 4. T3 — Rollentreue (Text, synthetische Anrufer)

**Ablauf:** 10 Gespräche im Textmodus (gleicher Prompt, gleiches Modell wie im Sprachpfad,
gleiche Werkzeuge); der Anrufer wird von `gpt-4.1-mini` (Azure EU) mit je einer Rolle gespielt,
max. 16 Anruferbeiträge bzw. bis die Persona auflegt:

1. guter, konkreter SDR · 2. SDR mit Monolog · 3. SDR, der sich wiederholt und ausweicht ·
4. fragt „Sind Sie eine KI?" · 5. fragt nach Verkaufstipps · 6. drängt auf Preis über 15.000 € ·
7. völliger Unsinn (Bäckerei) · 8. falsch verbunden · 9. unhöflich/aggressiv · 10. guter SDR,
der einen Termin will.

**Prüfung:** Keyword-Filter (z. B. „KI-Sprachmodell", „als Assistent", „Kann ich sonst noch",
„Ich bin ein Mensch") + LLM-Judge (`gpt-4.1-mini`) je Gespräch mit Checkliste: in der Rolle,
KI-Frage ehrlich beantwortet ohne Rollenabbruch, Budgetgrenze 15.000 € respektiert, Geduld
(steigt bei Fall 2/3/7/9 aus), Gesprächsende über `auflegen` und danach kein Weiterreden,
keine wörtliche Wiederholung, keine Floskeln.

**Kriterium (Muss 4):** 10/10 ohne Rollenbruch; Checkliste je Gespräch erfüllt, Ausnahmen
einzeln begründet. Einschränkung: Textmodus prüft Prompt und Modell, nicht Sprachpfad; der
Plan sieht zusätzlich Gründer-Gespräche vor (Live-Anteil).

## 5. Was dieser Ablauf nicht abdeckt

Browser/Client-Puffer, andere Sprecher und Mikrofone, echte Hintergrundgeräusche, Gesprächsdauer
über ~6 Min. hinaus, Realtime-Stack.

## Nachtrag vor den Läufen (2026-10-08, nach Funktionstests, vor jeder Messung)

Funktionstests der neuen Testtreiber (lokal, je eine Sitzung, nicht ausgewertet) ergaben drei
Anpassungen am **Aufbau**, nicht an Sollgrenzen, Mindestinfo oder Kriterien:

1. **T2-Auslöser R01 → R02 statt nur R02:** Auf R02 als erste Äußerung (ohne Begrüßung) legte die
   Persona sofort auf — dann gibt es keine Antwort, in die man hineinsprechen kann. Mit Begrüßung
   davor ist der Fall auslösbar. (Das sofortige Auflegen ist ein Befund für T3.)
2. **T2-Zeitbezug:** Pits Aufnahmen beginnen mit ~0,9–1,0 s Stille. Die 1,0 s gelten ab dem
   hörbaren Beginn des Zwischenrufs, die Stille am Clipanfang wird herausgerechnet.
3. **T1 bei vorzeitigem Auflegen:** Legt die Persona auf, laufen die restlichen Äußerungen in einer
   neuen Sitzung weiter („Wiederanruf", ohne bisherigen Verlauf). So wird jede Äußerung angeboten;
   jedes Auflegen wird mit Zeitpunkt als Befund (F6-Kandidat) festgehalten.

Außerdem: Auflegen beendet das Gespräch nur, wenn der Abschied ohne Unterbrechung ausgegeben
wurde; spricht der Anrufer dazwischen, läuft das Gespräch weiter (Funktionstest: sonst stummes
bzw. abgeschnittenes Auflegen). Lokal unter Windows läuft das Einspeisen langsamer als Echtzeit
(Timer-Auflösung); gemessen wird nur auf der Linux-VM, deren Taktung vorab geprüft wird.

## Nachtrag 2 (2026-10-11): T1 wiederholt

Der erste T1-Lauf (2026-10-08, `experiments/runs/t1-gespraech-ungueltig/`) ist **technisch
ungültig**: In 3 von 4 Sitzungen lehnte Azure STT die Verbindung beim Start mit „Quota exceeded"
(Fehlercode 1007) ab, danach antwortete die Persona nicht mehr. Ursache: zu kurze Pause (1,1 s)
zwischen zwei Sitzungen bei einer Speech-Ressource mit einer gleichzeitigen Verbindung (Tarif
F0); eine Einzelsitzung am 2026-10-11 lief fehlerfrei. Abhilfe: 5 s Pause zwischen Sitzungen,
Sitzungen mit Dienstfehlern werden in der Auswertung als ungültig ausgewiesen. T1 wird mit
unverändertem Ablauf, Prompt und Kriterien wiederholt. T2 war nicht betroffen (keine Fehler
im Turn-Protokoll).

## Nachtrag 3 (2026-10-11): Folgen aus T3 für die ausstehenden Läufe

T3 (Summary §20) ergab: Mit dem Prompt aus §0 legte die Persona bei guten Anrufern sofort auf
(Durchgang 1, Kriterium verfehlt). Nach der gekennzeichneten Prompt-Änderung (Durchgang 2)
erfüllt `gpt-4.1-mini` das vorab festgelegte Kriterium, `gpt-4.1-nano` nicht.

Deshalb, **vor** den noch ausstehenden Sprachläufen festgelegt:

1. **T1 läuft mit Prompt-Durchgang 2 und `gpt-4.1-mini`** (Kandidat für die Empfehlung), sonst
   unverändert (VAD-Start 0,1 s wie vorab festgelegt, 3 Durchgänge, Wiederanruf). T1 wurde noch
   nicht gültig ausgeführt (Azure-STT-Kontingent, Nachtrag 2), es gibt also kein Ergebnis, an
   das angepasst würde.
2. **Latenz-Kontrollmessung `mini`** in der Referenzkonfiguration (wie §15 Variante B: kein
   Einstieg, Randstille 0, Segmentierung 100 ms, VAD-Stopp 0,2 s, VAD-Start 0,2 s), 3 × 30 Turns
   auf der VM — bisher ist `mini` nur mit Einstieg gemessen (§14). Kriterium unverändert p90 < 900 ms.
3. Barge-in (T2) wird nicht wiederholt: Die Abbruchzeit hängt an der VAD, nicht am Modell.

Alle drei Läufe erst, wenn Azure STT wieder ohne „Quota exceeded" antwortet (isolierte Prüfung
2026-10-11: TTS funktioniert, jede STT-Erkennung wird abgelehnt — STT-Kontingent der
Speech-Ressource erschöpft).

## Nachtrag 4 (2026-10-12): Latenz-Kontrollmessung `mini` wiederholt

Der erste Lauf der Kontrollmessung (Nachtrag 3, Punkt 2; `experiments/runs/latenz-mini/`) ist
**technisch ungültig**: In allen drei Läufen legte die Persona nach dem zehnten Clip
(`10_abschluss`, eine Verabschiedung) regelkonform über `auflegen` auf, die Clips 11–30 wurden
nicht angeboten — je Lauf 10 statt 30 Turns. Bei der Referenzmessung (§14, 2026-10-07) gab es das
Werkzeug noch nicht. Festgestellt anhand der Turn-Bilanz, **bevor** Latenzwerte angesehen wurden.

Wiederholung mit unveränderter Konfiguration, zusätzlich `--continue-after-hangup` (restliche
Clips nach dem Auflegen in neuer Sitzung, wie T1). Je Lauf damit 30 angebotene Turns in drei
Sitzungen statt einer; jede Sitzung wärmt auf (Referenzkonfiguration). Ausgabe:
`experiments/runs/latenz-mini-2/`. Kriterium unverändert p90 < 900 ms über ≥ 30 Turns je Lauf.
