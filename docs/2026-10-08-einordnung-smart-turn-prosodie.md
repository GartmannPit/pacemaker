# Einordnung: Smart Turn und das Prosodie-Verbot

**Stand:** 2026-10-08 · **Verfasser:** Claude · **Status:** Entscheidung offen (Pit) ·
**Keine Rechtsberatung.**
**Bezug:** `CLAUDE.md` („Keine Emotionserkennung"), [Einordnung der Robustheitsprüfung §2.3](./2026-10-08-einordnung-pruefung-robustheitsprobe.md)

## 1. Sachverhalt

| | Belegt |
|---|---|
| **Was Smart Turn v3 tut** | Bekommt die letzten bis zu 8 s Nutzeraudio (16 kHz), gibt **eine Wahrscheinlichkeit** zurück, dass der Nutzer fertig ist; > 0,5 = Turn beendet. Whisper-Tiny-Encoder + linearer Klassifikator, lokal (ONNX, CPU). |
| **Woraus** | Laut Hersteller aus dem **Rohaudio — „prosody, pace, intonation"**, nicht aus dem Transkript ([Model Card](https://huggingface.co/pipecat-ai/smart-turn-v3), [Repo](https://github.com/pipecat-ai/smart-turn)). |
| **Was mit dem Ergebnis passiert** | Steuert nur, wann die Persona antwortet. Wird nicht gespeichert, nicht ausgewertet, fließt in kein Scoring und in keine Aussage über die Person. |
| **Im Stack seit** | Phase-0-Beginn (Pipecat-Default der Turn-Erkennung), in `CLAUDE.md` als „Pipecat Smart Turn" im Tech-Stack genannt. |

`CLAUDE.md` sagt: „Keine Prosodie-, Stimmlagen- oder Stress-Analyse, kein Emotions-Score.
Scoring nur über Gesprächsinhalt und -struktur. (EU-AI-Act Art. 5, am Arbeitsplatz verbotene
Praxis.) Auch nicht ‚nur zum Testen' einbauen."

## 2. Bewertung

**Wortlaut:** Smart Turn wertet Prosodie aus → nach dem Wortlaut ein Verstoß, und zwar schon
seit Phase-0-Beginn. Die Regel nennt Smart Turn zugleich im Tech-Stack; sie ist also in sich
widersprüchlich.

**Zweck:** Die Regel steht unter „Keine Emotionserkennung" und begründet sich mit AI Act Art. 5
(Emotionserkennung am Arbeitsplatz). Smart Turn erkennt keine Emotion und zieht keinen Schluss
über die Person; es beantwortet nur „spricht noch / fertig". Nach dem Zweck spricht viel dafür,
dass eine reine Endpunkterkennung ohne Speicherung und ohne Personenbezug nicht gemeint ist.
Das ist eine Einschätzung, keine juristische Prüfung.

**Produktsicht:** Kunden und Datenschutzbeauftragte lesen eher den Wortlaut („keine
Prosodieanalyse"). Eine Landingpage- oder AVV-Aussage „keine Prosodieanalyse" wäre mit Smart Turn
angreifbar.

**Technische Sicht (Phase-0-Befunde, Summary §16–§18):** Smart Turn ist an zwei gemessenen
Schwächen beteiligt — Zerfall bei Denkpausen und ~1 s Wartezeit bei Einwort-Antworten („OK."),
die es als unvollständig einstuft. Ob ein textbasierter Ersatz besser wäre, ist **nicht
gemessen**.

## 3. Optionen

| Option | Inhalt | Folge |
|---|---|---|
| **A — präzisieren** | `CLAUDE.md` erlaubt ausdrücklich eine Endpunkterkennung aus Audio, wenn sie nur „fertig / nicht fertig" liefert, nichts speichert und in keine Bewertung der Person einfließt; verboten bleibt jede Auswertung von Prosodie/Stimme **über die Person** (Emotion, Stress, Sicherheit, Scoring). | Kein Umbau. Produkttexte dürfen dann nicht pauschal „keine Prosodieanalyse" versprechen, sondern „keine Auswertung von Stimme oder Emotion über Sie". |
| **B — ersetzen** | Turn-Ende nur aus Stille (VAD) und Text/Kontext (z. B. Klassifikator auf dem Transkript). | Wortlaut sauber erfüllt. Erfordert Entwicklung und Messung; Latenz und Zerfall offen. Passt zur Architekturempfehlung für Phase 1. |
| **C — A jetzt, B prüfen** | A für Phase 0/1-Prototypen, B als Experiment in Phase 1 mit Abbruchkriterium. | Empfehlung (siehe unten). |

**Empfehlung:** C. Für die Phase-0-Abnahme ist entscheidend, dass die Spannung dokumentiert und
bewusst entschieden ist — nicht, dass sie technisch gelöst ist. Vor Produkttexten oder AVVs mit
der Aussage „keine Prosodieanalyse" muss die Entscheidung gefallen sein.

## 4. Gleiche Frage an anderer Stelle

Der Realtime-Stack (`s2s`) verarbeitet das Rohaudio im Modell; dort gilt dieselbe Abwägung
(EU-Compliance-Dokument, offener Punkt 6). Silero-VAD unterscheidet nur Sprache/Nicht-Sprache
und ist davon nicht betroffen.
