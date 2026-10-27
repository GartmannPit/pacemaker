# Lasttest-Harness — lokale Umsetzung vor dem ersten Lauf

Stand: 2026-10-27. Ergänzung zur [Präregistrierung](phase-1-lasttest.md), keine
Messung und keine Änderung der Kriterien. Ergebnisse des Lasttests bleiben **[offen]**.

## Entscheidung zu §2 und Summary §28

`metrics/turn_ledger.py:summarize()` berechnet `first_audio_after_clip_ms` unabhängig
vom Turn-Status. Ein eigenes Auswertungsskript für Summary §28 ist nicht im Repo.
Die vorhandenen synthetischen `live-l/turns`-Protokolle ergeben mit allen 29 vorhandenen
Clip-Werten einschließlich `zerfallen` die veröffentlichten gerundeten Werte 1622/2452 ms.
Nur `beantwortet` zu zählen ergäbe n=19 und entspräche damit nicht der dokumentierten
Grundgesamtheit. Das ist eine Nachauswertung vorhandener Daten, kein neuer Messlauf.
`abgebrochen` kommt in diesen Protokollen nicht vor; der Messcode behandelt dessen
Clip-Latenz ebenfalls unabhängig vom Status.

Für die neue Auswertung bleiben deshalb `beantwortet`, `zerfallen` und `abgebrochen`
mit vorhandenem Clip-Wert in der Latenzbasis. Die Status werden einzeln gezählt;
`zerfallen` und `abgebrochen` zählen nicht als Dienstfehler. Der erste Clip jeder
Sitzung wird zusätzlich gemäß Lasttestplan als Kaltstart ausgeschlossen und separat
angezeigt. Andere Status und fehlende Werte werden als Ausschlüsse ausgewiesen.
Ohne belegte Dienstursache wird ein stummer Turn nicht automatisch OpenAI zugeschrieben;
er verhindert ein positives Urteil und führt zu „unklar“. Strukturierte Dienstfehler
im Manifest oder Fehler im Turn-Protokoll führen zu „nicht bestanden“.

Der Bereich 1,1–1,3 führt gemäß §5 zu „unklar“, auch wenn das rechnerische
20-%-Kriterium erfüllt ist; beide Einzelkriterien stehen zusätzlich im JSON.
Ein Blockmittel der CPU >85 % hat als „VM-begrenzt“ Vorrang. Server-Quantile und ihre
Verhältnisse zur E-Referenz stehen daneben; daraus wird keine automatische
Ursachenzuschreibung abgeleitet. CPU = `us + sy + st` aus `vmstat`; die erste,
seit Systemstart gemittelte Datenzeile wird verworfen.

## Befund zu §6.5: installierte Pipecat-Version 1.12.0

Lokal geprüft: `agent/.venv/lib/python3.12/site-packages/pipecat/services/openai/live/`
mit `events.py` (Server-Ereignisliste) und `llm.py` (Dispatch, `_report_usage`,
`_report_backend_usage`). Es gab keine Online-Abfrage oder Dienstverbindung.

- `session.usage.updated` enthält `usage.seconds`, **kumulative Sekunden**, keine
  modellierten Live-Tokens. `session.closed` kann die finale kumulative Usage liefern.
  Die Auswertung verwendet das Maximum; Zwischenstände werden nicht summiert.
- `response.event` kann im verschachtelten `response.completed` die Token-Usage des
  **Backend-Modells** liefern. Diese wird getrennt erfasst und über Response-ID
  dedupliziert. Backend-Tokens dürfen nicht auf das GPT-Live-TPM-Limit bezogen werden.
- Die lokale Server-Ereignisliste enthält keinen modellierten Rate-Limit-Typ.
  Unbekannte Ereignisse bleiben als `UnknownServerEvent` erhalten. Ereignisse mit
  `rate_limit` im Typ werden vor dem Pipecat-Dispatch erfasst. Dass der tatsächliche
  Server sie sendet, ist **[offen]**.

`live_usage/<run_id>.jsonl` enthält Run-ID, UTC- und Unix-Zeitstempel sowie unveränderte
Usage-Werte, Ereignis-/Response-IDs und etwaige Rate-Limit-Daten. Fehler werden ohne
Exception-Texte, HTTP-Header oder Transkripte gespeichert. Die Live-Tokenrate und
Live-Spitzen-TPM bleiben `null`; es wird nichts aus Sekunden geschätzt. Backend-Raten
werden separat ausgewiesen: je Sitzung sowie je Stufe über Sitzungen mit gemeldeter
Usage und bekannter Dauer (deren Anzahl wird genannt). Backend-Spitzen-TPM sind die
Summe gemeldeter Tokens in einem gleitenden 60-s-Fenster nach Empfangszeit.

**Nach dem Funktionstest muss die ausführende Person den Verbrauch in der OpenAI-Konsole
(Usage) ablesen.** Das Harness gibt diesen Hinweis aus. Der tatsächliche Umfang der
Usage-Ereignisse und Live-TPM bleiben bis dahin **[offen]**.

## Ablage und Aufruf durch die ausführende Person

Erst alle Vorbereitungen aus §4 auf der EU-Mess-VM erfüllen. Dieses Dokument erteilt
keinen zusätzlichen Messauftrag. Die beiden vorgesehenen Aufrufe aus dem Repo-Root:

```sh
bash infra/lasttest.sh funktionstest
bash infra/lasttest.sh reihe
```

Jeder Aufruf erhält einen eigenen Ordner unter
`experiments/runs/lasttest/<UTC-Zeit>-<PID>-<Modus>/`, darunter `<nr>-<block>/` mit
Manifesten, Turn-/Ereignisprotokollen, `live_diag`, `live_usage`, `vmstat.log`,
`rtt.jsonl`, Anrufer-Logs, `callers.jsonl`, `block.json` und `health.json`.
Nur eine Runde `E,L5,E,L10,E,L20,E` (L20 nachgetragen), je Anrufer 0–3 s Versatz, 30 s zwischen Blöcken.
Die RTT-Prüfung nutzt den neuen Modus `rtt-check.sh 10 live` gegen `api.openai.com`;
dieser liest keine `.env`. Region und Backend-Modell werden für diese Reihe fest gesetzt.
`UV` hat denselben Default wie in `messreihe.sh`: `$HOME/.local/bin/uv`.

Jeder Anrufer läuft in einer eigenen Prozessgruppe, mit `timeout 300` und 5 s
Kill-Frist. INT/TERM/EXIT beenden die Gruppen, nötigenfalls per KILL, und räumen
`vmstat` auf. Die Kostenannahmen aus §4 und das Budget bei Erreichen der Zeitgrenze
werden vor Sitzungsbeginn ausgegeben. Keine automatischen Wiederholungen oder
Wiederanrufe im Lastmodus. Bei >2 Dienstfehlersitzungen in einer Laststufe entfallen alle höheren;
ein Auflegen der Persona vor dem letzten Clip zählt als vollständige Sitzung (`hung_up`);
sonstige unvollständige Blöcke stoppen die Reihe. Ein fehlgeschlagener Funktionstest
startet keine Reihe.

Sitzungsablehnungen vor dem ersten Clip, HTTP-Status, unerwartete Socket- und
Sitzungsenden sowie ein nicht bestätigtes Sitzungsende landen im Manifest unter
`service_errors` und in der JSONL. Unbrauchbare Live-Verbindungen beenden die Pipeline.
Auch ein Ende vor Transport-Bereitschaft hinterlässt eine Sitzungsbilanz.
Bei Timeout/KILL belegt zusätzlich der Exit-Code den unvollständigen Anrufer; das
ist ohne weitere Evidenz kein dem Dienst zugeschriebener Fehler. Manifeste werden
atomar ersetzt, damit ein Abbruch keine halb geschriebene JSON-Datei hinterlässt.

Die Reihe schreibt am Ende `aggregate.json`. Eine abgebrochene Reihe kann lokal
nachträglich ausgewertet werden:

```sh
cd agent
uv run --offline --no-sync python -m pacemaker_agent.metrics.load_aggregate <Reihenordner>
```

Fehlende Anrufer/Protokolle/CPU-Daten oder unterschiedliche Kernkonfigurationen werden
nicht als Erfolg gewertet. Für ein positives Lasturteil müssen alle drei E-Blöcke
vorliegen. Funktionstests werden nicht gepoolt. Die Zuordnung des Server-Audios nutzt
Clip-Ende und Turn-Fenster derselben Sitzung; keine Zeitstempel verschiedener Rechner.

Run-IDs enthalten UTC mit Mikrosekunden, PID und UUID. Die Leser in `aggregate`,
`conversation`, `robustness`, `hold_simulation`, `transcript_export` und `barge_in`
verwenden vollständige Dateistämme bzw. Manifest-IDs, keine feste Zeitformatlänge.
Die Pfadzuordnung und der Transkript-Export werden zusätzlich mit neuer Run-ID getestet.

## Lokale Prüfung und offene Arbeit

Die Tests verwenden ausschließlich Mocks/künstliche Protokolle. Auch die Shell-Tests
ersetzen Anrufer, uv, timeout, RTT und vmstat vollständig; sie erzeugen keine Messdaten
oder Dienstaufrufe. Abgedeckt sind u. a. Parallel-IDs bei eingefrorener Uhr,
Kaltstarts/Status/Quantile/Urteile, VM-Begrenzung, fehlende Protokolle,
Pipecat-Verbindungsablehnungen 401/429/503, kumulative Usage und getrennte Backend-Tokens,
Blockfolge, L5-Abbruchregel und TERM-Aufräumen auch bei TERM ignorierenden Mock-Anrufern.

Offen: VM-Vorbereitung gemäß §4, echter Funktionstest einschließlich Kosten-/Usage-Ablesung,
eigentlicher Lasttest, tatsächliche Latenzen/CPU/TPM und Ergebnisbericht gemäß §7.
Keine Abhängigkeiten ergänzt; kein Commit oder Push. Vorhandene unversionierte Fixtures
wurden nicht verändert. `.env` wurde nicht gelesen; bei lokalen Prüfungen war
`PYTHON_DOTENV_DISABLED=1` gesetzt.

Abschließende Prüfung aus `agent/`, jeweils mit `PYTHON_DOTENV_DISABLED=1` und einem
Cache unter `/private/tmp`:

```text
uv run --offline --no-sync pytest
53 passed, 1 warning in 9.03s

uv run --offline --no-sync ruff check .
All checks passed!

uv run --offline --no-sync ruff format --check .
37 files already formatted
```

Die Warnung stammt aus Pipecats Import des veralteten Standardmoduls `audioop`.
`bash -n infra/lasttest.sh infra/rtt-check.sh` (aus Repo-Root) und `git diff --check`
waren ebenfalls erfolgreich, ohne Ausgabe. Keine echten Messläufe ausgeführt.
