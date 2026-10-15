# Experiment: Spekulativer Start zusammen mit TTS-Vorverbindung

**Stand:** 2026-10-14 · **Status:** vor den Läufen festgelegt (Präregistrierung). Änderungen an
Hypothese, Kriterien oder Auswertung nach den Läufen nur als gekennzeichneter Nachtrag.
**Bezug:** [Spekulativer Start](./2026-10-12-spekulativer-start.md) (Summary §23),
[TTS-Vorverbindung](./2026-10-14-tts-vorverbindung.md) (Summary §26),
[Prüfung der Phase-0-Ergebnisse](./2026-10-14-pruefung-phase-0-ergebnisse.md) Punkt 1 und 3,
[Testablauf Gespräch](./phase-0-testablauf-gespraech.md) (T1, Fehlerklassen F1–F6).

## 1. Ausgangslage und Fragen

Beide Hebel wurden bisher nur einzeln gemessen: Spekulation −126 ms p50 / −64 ms p90 (ohne
Vorverbindung), Vorverbindung −95 / −107 ms (ohne Spekulation). Die Kombination ist geschätzt
(~1,0 / ~1,27 s), und Einsparungen lassen sich bei Quantilen nicht addieren (Prüfung, Punkt 3).
Der Versuch beantwortet drei Fragen:

1. **Latenz:** Was bringt die Spekulation zusätzlich, wenn die Vorverbindung schon an ist?
2. **Vorbereitungszeit:** Wann liegt das Transkript erstmals ausreichend vollständig vor, und wie
   viel Zeit bleibt danach bis zur Audiofreigabe (reguläres Turn-Ende)? Davon hängt ab, wie viel
   die Spekulation überhaupt gewinnen *kann*.
3. **Nebenwirkungen:** Spricht die Persona häufiger vorzeitig hinein, und werden
   Selbstkorrekturen („zwölf – nein, fünfzehn“) weiterhin richtig verarbeitet?

## 2. Bedingungen

Beide auf `spekulation-kombi` (= `main` 6cf5636 + Spekulation 8f15769 + Messpunkte), Vorverbindung
in beiden an (Default), `azure-eu`/`gpt-4.1-mini`, EU-Mess-VM.

| Bedingung | Schalter | Wirkung |
|---|---|---|
| **A Kontrolle** | `PACEMAKER_SPECULATION=beobachten` | Regelpfad wie `main`; Trigger und Resolver laufen mit und protokollieren nur (keine Starts, keine Schleuse) |
| **B Kombination** | `PACEMAKER_SPECULATION=1` | spekulativer Start aktiv |

Damit läuft die zweite Silero-VAD in beiden Bedingungen; A und B unterscheiden sich nur durch die
Spekulation selbst.

## 3. Messpunkte (neu, Spekulationsprotokoll `spekulation/<run_id>.jsonl`, Unix-Zeit)

- `transkript`: jedes Zwischen-/Finaltranskript mit dem bisherigen Gesamttext des Turns und dem
  Zustand der schnellen VAD (`ruhig`).
- `pause` / `sprache`: Beginn einer Pause (schnelle VAD, 0,08 s) bzw. erneuter Sprache.
- `turn_ende`: reguläres Turn-Ende mit dem Turn-Text (der Text, auf den die Persona antwortet).
- nur B: `start`, `verworfen`, `bestaetigt`, `freigabe` (Audio bei Freigabe schon zurückgehalten?
  wie lange?), `audio_nach_freigabe` (Wartezeit, wenn noch kein Audio da war).

**Abgeleitet je beantworteter Äußerung** (Referenz Sprechende = `speech_end_clip` aus dem
Turn-Protokoll):

| Größe | Definition |
|---|---|
| Text vollständig | erstes `transkript`, dessen Gesamttext normalisiert dem Turn-Text gleicht (streng, wie die Bestätigung); zusätzlich locker ohne Leerzeichen, weil Zwischentranskripte z. B. „gmb h“ statt „GmbH“ liefern (Rauchtest) |
| frühester Start | erstes Ereignis (`transkript` oder `pause`) mit vollständigem Text **und** ruhiger schneller VAD — der früheste Zeitpunkt, zu dem eine Spekulation den richtigen Text hätte |
| verfügbare Vorbereitungszeit | `turn_ende` − frühester Start (obere Grenze des Gewinns) |
| genutzte Vorbereitungszeit (B) | Freigabe − Start der bestätigten Spekulation; Anteil „Audio bei Freigabe bereit“ |

Nur Äußerungen mit Status `beantwortet` und genau einem Turn-Ende. Auswertung:
`metrics/speculation_eval.py` (vor den Läufen geschrieben), F2/F3 aus `metrics/conversation.py`,
F4 aus `tests/judge.py`.

## 4. Messreihen (abwechselnd A, B, A, B, A, B je Reihe)

| Reihe | Material | Umfang je Bedingung | Zweck |
|---|---|---|---|
| **L** Latenz | synthetische Clips `fixtures/audio`, `--turns 30 --continue-after-hangup`, VAD-Start Default 0,2 s | 3 × 30 | Primärkriterium, Vorbereitungszeit |
| **T1** Gespräch | Pits Aufnahmen in T1-Reihenfolge, `--continue-after-hangup`, VAD-Start 0,1 s (wie §21.2) | 3 × 21 | F2/F3 mit echten Denkpausen, Korrekturen R05/R06/R08, Vorbereitungszeit |
| **K** Korrekturen | neue Clips `fixtures/korrektur` (`tests/generate_correction_fixtures.py`), `--continue-after-hangup`, VAD-Start Default | 3 × 9 | gezielte Selbstkorrekturen |

**Korrektur-Clips** (vorab erzeugt; Pause = eingefügte Pause, gemessen = längste Stille im Clip):

| Clip | Inhalt | Pause soll / gemessen |
|---|---|---|
| K00 | Einstieg (keine Korrektur, nicht gewertet) | – |
| K01 | „Bei uns im Team sind aktuell zwölf – nein Moment, fünfzehn Leute.“ | 300 / 480 ms |
| K02 | „Der Pilot würde bei Ihnen im Mai starten – also eher im Juni.“ | 150 / 250 ms |
| K03 | „Wir haben das bei einem Maschinenbauer umgesetzt – Entschuldigung, bei einem Logistiker.“ | 500 / 570 ms |
| K04 | „Die Lizenz kostet achtzig Euro im Monat – pro Nutzer, meine ich.“ | 300 / 380 ms |
| K05 | „Ich könnte Ihnen Dienstag – nein, Mittwoch einen Termin anbieten.“ | 150 / 220 ms |
| K06 | „Das Training dauert zwei Stunden – pro Woche, nicht am Stück.“ | 500 / 600 ms |
| K07 | „Ihr Ansprechpartner bei uns wäre Frau Keller – Verzeihung, Frau Kessler.“ | 300 / 460 ms |
| K08 | „Wir sitzen in Hamburg – also in Hannover meine ich.“ | 500 / 550 ms |

Mindestinfo je Clip (für den Judge): `tests/generate_correction_fixtures.py`, `MINDESTINFO`.

## 5. Hypothesen und Kriterien (vor den Läufen festgelegt)

**Erwartung:** Spekulation bringt mit Vorverbindung etwa denselben Gewinn wie ohne (~100–150 ms
p50), weil sie den Abschnitt *vor* dem Turn-Ende verkürzt und die Vorverbindung den *danach*.
Die verfügbare Vorbereitungszeit liegt in Reihe L bei ~250–350 ms (Turn-Ende-Abschnitt §23), in
T1 höher, aber mit mehr Neustarts.

**Latenz-Auswahl** (nach Prüfung, Punkt 1): alle als `beantwortet` klassifizierten Turns mit
gültigem Audiobeginn, auch Werkzeugabschiede. Die bisherige Auswahl (nur mit LLM-Textdelta) wird
daneben berichtet. Nenner und Bilanz (beantwortet / zerfallen / keine Antwort / Artefakte nach
Auflegen) je Bedingung.

| Kriterium | Grenze |
|---|---|
| **Primär:** E2E erstes Audio p50, Reihe L, B gegenüber A (gepoolt) | Verbesserung ≥ 150 ms (wie §23) |
| Sekundär: E2E p90, Reihe L | berichtet |
| Absolutwerte B, Reihe L | berichtet gegen Ziel p90 < 900 ms |
| Latenz T1 ohne F1/F2 | berichtet |
| Vorbereitungszeit (verfügbar, genutzt, Anteil Audio bereit) | berichtet, je Reihe |
| **Vorzeitiges Hineinsprechen:** F3, Reihen T1 + K gepoolt | B höchstens 2 Fälle mehr als A |
| Persona-Audio ohne vorangehendes reguläres Turn-Ende | **0** |
| **Korrekturen:** F4 bei K01–K08 und R05/R06/R08 (Judge, markierte Fälle von Hand) | B nicht mehr Verletzungen als A |
| Bestätigte Spekulation, deren Text vom regulären Turn-Text abweicht | **0** |
| Neue Fehler: mehr vollständige Antworten als Turn-Enden je Äußerung (doppelte Antwort), Auflegen ohne Bestätigung, `zaun_timeout` | B nicht mehr als A; `zaun_timeout` **0** |
| Verworfene spekulative LLM-Aufrufe je beantwortetem Turn | berichtet (Kosten) |

**Übernahme als Default** (`PACEMAKER_SPECULATION=1`) nur, wenn Primärkriterium, F3-Grenze,
Korrektur-Kriterien und Fehlerfreiheit erfüllt sind. Sonst bleibt die Spekulation abschaltbare
Option; eine abweichende Entscheidung ist Gründerentscheidung und wird als solche vermerkt.

**Gültigkeit:** Reihe ungültig bei Dienstfehlern (Quota, TTS-Abbrüche) in mehr als einer Sitzung;
dann Wiederholung der ganzen Reihe. Keine anderen Anfragen an dieselben Deployments während der
Läufe.

## Nachtrag 1 (2026-10-14): Ergebnis

Läufe 19:35–21:06 UTC auf der VM (`~/pacemaker-kombi`, Stand `901bdc3`), Daten
`experiments/runs/kombi-{l,t1,k}/`, keine Dienstfehler. Auswertung wie festgelegt
(`metrics/speculation_eval.py`, `metrics/conversation.py`, `tests/judge.py`), markierte Fälle von
Hand geprüft. Ausführlich: [Summary §27](../experiments/summaries/2026-10-03-llm-modellvergleich-deployment-typen.md).

| Kriterium | A Kontrolle | B Kombination | Ergebnis |
|---|--:|--:|---|
| **Primär:** erstes Audio p50 / p90, Reihe L, alle beantworteten (n = 81 / 81) | 1076 / 1337 | 1060 / 1340 | **verfehlt** (−16 ms p50, +3 ms p90) |
| dto. nur mit LLM-Text (n = 72 / 72) | 1065 / 1248 | 1044 / 1323 | – |
| verfügbare Vorbereitungszeit p50 / p90, L | 73 / 188 | 68 / 168 | – |
| Audio bei Freigabe bereit (B, L + T1 + K) | – | 0 / 110 | – |
| F3, T1 + K gepoolt | 28 / 90 | 26 / 90 | erfüllt |
| Persona-Audio ohne vorangehendes Turn-Ende | 1 | 2 | erfüllt (alle 3 sind Abschiedssätze nach `auflegen`, Fehlalarm der Prüfung) |
| Korrekturen F4, von Hand bestätigt (K01–K08, R05/R06/R08) | 0 / 32 | 3 / 30 | **verfehlt** |
| abweichend bestätigt / `zaun_timeout` | 0 / 0 | 0 / 0 | erfüllt |
| mehr Antworten als Turn-Enden | 1 | 1 | erfüllt (Abschiedssätze, wie oben) |
| **neu: Persona verstummt** (Turn-Ende, danach ≥ 3 s Stille ohne Persona-Audio) | 0 | 3 Sitzungen (6 Turn-Enden) | **neuer Fehler** |
| verworfene spekulative Aufrufe | – | 1,27 je Turn (L), 2,10 je Turn-Ende (T1), 1,76 (K) | – |

**Entscheidung nach der Regel: nicht übernommen.** Die Spekulation bleibt abschaltbar (Default aus).

**Befund Vorbereitungszeit:** Der vollständige Text liegt erst ~295 ms nach dem Sprechende vor
(Reihe L, p50), das reguläre Turn-Ende folgt ~70 ms später. Zwischentranskripte hinken dem
Gesprochenen hinterher; das letzte Wort kommt meist erst kurz vor oder mit dem Final-Transkript.
Die Spekulation kann deshalb höchstens ~70 ms p50 gewinnen (T1: 48–64 ms; K: 5–14 ms streng,
~100 ms ohne Leerzeichenvergleich), während LLM + TTS ab Start ~700 ms brauchen. Das Audio war in
keinem der 110 bestätigten Fälle bei der Freigabe fertig. Vom Gewinn −126 ms in §23 kann die
Methode damit höchstens ~70 ms erklären; der Rest war Streuung zwischen den Läufen.

**Neuer Fehler „Persona verstummt“ (nur B, Clip K04 in allen drei B-Sitzungen):** Startet die
Spekulation, kurz bevor der reguläre Pfad den Nutzer-Turn beginnt, bricht dessen Unterbrechung den
spekulativen LLM-Lauf ab. Der Spekulationszustand bleibt aber offen, wird beim Turn-Ende
„bestätigt“, die Schleuse öffnet leer, und der reguläre LLM-Aufruf ist verworfen. Folge: keine
Antwort; die nachgeholte Antwort zum Preis kommt erst nach dem nächsten Clip (daher zwei der drei
F4-Fälle bei K05). Behebbar (offene Spekulation bei fremder Unterbrechung verwerfen), nach diesem
Ergebnis aber ohne Nutzen.

**Weitere Abweichungen:**
- Die Integritätsprüfung „Audio ohne Turn-Ende“ zählt den Abschiedssatz nach `auflegen` mit (eigenes
  Audiostück ohne neues Turn-Ende). Nicht nachträglich geändert; die drei Fälle sind von Hand
  zugeordnet.
- Judge-Markierungen von Hand verworfen: A K05 („bis Mittwoch kaum Luft“ nimmt Mittwoch auf), A K08
  („Sitzen Sie tatsächlich in Hannover?“), B K02 („Pilot im Juni“), B K07 (kein falscher Name).
  Bestätigt: B K05 ×2 (Antwort auf den Preis statt auf Mittwoch, Folge des Verstummens), B K08
  („Hamburg oder Hannover, der Ort ist für uns okay“). Nicht markiert, aber gleich gelagert: eine
  weitere B-Antwort „Hamburg oder Hannover, egal“ — nach dem Verfahren nicht gezählt.
- T1, B: ein Turn ohne Antwort (R20 „Verstehe.“) ist ein STT-Ausfall (kein Transkript, kein
  Spekulationsstart in diesem Fenster), nicht spekulationsbedingt.
- T1-Latenz ohne F1/F2: A 1093 / 1665 (n = 26), B 908 / 1562 (n = 27). Mit ~64 ms verfügbarer
  Vorbereitungszeit nicht durch die Spekulation erklärbar; kleine, bedingte Stichprobe.
