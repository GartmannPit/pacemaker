# Phase 1 — Lasttest gleichzeitiger Gespräche (Stack `live`)

Stand: 2026-10-27 · Status: **Präregistrierung, noch nicht umgesetzt** · Prio 0 für Phase 1

Dieses Dokument ist Anleitung und Präregistrierung zugleich (CLAUDE.md, Messvertrag).
Änderungen nach dem ersten Messlauf nur als gekennzeichneter Nachtrag am Ende.

Es ersetzt den Azure-bezogenen Plan in `docs/phase-0-ergebnisse.md` §7 (Prio 0): Seit der
Gründerentscheidung vom 2026-10-15 läuft der Sprachpfad über OpenAI GPT-Live (`gpt-live-1`);
die gemessene Einzellatenz (Summary §28) haben die Gründer am 2026-10-27 als angemessen beschlossen.

## 1. Frage und Hypothese

**Frage:** Trägt der Stack `live` mehrere gleichzeitige Gespräche, ohne dass Dienstfehler
auftreten oder die Antwortzeit spürbar schlechter wird als im Einzelgespräch?

**Hypothese H1:** Bei 5 und bei 10 gleichzeitigen synthetischen Anrufern treten keine
Dienstfehler auf, und das p90 der Antwortzeit liegt je Stufe höchstens 20 % über dem p90 der
Einzelgespräche aus derselben Messreihe.

**Beobachtung B1 (kein Kriterium):** Wie viele Tokens pro Minute verbraucht ein Gespräch
gegenüber dem Organisationslimit von 30.000 TPM (§4)? Daraus folgt, wie viele Gespräche
gleichzeitig tragbar sind. Wird das Limit erreicht: welcher Fehler, wann, und was passiert mit
den laufenden Gesprächen?

## 2. Erfolgskriterium (Gründerentscheidung Pit, 2026-10-27)

Eine Laststufe gilt als **bestanden**, wenn beide Bedingungen erfüllt sind:

Gilt je Stufe für `L5` und `L10`.

1. **Keine Dienstfehler:** keine abgelehnte Sitzung, kein HTTP 429/5xx, kein unerwarteter
   Verbindungsabbruch, kein Turn mit Status `audiofehler` oder `keine_antwort`, der auf den
   Dienst zurückgeht.
2. **Latenz:** `p90(Stufe) ≤ 1,2 × p90(Einzel)`. `Einzel` = alle Einzelgespräch-Blöcke derselben
   Messreihe zusammengefasst (siehe §5).

Die Status `zerfallen` (ein Clip ergab mehrere Turns) und `abgebrochen` sind keine Dienstfehler,
werden aber je Stufe gezählt. Latenzbasis ist wie in Summary §28 je Clip
`first_audio_after_clip_ms`; vor der Umsetzung am Code prüfen, wie §28 diese Status
behandelt hat, und hier gleich verfahren.

Zusätzlich ausgewiesen, aber kein Kriterium: p50-Verhältnis, Fehlerquote je Status,
CPU-Last der VM, Ankunft des Server-Audios (`live_diag`).

Ist die VM selbst ausgelastet (CPU im Mittel eines Blocks > 85 %), wird die Stufe als
**„VM-begrenzt“** gekennzeichnet und nicht dem Dienst zugeschrieben. Dann entscheidet der
Vergleich der Server-Audio-Ankunft (`live_diag`), ob OpenAI langsamer wurde.

## 3. Rahmenbedingungen

| Punkt | Festlegung |
|---|---|
| Stack | `live`, Pipecat 1.12, Hintergrundmodell `gpt-4.1-mini` |
| Region | `OPENAI_LIVE_REGION=referenz` (api.openai.com) → Lauf als **„Baseline/Referenz“** kennzeichnen. Wiederholung mit `eu` nach Freigabe des EU-Projekts |
| Fixtures | nur synthetische Clips `agent/fixtures/audio` (10 Clips), `fixtures_sha` im Manifest prüfen. Keine Aufnahmen aus `fixtures/robust` |
| Ort | ausschließlich EU-Mess-VM (`infra/hetzner-setup.md`), nicht der Laptop |
| Parallel | keine andere Messung auf der VM und kein anderer Verbraucher desselben OpenAI-Projekts während der Reihe |
| Messpunkt | `first_audio_after_clip_ms` = letztes hörbares Sample des Clips → erstes Persona-Audio am Ausgabe-Transport der VM (**Agent-Ausgabe**, keine Browser-E2E-Latenz) |
| Zusatz | `PACEMAKER_LIVE_DIAG=1`: Ankunft des ersten hörbaren Server-Audios, trennt VM-Last von Dienstlatenz |
| Kaltstart | erster Turn jeder Sitzung getrennt ausweisen, im Hauptwert nicht enthalten |

## 4. Vorbereitung (vor dem ersten Lauf)

1. **Code auf die VM bringen:** Branch `gpt-live` pushen; auf der VM auschecken, `uv sync`.
   Die VM stand am 2026-10-27 noch auf `main` vom 11.10. (`f45f891`). Im Manifest muss eine
   echte Git-Revision stehen, nicht `unbekannt`.
2. **API-Key erneuern:** Der alte Key ist ungültig (401 am 2026-10-27). Pit trägt den neuen Key
   per SSH in `~/pacemaker/agent/.env` auf der VM ein, nicht über Git.
3. **Limits** (Stand 2026-10-27): Organisation im Tier **Build**. Modellseite `gpt-live-1`:
   **50 gleichzeitige Sitzungen** (Launch 300, Grow 500). Die OpenAI-Konsole (Limits der
   Organisation) zeigt für `gpt-live-1` zusätzlich **30.000 TPM**. Wie GPT-Live Tokens auf
   dieses Limit anrechnet (nur Audio oder auch Prompt je Antwort), ist nicht dokumentiert;
   je nach Zählweise reicht es grob für 3–30 gleichzeitige Gespräche. Das klärt B1.
4. **Kosten** (Stand 2026-10-27, OpenAI-Preisliste): `gpt-live-1` **0,05 $ je Minute**,
   sekundengenau, abgerechnet wird die **Sitzungsdauer**, nicht die Redezeit. Das
   Hintergrundmodell `gpt-4.1-mini` (0,40 $ / 1,60 $ je 1 Mio. Token Ein-/Ausgabe) wird nur
   für `auflegen` aufgerufen und ist vernachlässigbar. Eine Sitzung à 10 Clips dauert
   ~2,5–3 Min. (Läufe vom 2026-10-15). Plan §5: 18 Sitzungen ≈ 55 Min. ≈ **2,70 $**.
   Funktionstest vorab (§5) ≈ 0,15 $.
5. **Harness-Erweiterungen umsetzen und testen** (§6).

## 5. Ablauf

**Kostenrahmen (Vorgabe Pit, 2026-10-27): kurz halten.** Keine Wiederholung und keine
zusätzliche Stufe ohne neue Freigabe.

**0. Funktionstest** (vor der Reihe, zählt nicht zur Auswertung): 2 Anrufer gleichzeitig, je
3 Clips (`--turns 3`). Prüft nur, dass Run-IDs, Ablage, CPU-Protokoll und Sitzungsende
funktionieren. Bei Fehlern abbrechen, beheben, Funktionstest wiederholen.

**Blöcke:**

- `E` — Einzelgespräch: 1 Anrufer, 1 Sitzung à 10 Clips
- `L5` — 5 Anrufer gleichzeitig, je 1 Sitzung à 10 Clips
- `L10` — 10 Anrufer gleichzeitig, je 1 Sitzung à 10 Clips

Start mit zufälligem Versatz von 0–3 s je Anrufer.

**Reihenfolge** (eine Runde, ~20 Min.): `E, L5, E, L10, E`

Vor und nach jedem Block `infra/rtt-check.sh` (wie `infra/messreihe.sh`). Zwischen den Blöcken
30 s Pause.

**Umfang** (ohne Kaltstart-Turns): `E` 3 × 9 = 27 Turns; `L5` 5 × 9 = 45; `L10` 90. Das reicht für eine
**orientierende** Aussage („trägt / trägt nicht“), nicht für ein belastbares p90 auf wenige
Prozent. Liegt das Verhältnis knapp an 1,2 (zwischen 1,1 und 1,3), Ergebnis als „unklar“
ausweisen; eine Wiederholung braucht eine neue Freigabe.

**Abbruch:** Fallen in `L5` mehr als 2 Sitzungen mit Dienstfehlern aus, `L10` auslassen.

## 6. Nötige Harness-Erweiterungen

Der synthetische Anrufer ist für genau ein Gespräch gebaut. Fehlt:

1. **Eindeutige Run-ID:** `new_run_id()` in `agent/src/pacemaker_agent/metrics/run_manifest.py`
   hat Sekundenauflösung. Parallel gestartete Anrufer überschreiben sich dann gegenseitig
   (Manifest, Turn-Protokoll, Metriken). Run-ID um einen eindeutigen Anteil ergänzen
   (z. B. Mikrosekunden + PID); Leser der Run-ID (Aggregation, Export) mitprüfen.
2. **Laststufe im Manifest:** neue Konfigurationsfelder `load_concurrency` und `load_caller`
   (z. B. über Umgebungsvariablen `PACEMAKER_LOAD_CONCURRENCY`, `PACEMAKER_LOAD_CALLER`).
3. **Startskript** `infra/lasttest.sh`: startet je Block N Prozesse
   `synthetic_caller --stack live --turns 10` mit eigenem
   `PACEMAKER_RUNS_DIR=experiments/runs/lasttest/<datum>/<nr>-<block>`, Versatz 0–3 s,
   wartet auf alle, protokolliert CPU-Last der VM (`vmstat 1`) in denselben Ordner, hält die
   Reihenfolge aus §5 ein. Vorbild: `infra/messreihe.sh`.
   **Kostenschutz:** harte Obergrenze je Anrufer (z. B. `timeout 300`), danach Prozess beenden;
   bei Abbruch des Skripts (`trap` auf INT/TERM/EXIT) alle Anrufer beenden, damit keine
   Sitzung offen bleibt und weiter abgerechnet wird. Vor dem Start die geplante Zahl der
   Sitzungen und die Kostenschätzung ausgeben.
4. **Fehler sichtbar machen:** Sitzungsablehnungen, HTTP-Status und Verbindungsabbrüche des
   Stacks `live` als Turn-Status bzw. Manifest-Eintrag festhalten, nicht nur im Log.
5. **Token-Verbrauch erfassen (B1):** Nutzungs- und Rate-Limit-Ereignisse des Servers je
   Sitzung mit Zeitstempel als JSONL festhalten, falls GPT-Live sie liefert (in Pipecat 1.12
   und der Server-Ereignisliste prüfen; z. B. Usage je Antwort, Rate-Limit-Ereignisse).
   Liefert der Server nichts, das dokumentieren und auf Funktionstest-Ende den Verbrauch in
   der OpenAI-Konsole (Usage) ablesen lassen; keine Werte schätzen.
6. **Auswertung** `agent/src/pacemaker_agent/metrics/load_aggregate.py`: je Stufe n,
   Ausschlüsse (Kaltstart, Status), Erfolgs-/Fehlerzahlen, p50/p90 Agent-Ausgabe, p50/p90
   Server-Audio (`live_diag`), Verhältnis zu `E`, CPU Mittel/Maximum, Tokens je Gesprächsminute
   und Spitzen-TPM je Stufe (falls erfasst), Urteil nach §2.
7. **Tests** (pytest, ohne externe Dienste): Eindeutigkeit der Run-ID bei parallelem Aufruf,
   Auswertung mit künstlichen Turn-Protokollen (Kaltstart-Ausschluss, Verhältnis, Urteil,
   „VM-begrenzt“). `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`.

Neue Abhängigkeiten sind dafür nicht nötig.

## 7. Ergebnisablage

- Rohdaten: `experiments/runs/lasttest/<datum>/` auf der VM (gitignored)
- Zusammenfassung: `experiments/summaries/<datum>-lasttest-live.md`. Dort festhalten: Stack,
  Modell, Region (`referenz`), Git-Revision, Pipecat-Version, `fixtures_sha`, VM-Typ, Limits
  und Tier aus §4, Tabelle je Stufe nach §6.6, Urteil je Stufe, Abweichungen vom Plan
- Ergebnis danach in `docs/phase-0-ergebnisse.md` §7 (Prio 0) verlinken

## 8. Hinweise für ausführende Coding-Assistenten (z. B. Codex)

- `agent/.env` (lokal und auf der VM) nicht lesen, ausgeben oder kopieren. Keine API-Keys,
  SSH-Keys oder die VM-Adresse in Prompts, Logs oder Commits übernehmen.
- Keine Aufnahmen aus `agent/fixtures/robust` öffnen oder hochladen.
- Unit-Tests nur mit Mocks; OpenAI ausschließlich im beauftragten Messlauf ansprechen.
- Messdaten als JSONL, kein `print`. Keine Latenzen schätzen oder von Hand stoppen.
- Vor dem ersten Messlauf §4 vollständig erfüllen. Ergebnisse, die nicht gemessen wurden, als
  **[offen]** stehen lassen.

## Nachträge

Keine.
