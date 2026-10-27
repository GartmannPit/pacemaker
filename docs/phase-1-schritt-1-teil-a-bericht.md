# Schritt 1, Teil A — Implementierungsbericht

Stand: 2026-10-27. Basis: `s1-register`, `ac4c50105acf735d7a96694f2afe39b8746cbc68`.
Implementiert durch Codex; Review durch Claude und integriertes Review stehen aus.
Keine Commits, kein Push, keine neuen Abhängigkeiten, keine externen API-Aufrufe.

## Dateien

- `agent/src/pacemaker_agent/hybrid/journal.py`: append-only JSONL, `fsync`, exklusive
  `fcntl.flock`-Sperre, Verzeichnis `0700`, Journal `0600`, strenge Startprüfung.
- `agent/src/pacemaker_agent/hybrid/budget.py`: dauerhafte Reservierungen, idempotente
  Abrechnung, UTC-Monatsbudget, Guthabensperre und Warnung.
- `agent/src/pacemaker_agent/hybrid/sessions.py`: atomare Platzvergabe, Start/Ende,
  Watcher, Wiederanlauf und geordneter Shutdown.
- `agent/src/pacemaker_agent/hybrid/oplog.py`: typisierte Feld- und Ereignis-Allowlist;
  Hilfen für Standard-Logging und Loguru ohne Freitext oder Exception-Inhalte.
- `agent/tests/test_hybrid_register.py`: 69 netzfreie Testfälle mit synthetischen Daten.

`contracts.py`, `live/auth/app/cli`, `tools/gptlive_browser`, `pyproject.toml` und
`uv.lock` bleiben unverändert. Geschützte Datenpfade und `.env` wurden nicht geöffnet.

## Konstruktoren und Integration

```python
Journal(state_dir: str | Path)

Budget(
    journal: Journal,
    *,
    limit_micro: int = 25_000_000,
    warn_ratio: float = 0.8,
    live_reserve_micro: int = 500_000,
    backend_reserve_micro: int = 50_000,
    live_per_minute_micro: int = 50_000,
    input_per_million_micro: int = 400_000,
    output_per_million_micro: int = 1_600_000,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    oplog: contracts.OpLog | None = None,
)

SessionRegistry(
    budget: Budget,
    starter: contracts.Starter,
    journal: Journal,
    oplog: contracts.OpLog,
    *,
    max_parallel: int = 20,
    max_duration_s: float = 600,
    idle_timeout_s: float = 120,
    close_timeout_s: float = 15,
    clock: Callable[[], float] = time.monotonic,
)

OpLog(path: str | Path)
configure_logging(oplog: OpLog, *, include_loguru: bool = True) -> None
```

Reihenfolge: Journal öffnen, Betriebslog einrichten, Budget mit demselben Journal und
`oplog` erzeugen, Register erzeugen, `await registry.recover()` ausführen. Auch bei leerem
Journal sind Starts vorher gesperrt. Für `/healthz` steht `registry.ready` bereit.
`budget.status()` liefert den unveränderten `BudgetStatus`; dessen `warning` muss die
Anwendung für angemeldete Nutzer in den vorgesehenen Kontingenthinweis übersetzen.

`configure_logging()` vor dem Framework-Start aufrufen. Es ersetzt bisherige Root-Handler,
entfernt Handler bestehender benannter Logger und richtet optional Loguru neu ein.
Framework-Logs enthalten nur Ereignis und numerischen Level. Später zusätzlich eingerichtete
Framework-Handler bzw. separate Access-Dateien muss die Anwendung vermeiden oder entfernen.
Für eigene strukturierte HTTP-Ereignisse sind etwa `method`, `status`, `duration_s` erlaubt;
URL, Query, Header, Nachricht und Traceback werden verworfen. Zulässige Ereignisse und
Felder stehen vollständig in `oplog.py`; neue Ereignisse müssen dort ergänzt werden.

Beim Beenden zunächst keine weiteren HTTP-Starts annehmen, dann
`await registry.shutdown()`, danach `journal.close()` und zuletzt nach dem Framework
`oplog.close()`. `shutdown()` wartet auf laufende Starts und Aufräumaufgaben; verbleibende
defekte Watcher werden begrenzt abgewartet und abgebrochen.

Zusätzliche Integrationshilfen:

- `budget.set_provider_blocked(blocked: bool = True)` sperrt bzw. entsperrt neue Starts.
  Dies hebt keine Journalsperre auf. Die Guthabensperre gilt für die aktuelle Instanz und
  wird bei einem Neustart zurückgesetzt.
- `registry.snapshot()` liefert eine Kopie der offenen lokalen Referenzen und Zustände;
  keine Provider-IDs. Dies ist eine interne Betriebs-/Testhilfe, kein öffentlicher Endpunkt.
- `budget.reservations` liefert eine Kopie der offenen Reservierungen; `is_closed()` und
  `has_id()` dienen der konsistenten Rekonstruktion.
- `JournalError` signalisiert beschädigten bzw. nicht dauerhaft schreibbaren Zustand.
  Konstruktorfehler dürfen im Anwendungseinstieg nicht in ein leeres Register umgewandelt
  werden. Während des Starts wird ein Journalfehler vor dem Provider-Aufruf als
  `StartsBlocked`, danach als `StartFailed` mit eingeleitetem Aufräumen gemeldet.

## Entscheidungen

- Eine gemeinsame Register-Sperre umfasst Nutzerplatz, Gesamtplatz und Budgetreservierung.
  Provider-Netzwerkaufrufe liegen außerhalb dieser Sperre. Budgettransaktionen besitzen
  zusätzlich eine eigene Sperre gegen direkte konkurrierende Budgetzugriffe.
- Journal-Schreibvorgänge laufen über `asyncio.to_thread`, damit `fsync` nicht den
  Event-Loop blockiert. Es gibt keinen zweiten Event-Loop und keine Netzwerk-Thread-Brücke.
  Lesen und Prozesssperre erfolgen synchron beim Aufbau vor dem Serverstart.
- Start und Aufräumen sind mit separaten, referenzierten Tasks und `shield` gegen den
  Abbruch des Aufrufers geschützt. Eine abgebrochene Startanfrage erhält weiterhin die
  Erzeugungsantwort und beendet eine erfolgreich erzeugte Sitzung anschließend.
- Die Provider-ID steht vor `attach()` dauerhaft im Journal. Die monotone Deadline beginnt
  konservativ vor `create()`; `attach()` erhält sie absolut sowie `idle_timeout_s`.
  Der Watcher ergänzt die Deadline mit einem eigenen Zeitlimit. Die Erkennung nichtleerer
  Nutzer-Transkript-Deltas bleibt wegen des Vertrags Aufgabe des Sidebands in Teil B.
- Ein Watcher je angehängter Sitzung verarbeitet `wait_closed()`. Abschlussbuchung und
  Platzfreigabe sind serialisiert; wiederholtes `end()` und ein gleichzeitiges Auflegen
  erzeugen keine doppelte Buchung. Ein unbestätigtes Ende führt zum Notschluss; bleibt
  dieser unbestätigt, bleiben Eintrag und volle Reservierung erhalten.
- `end()` prüft Nutzer-ID und lokale Referenz. Die Nutzer-ID muss aus der gültigen Anmeldung
  kommen; Cookie-, Ablauf- und Widerrufsprüfung gehören zu Teil B.
- `CreateUnclear` und unerwartete Erzeugungsfehler behalten die volle Reserve und den Zustand
  `erzeugung_ungeklaert`; kein erneuter Erzeugungsaufruf. Nur eindeutig fehlgeschlagene
  Erzeugungen (`StartFailed`, `ProviderBlocked`) geben die Reserve frei.
- Ein Absturz zwischen Reservierung und erstem Sitzungseintrag wird konservativ als
  unbekannte Erzeugung rekonstruiert. Ohne Provider-ID ist kein gezielter Notschluss möglich;
  diese Reservierung wird auch beim Monatswechsel nicht automatisch freigegeben.
- Beim Wiederanlauf werden bekannte offene Provider-IDs geschlossen. Bis zu ihrer
  Bestätigung bleibt das Register nicht bereit. Erzeugungen ohne Provider-ID behalten
  Eintrag und Reserve, verhindern nach der Rekonstruktion aber nicht sämtliche anderen
  Starts. Nutzer-, Gesamtplatz- und Budgetgrenzen gelten weiterhin.
- Abrechnung bzw. Freigabe werden vor dem letzten Sitzungszustand persistiert. Ein Absturz
  genau dazwischen wird anhand der bereits abgeschlossenen Budget-ID erkannt; es entstehen
  weder Doppelbuchung noch eine erneut gebundene Reserve.
- Geld wird ausschließlich als ganzzahlige Mikro-Dollar gebucht; Bruchteile werden
  aufgerundet. Live-Sekunden sind kumulativ. Die Token-Summen müssen bereits vom Starter
  nach Response-ID dedupliziert sein; der Vertrag übergibt keine einzelnen Response-IDs.
- Fehlende/nicht finale Live-Usage kostet mindestens die Live-Reserve. Unvollständige/nicht
  finale Backend-Usage kostet mindestens die Backend-Reserve; höhere bekannte Kosten werden
  vollständig berechnet. Ein leeres, finales und vollständiges Backend-Aggregat bedeutet,
  dass kein Backend-Aufruf gesehen wurde. Attach-Fehler kosten bei bekannter finaler Usage
  mindestens 15 s; ohne Usage werden konservativ die gesamten 0,55 $ gebucht.
- `settle()` bei unbestätigtem Ende liefert `0` als noch nicht gebuchten Betrag, schreibt
  aber keine Nullbuchung und lässt die volle Reservierung bestehen.
- Buchungen zählen zum UTC-Monat der Reservierung; sämtliche offenen Reservierungen zählen
  bei jeder Startprüfung mit. Ab 80 % wird `budget_warnung` geschrieben; `status().blocked`
  berücksichtigt bereits, ob die nächste volle Reserve noch hineinpasst.

## Verträge und offene Punkte

Keine Änderung an `contracts.py` erforderlich oder vorgeschlagen. Zusätzlicher interner
Zustand liegt in `Reservation` und `_Session`. Weil `force_close()` keine Usage zurückgibt,
wird nach einem Absturz oder Attach-Fehler ohne vollständige Usage mit Reserven abgerechnet.

Offen bleiben Claude-Review, Integration mit Teil B, Anmeldung/HTTP, tatsächliche
Inaktivitätserkennung im Sideband und die freigegebene Live-Abnahme. Keine Browser-,
Provider-, VM- oder Latenzmessung ausgeführt; keine EU-Betriebsfreigabe abgeleitet.

## Ausgeführte Prüfungen

Aus `agent/`, jeweils mit `PYTHON_DOTENV_DISABLED=1` und
`UV_CACHE_DIR=/private/tmp/pacemaker-s1-uv-cache`:

```text
uv run --offline --no-sync pytest -q tests/test_hybrid_register.py
69 passed in 0.67s

uv run --offline --no-sync pytest -q
182 passed, 1 warning in 10.41s

uv run --offline --no-sync ruff check .
All checks passed!

uv run --offline --no-sync ruff format --check .
49 files already formatted
```

Die Warnung stammt aus Pipecats bestehendem Import von `audioop` (Python-Deprecation).
Die Tests verwenden ausschließlich Fakes/Mocks und temporäre synthetische Dateien.
Zusätzlich: `git diff --check` erfolgreich; geschützte Vertrags-, Prototyp- und
Abhängigkeitsdateien ohne Diff. Neue Dateien bleiben für das Claude-Review uncommittet.
