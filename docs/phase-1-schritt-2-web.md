# Phase 1, Schritt 2 — Web-Frontend `web/` (Plan)

Stand: 2026-10-28 · Status: **Entwurf, von Codex geprüft und eingearbeitet; Entscheidungen §5 offen** · Bezug:
[Phase-1-Plan](./phase-1-mvp.md) §2 Schritt 2, §3 · Server:
[Schritt 1](./phase-1-schritt-1-server.md) inkl. Nachträge (Herzschlag, Beacon, Wiederanlauf)

## 1. Ziel

Eine Gesprächsseite für SDRs mit **einer Persona** (Markus Brandt): anmelden, verbinden,
sprechen, hören, Live-Transkript sehen, KI-Hinweis jederzeit sichtbar, beenden. Sie ersetzt die
Testseite `agent/src/pacemaker_agent/hybrid/static/index.html`. Server, Sitzungslebenszyklus,
Budget und Sperren bleiben wie in Schritt 1; das Frontend ist **nicht vertrauenswürdig** und
erhält keine neuen Befugnisse.

Nicht in Schritt 2: Personas-Auswahl, Scoring/Ergebnisse, Verlauf, Self-Service-Login
(Schritt 5), Persistenz (Schritt 6), Latenz-HUD und Browser-Latenzmessung (Schritt 7, §4.4).

## 2. Abnahmekriterien

| # | Kriterium |
|---|---|
| W1 | Gespräch im Browser über den Server aus Schritt 1: Anmeldung, Start, Hören, Sprechen, Live-Transkript (Nutzer und Persona getrennt), Ende per Knopf, durch Auflegen der Persona, durch Zeitlimit und Inaktivität – jeweils mit verständlichem Abschlusstext in Sie-Form. |
| W2 | KI-Transparenz: Hinweis „Sie sprechen mit einer KI-Trainingsfigur“ vor dem Start und während des Gesprächs sichtbar, nicht ausblendbar. |
| W3 | Fehlerpfade mit deutscher Meldung und sauberem Aufräumen (Mikrofon aus, Peer zu, Herzschlag gestoppt): Mikrofon verweigert/fehlt, Start abgewiesen (alle `fehler`-Codes des Servers), WebRTC-Aufbau scheitert, Verbindung bricht ab (ICE `failed`/`disconnected` > Frist), Server antwortet 401/404/5xx, Netzverlust. **Beenden und Abmelden stoppen Mikrofon-Tracks, Wiedergabe und Peer sofort lokal**, unabhängig von der HTTP-Antwort; ein verspätet zurückkehrendes `getUserMedia` oder ein abgebrochener Start hinterlässt kein offenes Mikrofon. Bei 401 oder Nutzerwechsel wird das Transkript aus DOM und Speicher gelöscht. |
| W4 | Lebenszyklus gegenüber Schritt 1 unverändert: Herzschlag (5 s / lokale Frist 15 s, höchstens eine offene Anfrage, Zeitlimit je Anfrage, Kontext je Gespräch), Beacon mit `grund: "tab"`, Abbruch bei 401/404. Verspätete Antworten eines alten Gesprächs wirken nie auf ein neues. |
| W5 | Sicherheit: keine Secrets, Provider-Keys, Provider-IDs **oder Persona-Instruktionen** im Bundle oder im Browser – auch nicht in Datenkanal-Ereignissen (§4.1); nur Same-Origin-Aufrufe; keine Drittanbieter-Ressourcen (Schriften, CDNs, Analytics); CSP ohne `unsafe-inline`/`unsafe-eval`; kein Speichern von Transkripten in `localStorage`, `sessionStorage`, IndexedDB oder Cookies. |
| W6 | Datensparsamkeit: Transkript nur im Speicher der Seite, verworfen bei neuem Start, Abmelden oder Neuladen. Kein Audio-Mitschnitt, keine Audioanalyse. |
| W7 | Prüfungen grün (aus `web/`): Typecheck (`strict: true`), eslint, prettier `--check`, `pnpm build`; Logiktests (§3.6); Agent-Tests und ruff wie in Schritt 1. |
| W8 | Manuelle Prüfung nach CLAUDE.md (Mikrofonfreigabe, Verbindungsaufbau, Audiowiedergabe, Disconnect; HUD entfällt, §4.4) in den verbindlichen Browsern aus §5.3 (je Browser Grundgespräch und Fehlerpfade), einmal Gespräch > 5 min im Hintergrund-Tab in Chrome (Timerdrosselung, offen aus Schritt 1); Prüfung, dass der Browser keine `session.*`-Ereignisse mehr erhält. Region `referenz`, Pits Stimme, als Referenzlauf gekennzeichnet; Schätzung ≈ 0,80 $, Ist-Kosten dokumentiert. |

## 3. Festlegungen

### 3.1 Technik und Werkzeuge

- Vite + TypeScript, **kein UI-Framework**, keine Laufzeitabhängigkeiten (CLAUDE.md).
  Entwicklungsabhängigkeiten: `vite`, `typescript`, `@types/node`, `eslint`, `@eslint/js`,
  `typescript-eslint`, `prettier`. `pnpm-lock.yaml` versioniert; Versionen beim Anlegen
  festlegen und im Nachtrag dokumentieren.
- Node **≥ 22.18** (Type-Stripping standardmäßig aktiv) und pnpm fehlen auf Pits Rechner (geprüft 2026-10-28; nur eine Codex-interne Node
  vorhanden). Installation per Homebrew (`brew install node@22 pnpm`) durch Claude nach Pits
  Freigabe (§5). Codex hat kein Netz: Claude legt Gerüst und `node_modules` im Worktree an,
  bevor Codex übernimmt.
- `package.json`-Skripte: `dev`, `build`, `typecheck` (`tsc --noEmit`), `lint`, `format`,
  `format:check`, `test`.

### 3.2 Auslieferung und Herkunft

- **Lokal und Abnahme:** Der Hybrid-Server liefert das gebaute `web/dist` aus (gleiche
  Herkunft, keine CORS-Regeln, Cookie `SameSite=Strict` bleibt gültig). Pfad über
  `PACEMAKER_WEB_DIST` (explizit; fehlt er oder fehlt `index.html` darin → Startabbruch mit
  verständlicher Meldung, kein stiller Rückfall auf die Testseite). Ohne Verzeichnislisten,
  ohne Symlinks im Build (Prüfung beim Start), `index.html` mit `no-store`, gehashte Assets
  mit langer Cache-Dauer – die Sicherheits-Middleware setzt `no-store` dafür nicht mehr pauschal.
- **Produktion:** aiohttp empfiehlt `add_static()` nur für die Entwicklung
  ([Referenz 3.14.3](https://docs.aiohttp.org/en/v3.14.3/web_reference.html#aiohttp.web.UrlDispatcher.add_static)).
  Im Pilot liefert der ohnehin nötige TLS-Proxy `web/dist` unter derselben Herkunft aus und
  leitet `/api` und `/healthz` weiter; Auswahl und Konfiguration mit dem EU-Hosting in Schritt 7.
- CSP für die Seite: `default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self';
  media-src 'self' blob:; img-src 'self'; base-uri 'none'; form-action 'none';
  frame-ancestors 'none'`. Vite-Build ohne Inline-Anteile: nur externe Module und CSS, keine
  Inline-Handler, `build.assetsInlineLimit: 0`, `build.modulePreload.polyfill: false`; den
  Build auf Inline-Anteile prüfen ([Vite-CSP](https://vite.dev/guide/features.html#content-security-policy-csp)).
  WebRTC zu OpenAI fällt nicht unter `connect-src` (keine Fetch-/XHR-/WebSocket-Verbindung);
  im Browser bestätigen.
- **Entwicklung:** bevorzugt `pnpm build --watch` gegen 8080 (gleiche CSP wie Abnahme).
  Alternativ `pnpm dev` mit Vite-Proxy für `/api` und `/healthz` auf `127.0.0.1:8080`.
  Der Browser sendet dabei Origin `http://localhost:5173`; Server dafür mit
  `PACEMAKER_PUBLIC_ORIGIN=http://localhost:5173` starten (nur `DEV_LOOPBACK`; CSS-HMR braucht
  Inline-Stile, CSP gilt dort nicht).
- Die Testseite und ihre CSP-Hash-Berechnung entfallen nach Abnahme von W1–W8 im selben Schritt.

### 3.3 Aufbau der Seite

- Ansichten: **Anmeldung** → **Bereit** (KI-Hinweis, Headset-Empfehlung wegen Echo und
  Rollenbruch, Kontingent-Hinweis aus `/api/status`, Start-Knopf) → **Gespräch** (Status,
  Restzeit, Live-Transkript, Beenden) → **Beendet** (Abschlusstext, Transkript
  bleibt bis zum nächsten Start sichtbar, „Neues Gespräch“).
- Restzeit: Server liefert die maximale Dauer in der Startantwort (neues Feld
  `max_dauer_s`); Anzeige ist Information, Durchsetzung bleibt serverseitig.
- Abschlusstexte je Ende: Auflegen der Persona, eigenes Beenden, Zeitlimit, Inaktivität,
  Verbindungsverlust, Server nicht erreichbar, erneute Anmeldung nötig. Die Seite erfährt Ende
  und Grund aus der **Herzschlag-Antwort** (§4.2), nicht mehr aus dem Datenkanal. „Beendet“
  verspricht keine bestätigte Schließung beim Provider (Schritt-1-Nachtrag).
- Stimme: **keine Auswahl** in der Oberfläche; der Server legt die Stimme der Persona fest
  (Entscheidung Pit, §5.1). Das Feld `stimme` im Start-Request wird danach mit 400 abgewiesen.
- Barrierearmut: semantisches HTML, Fokusführung, `aria-live` für Status und Transkript,
  Tastaturbedienung, ausreichender Kontrast. Responsive bis Tablet; Smartphone nicht Ziel.

### 3.4 Audio

- Audiopfad **unverändert gegenüber Prototyp und Testseite**: `getUserMedia({ audio: true })`,
  ein Audio-Track, Datenkanal `oai-events`, Angebot nach ICE-Sammlung (höchstens 5 s), Ausgabe
  über `<audio autoplay>` nach Nutzergeste. Keine Pegelanzeige, kein AudioContext, keine eigene
  Verarbeitung. Damit ändert Schritt 2 den Audiopfad nicht, und es ist kein Latenz-
  Regressionsnachweis nötig. Jede Abweichung davon (z. B. andere Constraints) braucht einen
  präregistrierten Vergleich nach CLAUDE.md und wird vorher geklärt.

### 3.5 Code-Struktur

- `src/api.ts` (typisierte Aufrufe, Zeitlimits, Fehlercodes → Meldungen),
  `src/gespraech.ts` (WebRTC, Transkript-Ereignisse, Lebenszyklus als Zustandsautomat mit
  Kontext je Gespräch; jeder asynchrone Schritt prüft danach, ob sein Kontext noch aktuell ist), `src/herzschlag.ts` (reine Logik, testbar mit injizierter Uhr und
  injiziertem `fetch`), `src/ansicht.ts` (DOM), `src/main.ts`.
- Übernahme der in Schritt 1 geprüften Logik aus der Testseite (Herzschlag, Beacon,
  Aufräumen), nicht neu erfinden.

### 3.6 Tests

- Logiktests für `herzschlag.ts` und den Zustandsautomaten mit dem **Test-Runner von Node**
  (`node --test`, TypeScript per Type-Stripping ab Node 22.18), damit kein Test-Framework als
  neue Abhängigkeit nötig ist. Voraussetzungen: nur löschbare Typsyntax
  (`erasableSyntaxOnly`), explizite `.ts`-Importe (`allowImportingTsExtensions`, `noEmit`),
  keine Enums oder Pfad-Aliase; Typecheck schließt die Tests ein. Fälle: Takt, lokale Frist,
  hängende Anfrage, 401/404/5xx, Endstatus mit Grund, verspätete Antwort nach Neustart eines
  Gesprächs, Beenden bei hängendem `/api/end`, verspätetes `getUserMedia`, Aufräumen.
- Keine Browser-Testsuite in Schritt 2 (Playwright o. ä. wäre eine neue Abhängigkeit);
  Browserverhalten manuell nach W8.

## 4. Server-Anpassungen

1. **Datenkanal ohne Sitzungsressource (P1, betrifft schon Schritt 1).** `session.started` und
   `session.closed` enthalten laut SDK die aufgelöste Sitzung samt `id`, `instructions`
   (Persona-Prompt mit verdeckten Schmerzpunkten) und `delegation`
   (`pipecat/services/openai/live/events.py`, `SessionResource`). Der Browser erhält sie heute.
   Allowlist auf `session.input_transcript.delta` und `session.output_transcript.delta`
   reduzieren; Ende erfährt die Seite über den Herzschlag. Synthetisch prüfen, dass im Browser
   kein `session.*`-Ereignis mehr ankommt (W8). (Claude, `live.py`)
2. **Herzschlag liefert Status (Codex, `sessions.py`; Claude, `app.py`).** Antwort 200
   `{"zustand": "laufend"|"endend"|"beendet", "grund": <EndReason|null>}` für die eigene
   `session_ref`; abgeschlossene Sitzungen bleiben dafür begrenzt im Speicher (z. B. 10 min,
   höchstens 2 × `max_parallel` Einträge, nur Zustand und Grund). Unbekannt oder fremd → 404
   (gleich behandelt). `last_seen` wird nur bei laufenden Sitzungen aktualisiert. Die Seite
   beendet den Herzschlag erst nach einem Endzustand.
3. **Auslieferung `web/dist`** (§3.2) samt CSP `'self'`, Cache-Regeln und Startprüfung;
   Testseite nach Abnahme entfernen. (Claude, `app.py`, `server.py`)
4. **Startantwort** um `max_dauer_s`. (Claude)
5. **Feste Stimme** je Persona nach Pits Entscheidung (§5.1): Serverkonstante bzw.
   `PACEMAKER_VOICE` aus der Allowlist, Client-Feld `stimme` → 400. (Claude)
6. Latenz: kein HUD in Schritt 2; Audiopfad unverändert (§3.4). Browser-E2E-Messung mit eigener
   Instrumentierung gehört zur Präregistrierung in Schritt 7.
7. Hinweis für später: `SessionResource.expires_at` könnte das Restrisiko „Sitzung läuft ohne
   unsere Frist weiter“ (Schritt-1-Nachtrag) begrenzen; im Sideband auswerten und prüfen.

## 5. Entscheidungen für Pit

1. **Stimme von Brandt** fest auf dem Server statt Auswahl in der Oberfläche. Empfehlung: fest;
   welche der 8 Stimmen, entscheidet Pit (bisher API-Vorgabe).
2. **Node 22 und pnpm per Homebrew installieren** (lokal, kostenlos). Empfehlung: ja.
3. **Browser-Umfang für den Pilot:** Chrome/Edge und Firefox verbindlich, Safari nach Aufwand.
   Empfehlung: so.

## 6. Review Codex (2026-10-28), eingearbeitet

- P1: Sitzungsressource im Datenkanal (§4.1); sofortiges lokales Beenden (W3).
- P2: Endstatus über den Herzschlag (§4.2); Produktion über TLS-Proxy, Cache-Middleware
  (§3.2); Vite-CSP-Einstellungen (§3.2); Node ≥ 22.18, `@types/node`, Testvoraussetzungen
  (§3.6); Latenz: Audiopfad bleibt unverändert statt Nachweis zu vertagen (§3.4); feste Stimme
  serverseitig durchgesetzt (§4.5).
- P3: Pegelanzeige gestrichen; W8 an Browser-Umfang gekoppelt; Kosten neu geschätzt.

## 7. Aufteilung und Ablauf

1. Codex prüft diesen Plan; Einarbeitung; Pits Entscheidungen §5.
2. Claude: Node/pnpm, Gerüst `web/` (Vite, TS strict, eslint, prettier, Skripte, Lockfile),
   Server-Anpassungen §4.1, §4.3–§4.5. Codex parallel: §4.2 im Register.
3. Codex: Seite nach §3.3–§3.6 im eigenen Worktree auf Basis des Gerüsts.
4. Cross-Review, alle Prüfungen durch Claude, Merge; Live-Abnahme W8 (≈ 0,80 $, Kleinlauf).
5. Ergebnis als Nachtrag; CLAUDE.md-Befehle für `web/` prüfen und anpassen.
