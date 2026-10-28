# Phase 1, Schritt 1 — Hybrid-Server und Sitzungslebenszyklus (Plan)

Stand: 2026-10-27 · Status: **umgesetzt und gegenseitig geprüft (206 Tests grün); Live-Abnahme (§5.4) ausstehend** · Bezug:
[Phase-1-Plan](./phase-1-mvp.md) §2 Schritt 1, §3, §6 · Prototyp: `agent/tools/gptlive_browser/`

## 1. Ziel

Ein Server, der den Hybrid aus dem Architekturversuch betriebsfest macht: Gespräche nur für
angemeldete Nutzer, Grenzen für Parallelität, Dauer und Kosten, sauberes Aufräumen, Logs ohne
Gesprächsinhalte. Frontend (`web/`) folgt in Schritt 2; hier genügt eine schlichte Testseite.
Lokale Abnahme ist **keine** EU-Betriebsfreigabe (Phase-1-Plan §1).

## 2. Abnahmekriterien

Für jeden Fehlerpfad wird nachgewiesen: Abschlussstatus, verbleibende Reservierung,
verbleibende Registereinträge. Abgewiesene Starts lösen keinen Provider-Aufruf aus.

| # | Kriterium |
|---|---|
| A1 | Sitzungsstart und Beenden nur mit gültiger Anmeldung; ungültige, abgelaufene und widerrufene Anmeldungen sowie fremde `session_ref`s werden abgewiesen. |
| A2 | Höchstens 1 Gespräch je Nutzer und höchstens `PACEMAKER_MAX_PARALLEL` (Default 20) gesamt; startende und endende Gespräche zählen mit; gleichzeitige Starts desselben und verschiedener Nutzer korrekt. |
| A3 | Der Server sendet spätestens 600 s nach Erzeugung `session.close` (`PACEMAKER_MAX_DURATION_S`, höchstens 600). Ohne `session.closed` binnen 15 s folgt `force_close` über eine neue Verbindung; bleibt die Bestätigung aus, Zustand `abschluss_ungeklaert` mit gebundener Reserve. Eine Laufzeitgrenze bei OpenAI selbst ist damit nicht garantiert (siehe Grenze in A5). |
| A4 | Budget 25 $/Monat: Warnung, wenn verbraucht + gebunden ≥ 80 %; Start verweigert, wenn verbraucht + gebunden + Reserve des neuen Gesprächs > Budget. Fehlende Usage wird nie mit 0 gebucht. Für das Hintergrundmodell gibt es **keine garantierte Obergrenze** (Aufrufzahl technisch nicht begrenzbar); es gilt eine geschätzte Reserve (§3). |
| A5 | Aufräumen bei: Persona-Auflegen, Nutzer-Ende, Tab-Schließen (Beacon), WebRTC-Abbruch ohne Beacon, Sideband-Abbruch, Attach-Fehler, Abbruch der HTTP-Anfrage während des Starts, geordnetem Shutdown, Neustart nach Absturz. Grenze: Geht die Antwort von OpenAI auf die Erzeugung verloren, kennt der Server die Sitzung nicht und kann sie nicht gezielt schließen; dieser Fall wird als `erzeugung_ungeklaert` mit voller Reserve gebucht. |
| A6 | Datenkanal immer gesperrt (`allowed_client_events: []`), Serverereignisse an den Browser per fester Allowlist; Debug-/Unlock-Felder im Request werden abgewiesen. |
| A7 | Betriebslog JSONL mit Feld-Allowlist; Framework-, Access- und Exception-Logs eingeschlossen. Nie: Gesprächsinhalte, Audio, SDP, Passwörter, Cookies, Authorization-Header, Keys, Provider-Fehlertexte. |
| A8 | Region explizit (`OPENAI_LIVE_REGION`), Erzeugung und Sideband auf demselben Host, keine Redirects mit Hostwechsel. Konfigurationstest, kein EU-Nachweis. |
| A9 | Aus `agent/`: `PYTHON_DOTENV_DISABLED=1 uv run --offline --no-sync pytest`, `uv run --offline --no-sync ruff check .`, `uv run --offline --no-sync ruff format --check .` grün. |

## 3. Festlegungen

**Technik.** `aiohttp` 3.14.3 (bereits im Lockfile, wird direkte Abhängigkeit). Ein
asyncio-Loop, keine Thread-Brücke. Paket `agent/src/pacemaker_agent/hybrid/`, Einstieg
`pacemaker-server`. Eine Prozesssperre (`fcntl.flock`) je State-Verzeichnis verhindert
Doppelbetrieb.

**Anmeldung (minimal; Self-Service in Schritt 5).**
- Nutzer per CLI (`pacemaker-server nutzer-anlegen <name>`), Passwort über `getpass`, nie als
  Argument. Nutzerdatei `PACEMAKER_USERS_FILE` (Verzeichnis `0700`, Datei `0600`), atomar
  geschrieben, gegen parallele Änderung gesperrt; stabile Nutzer-ID, Name normalisiert
  (Kleinschreibung, NFC). Beschädigte Datei → Startverweigerung.
- Hash: scrypt `n=2**17, r=8, p=1, dklen=32`, 16 Byte Salt, `maxmem` passend; Format mit
  Version und Parametern. Berechnung außerhalb des Loops, höchstens 2 parallel, Warteschlange
  begrenzt. Unbekannte Nutzer: Dummy-Hash, gleiche Meldung, `hmac.compare_digest`.
- Brute Force: 5 Fehlversuche je Konto und 30 je IP in 15 Min. → `429` mit `Retry-After`;
  Zählerspeicher begrenzt.
- Anmeldung serverseitig: zufällige Login-ID (32 Byte) im Cookie, Ablauf 12 h serverseitig
  geprüft. Logout löscht die Login-ID; Sperren oder Passwortänderung löscht alle des Nutzers.
  Cookie `HttpOnly`, `SameSite=Strict`, `Path=/`, ohne `Domain`; unter HTTPS `__Host-`-Präfix
  und `Secure`. Unsicheres Cookie nur im ausdrücklichen Loopback-Entwicklungsmodus
  (`PACEMAKER_DEV_LOOPBACK=1`), nie anhand des Host-Headers.
- CSRF: Origin exakt gegen `PACEMAKER_PUBLIC_ORIGIN` (Schema, Host, Port) für Login, Logout,
  Start, Ende. Fehlende oder `null`-Origin wird abgewiesen – einzige Ausnahme: Beacon auf
  `/api/end` mit gültigem Cookie **und** passender `session_ref` (zufällig, nur dem
  eigenen Browser bekannt).

**Kosten und Budget.**
- Beträge als Ganzzahl in Mikro-Dollar. `gpt-live-1` 0,05 $/Min. nach kumulativen
  Live-Sekunden (nie summieren); Hintergrundmodell nach Tokens zu Listenpreis
  (`gpt-4.1-mini` 0,40 / 1,60 $ je 1 Mio.), dedupliziert nach Response-ID, auch aus
  fehlgeschlagenen/unvollständigen Responses, sofern Usage vorhanden.
- Reserve je Gespräch: 600 s × 0,05 $/Min. = 0,50 $ plus Backend-Schätzung 0,05 $
  (Messwert Versuch: ~3.800 Tokens je Auflegen ≈ 0,002 $; Faktor > 20). Die Backend-Reserve
  ist keine Garantie (A4).
- Reservierung **vor** dem kostenpflichtigen Aufruf mit lokaler ID, dauerhaft im Journal.
  Abrechnung idempotent mit derselben ID. Fehlende Komponenten bei bestätigtem Ende: mit
  Reserve buchen, als `geschaetzt` markiert; `backend_complete=False` → Backend-Anteil
  mindestens mit der vollen Backend-Reserve. Unbestätigtes Ende: Reserve bleibt gebunden,
  bis `force_close` bestätigt; zählt weiter gegen das Budget. Attach-Fehler: mindestens 15 s
  Anlaufkosten buchen. Ein Gespräch zählt zum UTC-Monat seines Starts; die Prüfung rechnet
  offene Reservierungen unabhängig vom Monat mit.
- Warnung ab 80 % (verbraucht + gebunden): Betriebslog `budget_warnung` und Hinweis in
  `/api/status` für angemeldete Nutzer („Kontingent bald erschöpft“); Pit liest das
  Betriebslog. `credit_balance_exhausted` oder Quota-Fehler von OpenAI sperren neue Starts
  bis zum Neustart bzw. Freigabe per CLI.
- Zweite Sicherung: Projektbudget in der OpenAI-Konsole. Ein Alarm stoppt keine Anfragen, ein
  Hard Limit greift nicht sofort – es ergänzt, ersetzt nicht.

**Journal und Wiederanlauf.** Ein append-only JSONL-Journal (`PACEMAKER_STATE_DIR`) für
Reservierungen, Provider-IDs (sofort nach Bekanntwerden, vor Attach), Zustandswechsel und
Abrechnungen. Beim Start: Journal einlesen, Reservierungen und offene Sitzungen
rekonstruieren, offene Sitzungen per `force_close` schließen; erst danach Starts annehmen
(`/healthz` meldet bis dahin „nicht bereit“). Schreibfehler im Journal sperren neue Starts.
Beschädigtes Journal führt nicht zu einem leeren Register, sondern zur Startverweigerung.

**Gesprächsinaktivität.** 120 s ohne nichtleeres Nutzer-Transkript-Delta (monotone Uhr, Start
beim Attach) → Ende mit Grund `inaktiv`. Ergänzt Beacon und die Verbindungsverlust-Erkennung
von OpenAI (~21–27 s im Versuch).

**HTTP.** Body-Grenzen: Login/Ende 4 KiB, Start 80 KiB (SDP ≤ 64 KiB), Lesezeitlimit 10 s;
Schema- und Typprüfung, Stimmen-Allowlist (8 Stimmen aus dem Versuch). Header: CSP mit Hash,
`frame-ancestors 'none'`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`,
`Cache-Control: no-store` für API und Anmeldung, HSTS unter HTTPS – auch bei Fehlerantworten.
Provider-Fehler: Client-Eingabefehler 400; Provider-Konfiguration/Auth 503; temporäre
Ausfälle 502/503/504; nur lokale Fehlercodes und deutsche Meldungen. **Kein Wiederholen
eines möglicherweise erfolgreichen Erzeugungsaufrufs.** `/healthz` ohne Details, keine
kostenpflichtigen Provider-Aufrufe.

**Transkripte.** In Schritt 1 keine Persistenz. Der Sideband hält Text nur im Speicher;
Endpunkte des Prototyps `/api/browser_transcript` und `/api/result` entfallen.

## 4. Verträge (`hybrid/contracts.py`, vor der Aufteilung festgelegt)

```python
EndReason = Literal["nutzer", "auflegen", "zeitlimit", "inaktiv", "tab_geschlossen",
                    "verbindung_verloren", "sideband_abbruch", "attach_fehler",
                    "server_ende", "wiederanlauf"]
SessionState = Literal["startend", "laufend", "endend", "abschluss_ungeklaert",
                       "erzeugung_ungeklaert", "beendet"]

@dataclass(frozen=True)
class UsageSummary:
    live_seconds: int | None          # kumulativ, None = nicht gemeldet
    backend_tokens: dict[str, int]    # input/output, dedupliziert
    backend_complete: bool            # jede gesehene Response hatte Usage
    final: bool                       # aus session.closed

@dataclass(frozen=True)
class CloseOutcome:
    confirmed: bool                   # session.closed empfangen
    reason: EndReason

@dataclass(frozen=True)
class StartResult:
    session_ref: str                  # zufällig, lokal; nie die Provider-ID
    answer_sdp: str

class CreateUnclear(Exception): ...   # Erzeugung möglicherweise erfolgt

class SidebandHandle(Protocol):
    async def close(self, *, reason: EndReason) -> CloseOutcome: ...
    async def wait_closed(self) -> tuple[CloseOutcome, UsageSummary]: ...
    def usage(self) -> UsageSummary: ...   # Zwischenstand

class Starter(Protocol):              # live.py; in Tests ersetzt
    async def create(self, sdp: str, voice: str | None) -> tuple[str, str]: ...  # provider_id, SDP
    async def attach(self, provider_id: str, *, deadline_s: float,
                     idle_timeout_s: float) -> SidebandHandle: ...
    async def force_close(self, provider_id: str) -> CloseOutcome: ...

class Budget:                          # budget.py
    async def reserve(self, local_id: str) -> None: ...      # wirft BudgetErschoepft
    async def settle(self, local_id: str, *, usage: UsageSummary,
                     closure: CloseOutcome) -> int: ...       # Mikro-Dollar, idempotent
    async def release_uncreated(self, local_id: str) -> None: ...
    def status(self) -> BudgetStatus: ...

class SessionRegistry:                 # sessions.py
    async def start(self, user_id: str, sdp: str, voice: str | None) -> StartResult: ...
    async def end(self, user_id: str, session_ref: str, *, reason: EndReason) -> bool: ...
    async def recover(self) -> None: ...
    async def shutdown(self) -> None: ...
```

Prüfung und Vergabe von Nutzerplatz, Gesamtplatz und Reservierung unter einer gemeinsamen
Sperre; Netzwerkaufrufe außerhalb. Ein Watcher je Gespräch verarbeitet Auflegen, Abbruch,
Deadline und Inaktivität genau einmal; Abbruch der HTTP-Anfrage bricht das Aufräumen nicht ab.

## 5. Aufteilung und Ablauf

1. **Claude** legt `contracts.py` an (Basis-Commit für beide Teile).
2. Parallel, je eigener Worktree:
   - **Teil A (Codex):** `budget.py`, `sessions.py`, `journal.py`, `oplog.py` mit Tests gegen
     einen Fake-`Starter`. Besitzt Journal, Reservierung, Register, Wiederanlauf.
   - **Teil B (Claude):** `live.py` (Übernahme aus dem Prototyp, `Starter`, Deadline ab
     Erzeugung, Inaktivität, `force_close` mit Bestätigung, Backend-Usage auch bei
     Fehl-Responses), `auth.py`, `app.py`, `cli.py`, Testseite, pyproject, Tests.
3. Review: Claude prüft A, Codex prüft B; danach Codex den integrierten Stand. Integration und
   Merge durch Claude.
4. **Live-Abnahme** (Freigabe Pit, Deckel 0,50 $, höchstens 6 Sitzungen, je ≤ 2 Min.):
   Auflegen, Nutzer-Ende, Tab-Schließen, Abbruch ohne Beacon, zweiter Start bei belegter
   Nutzersitzung (Abweisung ohne Provider-Aufruf), Neustart während eines Gesprächs.

## 6. Offen, nicht Teil dieses Schritts

- **Hosting [offen, Pit]:** Außerhalb von localhost braucht das Mikrofon HTTPS. Vorschlag:
  eigene kleine Hetzner-VM (nicht die Mess-VM), Docker, TLS-Reverse-Proxy; Entscheidung und
  AVV vor Inbetriebnahme.
- Self-Service-Login, Passwort zurücksetzen: Schritt 5. Transkript-Persistenz: Schritt 6.

## Nachtrag: Umsetzung (2026-10-27)

- Teil A (Codex) und Teil B (Claude) in `agent/src/pacemaker_agent/hybrid/`, zusammengeführt
  in `gpt-live`. Prüfungen: 206 Tests, ruff check und format grün (Mocks, ohne Netz).
- Abweichungen vom Plan: Cookie enthält eine zufällige Login-ID statt HMAC-Signatur
  (serverseitige Liste, Widerruf über Anmeldeversion in der Nutzerdatei); Logins nur im
  Speicher, ein Neustart meldet alle ab. Vertrag ergänzt: typisierte Startfehler
  (`OfferRejected`, `ProviderConfig`, `ProviderUnavailable`), `SidebandHandle.provider_blocked()`,
  `attach()` erhält verbleibende Sekunden.
- Reviews: Claude prüfte Teil A (Deadline-Übergabe korrigiert), Codex prüfte Teil B und die
  Integration (1 × P1, 8 × P2, alle behoben und bestätigt).
- Offen: Live-Abnahme (Freigabe Pit, ≤ 0,50 $); Verhalten von OpenAI beim Anhängen an eine
  bereits beendete Sitzung (404/410 als „beendet“ angenommen) – davon hängt ab, ob ein
  Wiederanlauf den Server dauerhaft „nicht bereit“ lassen kann.

## Nachtrag: Live-Abnahme (2026-10-28)

Region `referenz`, Pits Stimme (Gründerfreigabe 2026-10-15), Chrome lokal, Server
`127.0.0.1:8080`. Kosten laut Journal ≈ 0,61 $ (Runde 1 ≈ 0,26 $, Runde 2 ≈ 0,33 $,
Diagnose ≈ 0,02 $); **freigegeben waren 0,50 $** – überschritten durch ein 5:22 min langes
Auflege-Gespräch im Nachtest, für das kein Zeitlimit genannt war.

| Fall | Ergebnis |
|---|---|
| Start (Runde 1) | zunächst **fehlgeschlagen**: Live-API lehnte `allowed_server_events` als Stringliste mit `400 invalid_type` ab (Formatänderung seit spätestens 2026-10-28, ohne Ankündigung gefunden). Behoben: `ServerEventSelector`-Objekte (`15e687a`); Startfehler-Codes jetzt im Betriebslog (`6a77063`). Anlass für den API-Wächter (`docs/phase-1-mvp.md` §1). |
| 1 Persona legt auf | Runde 1 nicht erreicht; Nachtest **bestanden** (`auflegen`). Pit: Brandt legte nach Terminvereinbarung recht schnell auf – Persona-Feinschliff in Schritt 3. |
| 2 Beenden | bestanden (`nutzer`, Abschluss in ≈ 3 s) |
| 3 Tab schließen | Runde 1: beendet, aber als `nutzer` gezählt (Chrome sendet Origin beim Beacon) → Kennzeichen `grund: "tab"` (`7abca16`). Nachtest: **nicht bestanden** – Ende als `verbindung_verloren` nach 70 s Gesprächsdauer; Endpunkt per curl geprüft (mit/ohne Origin, mit Kennzeichen → korrekt), Beacon kam offenbar nicht an. Ursache offen. Anmeldung blieb erhalten. |
| 4 Abbruch ohne Beacon | bestanden (`verbindung_verloren`; Nachlauf nicht gemessen) |
| 5 Zweiter Start | bestanden (409 ohne Provider-Aufruf, `start_abgewiesen`) |
| 6 `kill -9` während Gespräch | bestanden: nach 3 s bereit, laufende Sitzung per force_close bestätigt geschlossen, Reserve geschätzt gebucht |

**Attach an beendete Sitzung (offene Frage aus dem Nachtrag oben):** zuerst HTTP 404, Minuten
später durchgehend **HTTP 503**. Ein später Neustart hätte den Server dauerhaft gesperrt.
Behoben (`9577abd`, Plan von Codex geprüft, Umsetzung Codex, Review Claude): force_close-
Wiederholungen nach 0/5/15/30/60 s mit gemeinsamer Frist 120 s, danach Ersatzabschluss mit
voller Reserve bzw. höherer beobachteter Usage (`budget_settle` mit `unconfirmed: true`,
Oplog `abschluss_unbestaetigt`); gilt auch im laufenden Betrieb; Recovery im Hintergrund,
`/healthz` währenddessen 503. **Ersetzt** die Regel aus §3/A3, dass eine Reserve bis zur
Bestätigung gebunden bleibt (Freigabe Pit 2026-10-28). Live geprüft (kostenlos, tote Sitzung):
`/healthz` 503, nach 123 s bereit, Buchung 0,55 $ markiert.

**Restrisiko (akzeptiert):** Ist 503 ein echter Ausfall und lebt die Sitzung weiter, läuft sie
ohne unsere Frist, bis der Browser trennt; OpenAI erzwingt keine Höchstdauer. Dann sind
„1 Gespräch je Nutzer / 20 gesamt“ für tatsächlich lebende Provider-Sitzungen nicht garantiert,
und Kosten können die Reserve übersteigen. 503 gilt nie als Bestätigung. Sitzungen ohne
`provider_id` (`erzeugung_ungeklaert`) sind nicht nachbehandelt (bekannte Lücke).

**Datensparsamkeit:** `session.store = false` ausdrücklich gesetzt (`7abca16`; Standard laut
API-Referenz heute false, betrifft Forking/Aufnahme-Download – keine Aussage über sonstige
Provider-Aufbewahrung; DPA bleibt Pilotblocker).

**Offen:** Ursache Beacon (Fall 3); Nachtest der Datenkanalsperre nach der API-Formatänderung
(`allowed_client_events: []` unverändert dokumentiert, live nicht erneut geprüft);
Nachlaufzeit ohne Beacon messen. Prüfungen: 228 Tests, ruff grün.

### Nachtrag 2: Herzschlag und Sperre (2026-10-28, abends)

- **Tab ohne Beacon** (Cmd+W im eingebetteten Editor-Browser) lieferte zuvor erst nach ≈ 80 s
  `verbindung_verloren`. Neu: Herzschlag der Seite alle 5 s, Register beendet nach 15 s ohne
  Herzschlag (`herzschlag_fehlt`, Prüftakt 1 s); Seite beendet lokal bei 404/401 oder ohne
  Bestätigung für 15 s (`022ea38`, `07cdc40`, `14390a8`; Plan von Codex geprüft;
  Integrationsreview fand fehlenden Shutdown-Schließversuch nach unbestätigtem Erstversuch,
  behoben `7cd6ae5`). Ende-Anfragen im Betriebslog mit Status (`4856dab`).
- **Live (Referenz, Pits Stimme; Firefox bzw. eingebetteter Editor-Browser, Chrome nicht
  getestet):** Tab schließen ohne Beacon → `herzschlag_fehlt`, Sitzung
  33 s nach Start beendet; Tab schließen mit Beacon → `tab_geschlossen`; Wegnavigieren →
  Beacon 200, `tab_geschlossen`. Nachlauf zwischen Schließen und Ende nicht exakt gemessen
  (Schließzeitpunkt nicht protokolliert).
- **Datenkanalsperre nach API-Formatänderung bestätigt** (Prototyp, `?debug=1`): Angriffe 1–4,
  6–8 einschließlich Befehlsflut sämtlich `event_not_allowed`; Angriff 5 nicht auslösbar (kein
  offener Werkzeugaufruf), wie im Architekturversuch.
- **Lücke:** Bricht der Browser beim Schließen die Beacon-Verbindung ab, bricht aiohttp den
  Handler ab (`handler_cancellation`); das Ende läuft weiter (shield), aber der Statuseintrag
  fehlt im Betriebslog.
- **Offen:** Hintergrund-Tab > 5 min mit aktivem Gespräch (Chrome-Timerdrosselung; Erwartung
  laut Chrome-Doku unkritisch, nicht gemessen). Kosten dieser Runde ≈ 0,08 $; Abnahme gesamt
  ≈ 0,79 $. Prüfungen: 261 Tests, ruff grün.
