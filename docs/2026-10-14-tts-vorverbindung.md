# Experiment: TTS-Verbindung nach Unterbrechung neu öffnen

**Stand:** 2026-10-14 · **Status:** vor dem Lauf festgelegt (Präregistrierung). Änderungen nach dem
Lauf nur als gekennzeichneter Nachtrag.
**Bezug:** [Recherche Latenzhebel](./2026-10-14-recherche-latenzhebel.md), Summary §25, Diagnose
`metrics/tts_diag.py` (Branch `tts-diagnose`).

## 1. Befund aus der Diagnose

Isoliert liefert Azure TTS das erste Audio nach ~30–110 ms, in der Pipeline maß Pipecat 250–390 ms.
Die Diagnose (`PACEMAKER_TTS_DIAG=1`, SDK-Wert `SynthesisConnectionLatencyMs`) zeigt: Beim **ersten
Satz jedes Turns** baut das SDK die Verbindung neu auf (~250–350 ms); Folgesätze derselben Antwort
nicht. Ursache: Pipecat sendet bei jedem Sprechbeginn des Nutzers eine Unterbrechung, auch wenn
die Persona schweigt; die Azure-TTS ruft dabei `stop_speaking_async()` auf, und das schließt die
Verbindung (isoliert nachgestellt: danach 258 ms Neuaufbau; Neuöffnen danach: 0 ms). Pipecat-
Eigenzeit und Event-Loop-Verzögerung sind vernachlässigbar (< 1 ms bzw. ≤ 5 ms).

## 2. Verfahren

Nach Pipecats Unterbrechungsbehandlung öffnet die TTS die Verbindung im Hintergrund neu
(`Connection.open`), Schalter `PACEMAKER_TTS_PRECONNECT=1`, im Manifest als `tts_preconnect`.
Ein Öffnen schon bei Sprechbeginn wurde vom anschließenden Stopp wieder geschlossen und ist
verworfen.

## 3. Hypothese und Kriterien (vor dem Lauf festgelegt)

Erwartung: Erstes Audio −200 bis −300 ms bei p50 und p90 (der Neuaufbau fällt bei jedem Turn an).

**Messung:** EU-Mess-VM, `azure-eu`/`gpt-4.1-mini`, Referenzkonfiguration mit TTS-Sprache `de-DE`
und Warm-up mit Persona-Prompt (`main` 56e5c14), `--continue-after-hangup`, 3 × 30 Turns ohne und
3 × 30 mit Vorverbindung, abwechselnd (ohne, mit, …). Diagnose in beiden Bedingungen an.

| Kriterium | Grenze |
|---|---|
| **Primär:** E2E erstes Audio p50, mit gegenüber ohne (gepoolt je Bedingung) | Verbesserung ≥ 150 ms |
| Sekundär: E2E p90 | berichtet |
| Kontrolle: Anteil erster Sätze mit `SynthesisConnectionLatencyMs` > 0 | ohne: hoch, mit: ~0 |
| Neue Fehler (TTS-Fehler, fehlende Antworten, abgeschnittenes Audio) | 0 |

Übernahme in die Referenzkonfiguration (Default an), wenn Primärkriterium erfüllt und keine neuen
Fehler.

## Nachtrag 1 (2026-10-14): Ergebnis und Übernahme

Daten `experiments/runs/tts-vorverbindung/` (VM-Kopie `~/pacemaker-diag`). Keine Fehler im Log,
gleiche Turn-Bilanz in beiden Bedingungen.

| Bedingung | Turns | Text → Audio p50 / p90 | Erstes Audio p50 / p90 |
|---|--:|--:|--:|
| ohne | 70 | 456 / 604 | 1201 / 1442 |
| mit | 70 | 351 / 579 | 1106 / 1335 |

Diagnose der ersten Sätze je Turn: Neuaufbau ohne Vorverbindung in 79/80 Turns (p50 79 ms), mit
Vorverbindung in 0/80; Azure-Server-Zeit unverändert (p50 193 ms); erstes TTS-Audio 287 → 208 ms
p50.

- **Primärkriterium (≥ 150 ms bei p50) verfehlt:** −95 ms p50, −107 ms p90.
- **Fehler in der Erwartung:** Die angenommenen ~250–350 ms Neuaufbau stammten aus Laptop-Läufen
  (längere Strecke nach Frankfurt). Auf der VM kostet der Neuaufbau ~80 ms; die Vorverbindung
  beseitigt ihn vollständig, der gemessene Gewinn entspricht dem.
- **Abweichung von der Regel (Gründerentscheidung 2026-10-14):** Trotz verfehltem Kriterium
  übernommen (Default `PACEMAKER_TTS_PRECONNECT=1`), weil die Änderung keine Mehrkosten und kein
  zusätzliches Risiko hat und keine neuen Fehler zeigte. Ab jetzt tragen neue Läufe
  `tts_preconnect` im Manifest; ihr `config_hash` unterscheidet sie von früheren.
- Offen: Die Azure-Server-Zeit (130–190 ms in der Pipeline gegenüber ~30 ms erstes Paket im
  isolierten Test); Kandidaten Abtastrate 24 kHz, Wort-Zeitmarken, SSML.

## Nachtrag 2 (2026-10-14): Offene Server-Zeit — Abtastrate und Wort-Zeitmarken ohne Einfluss

Kurzmessung auf der VM (`~/probe/azure_rate_wb.py`): 16 gegen 24 kHz × Wort-Zeitmarken an/aus,
sonst wie die Pipeline (Sprache, WebSocket-Property, Pipecat-SSML); je Variante mehrere frisch
aufgebaute Verbindungen, Varianten abwechselnd, 1 s Abstand. Messwert
`SynthesisServiceLatencyMs` (Server-Zeit), Median je Verbindungsrunde:

| Lauf | 16 kHz / aus | 16 kHz / an | 24 kHz / aus | 24 kHz / an |
|---|---|---|---|---|
| 1 (5 Runden) | 228, 214, 201, 201, 28 | 47, 37, 33, 29, 24 | 202, 216, 202, 210, 28 | 220, 211, 202, 176, 38 |
| 2 (4 Runden, Aufbau-Reihenfolge rotiert) | 10, 36, 37, 28 | 20, 29, 29, 20 | 10, 37, 38, 38 | 11, 34, 48, 28 |

**Befund:** Kein konsistenter Einfluss von Abtastrate oder Wort-Zeitmarken. Die Server-Zeit
schwankt zeitlich zwischen ~10–40 ms und ~200 ms für alle Varianten gleichzeitig (Lauf 2 eine halbe
Stunde nach Lauf 1: durchgehend schnell). Die Lücke zwischen isolierten Tests (~30 ms) und der
Pipeline-Messung (130–190 ms) ist damit Messzeitpunkt, keine Konfiguration. Kein weiterer Hebel auf
unserer Seite; A/B-Vergleiche bleiben nur mit abwechselnder Reihenfolge gültig.
