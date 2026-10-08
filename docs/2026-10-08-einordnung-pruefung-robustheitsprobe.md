# Einordnung der Prüfung der Robustheitsprobe

**Stand:** 2026-10-08
**Bezug:** [Prüfung der Robustheitsprobe (Codex)](./2026-10-08-pruefung-robustheitsprobe.md),
Summary §16 ([Modellvergleich](../experiments/summaries/2026-10-03-llm-modellvergleich-deployment-typen.md))
**Verfasser:** Claude (hat die Probe selbst durchgeführt — nicht unabhängig)

## 1. Ergebnis

Die Prüfung bestätigt alle Zählwerte und Latenzen aus §16 und ist in der Interpretation
berechtigt strenger. Sie findet einen echten neuen Fehler (kurze Äußerungen, §2.1), eine
Reproduzierbarkeitslücke meiner Auswertung (§2.2) und eine offene Grundsatzfrage zu Smart Turn
(§2.3). Die Korrekturen aus ihrem §7 übernehme ich weitgehend; §16 ist entsprechend geändert.

## 2. Wichtigste Punkte

### 2.1 Kurze Äußerungen brauchen 3,2–3,6 s (neu, übernommen)

Bei R19 („OK.", 0,27 s Sprache) greift die VAD nicht; das Turn-Ende kommt über den
Transkript-Fallback mit Zeitlimit. Daher fehlen genau diese sechs Sitzungen in den Latenzdateien
(150 statt 156). Für Gespräche relevant: „Ja.", „Okay.", „Verstehe." sind häufig.

Ursache nicht isoliert. **Hypothese (ungeprüft):** Pits Aufnahmen sind leise gepegelt (Spitze
~7 % Vollausschlag); Silero verlangt mindestens 200 ms Sprache (`start_secs`) bei einer
Mindestlautstärke. R20 („Verstehe.", 0,44 s) und R21 funktionieren.

→ Wird in der VAD-Kurve als Pflichtkontrolle mit ausgewertet (R19–R21); eigener Hebel, falls
nötig (VAD-Start, Pegel).

### 2.2 §16 war mit `robustness.py` nicht reproduzierbar (übernommen, behoben)

Ich hatte für die Tabelle von Hand gefiltert (nur nicht zerfallene Sitzungen, nur Abbrüche mit
Text). `robustness.py` ist jetzt so umgebaut, dass es genau diese Werte erzeugt, Sitzungen ohne
VAD-Zeitbasis separat zeigt, einen fairen Vergleich über dieselben Clips liefert und nach
Segmentierung **und** VAD-Stopp gruppiert. Ergebnis deckt sich mit Codex' Nachrechnung (gleiche
10 Clips: 944/1266, 1236/1657, 1315/2209 ms).

### 2.3 Smart Turn und das Prosodie-Verbot (offen — Entscheidung Pit)

Smart Turn v3 entscheidet aus Audiomerkmalen (Log-Mel), ob ein Turn beendet ist; es liefert
keinen Emotions-Score, nutzt aber vermutlich auch Satzmelodie. `CLAUDE.md` verbietet wörtlich
„Prosodie-, Stimmlagen- oder Stress-Analyse" und nennt Smart Turn zugleich im Tech-Stack.

Meine Einschätzung: Das Verbot zielt (wie AI Act Art. 5) auf Rückschlüsse über die Person —
Emotion, Stress. Eine Endpunkterkennung, die nur „Turn fertig / nicht fertig" ausgibt und nichts
speichert oder bewertet, fällt sinngemäß nicht darunter. Die Formulierung in `CLAUDE.md` sollte
das aber ausdrücklich sagen — oder Smart Turn wird ersetzt (z. B. Stille/VAD + textbasierte
Vollständigkeitsprüfung). **Keine Rechtsprüfung; vor dem Produktpfad klären.**

### 2.4 Übernommene Korrekturen (Details in §16)

| Bisher | Jetzt |
|---|---|
| Zerfall „unabhängig von der Segmentierung" | 30/29/28 von je 52; größere Segmentierung beseitigt den Zerfall nicht, Unabhängigkeit nicht nachgewiesen |
| Ursache „VAD + Smart Turn, nicht die Segmentierung" | Turn-Erkennung im Zusammenspiel mit STT ist der plausible Haupthebel; nicht isoliert verglichen |
| „hörbar unterbrochen" / „nur still verworfen" | „Ausgabe vor Fortsetzung mit Transkripttext (Näherung)" / „ohne Transkripttext"; kein Hörnachweis |
| „100 ms bestätigt, ohne mehr Zerfall" | vorläufig schnellste Referenz; leicht mehr Zerfall (30 vs. 28); Robustheit offen |
| „Information geht nicht verloren" | nur in Beispielen belegt, nicht systematisch geprüft |
| Latenz ohne Nenner | Nenner 20/21/22, R19 separat; Latenz zerfallener Sitzungen nicht als Antwortzeit verwertbar |
| R12 „zerfällt dreimal" | vier erkannte Turns (drei zusätzliche Grenzen) |
| „Nicht jeder Zerfall ist falsch" | gegenüber der vorab gesetzten Sollgrenze bleibt jeder Zerfall eine Abweichung; die gesprächspragmatische Bewertung wird getrennt annotiert |

### 2.5 Schritt C ist nicht abgeschlossen (übernommen)

Es fehlen das zusammenhängende Gespräch (die Reihe lief mit `--fresh`), annotierte Sollgrenzen
und kritische Mindestinfo je tatsächlich gesprochener Variante (Pit hat frei formuliert; die
STT-Kontrolltexte sind keine fehlerfreie Referenz).

### 2.6 Metriken (übernommen)

- „Vollständigkeit der ersten Nachricht" heißt jetzt **Wortabdeckung** — grober Indikator, kein
  Verständnismaß.
- Für spätere Versuche: orthogonale Flags neben dem Endstatus (zusätzliche Grenzen, Ausgabe vor
  Sollende, Mindestinfo erfüllt) — sinnvoll, sobald Sollgrenzen annotiert sind.

## 3. Reihenfolge

Codex empfiehlt: (1) Auswertung korrigieren, (2) gemeinsamer Abbruchpfad, (3) VAD-Vergleich,
(4) textbasierte Fortsetzungsprüfung, (5) Audio-Gating.

Umsetzung: (1) ist erledigt (§2.2). Als nächstes folgt wie vereinbart der **VAD-Stopp-Vergleich**
(0,2 / 0,4 / 0,6 s, Segmentierung 100 ms, alle 26 Aufnahmen, zwei gegenbalancierte Durchgänge),
mit R19–R21 als Pflichtkontrolle für kurze Äußerungen. Er braucht den Abbruchpfad nicht; dieser
bleibt in Schritt B (Barge-in ist Muss-Kriterium). Abbruchkriterium vorab: Ein längerer VAD-Stopp
gilt nur als Gewinn, wenn er den Zerfall deutlich senkt **und** die Latenz der gleichen Clips nicht
über das hinaus verschlechtert, was der Zerfallsgewinn rechtfertigt — sonst zurück zu 0,2 s.

## 4. Entscheidungen für Pit

1. Smart Turn und Prosodie-Verbot: `CLAUDE.md` präzisieren (Endpunkterkennung ohne Personen-
   rückschluss erlaubt) oder Smart Turn ersetzen?
2. Annotation von Sollgrenzen und Mindestinfo für die tatsächlich gesprochenen Varianten (R/S) —
   gemeinsam durchgehen (~30 Min.)?
