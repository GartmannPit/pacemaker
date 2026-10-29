# Phase 1, Schritt 5/6 — Datenmodell und Mandantentrennung (Plan)

Stand: 2026-10-29 · Status: **Rahmenplan FREIGEGEBEN (Pit, 2026-10-29)** nach Codex-Review (Runde 5, §12);
Umsetzung erst in Schritt 5/6 nach Gates G5/G6 · Bezug: [Phase-1-Plan](./phase-1-mvp.md) §1, §2 (Schritte 5
und 6), §4, §5, §6 · [Strategie](../Pacemaker.md) §4.4 · [Schritt 1](./phase-1-schritt-1-server.md) ·
[Schritt 2](./phase-1-schritt-2-web.md) §9, §10

## 1. Ziel und Abgrenzung

Das Datenmodell ist **von Anfang an mandantenfähig** (Strategie §4.4), die **Funktion** bleibt
in Phase 1 bei der Mindesttrennung (Plan §5): Nutzer lesen und ändern ausschließlich eigene
Sitzungen und Ergebnisse; kundenübergreifender Zugriff ist ausgeschlossen; Kunden-Admins sehen
nichts. Rollen, Manager-Sicht und kundenkonfigurierbare Frameworks und Personas folgen in
Phase 2 als zusätzliche Policies und Tabellen, ohne Umbau der vorhandenen Daten.

Dieser Plan legt **keinen Anbieter** fest (Entscheidung Pit, AVV vorher). **Persistenz erst
nach beschlossenen Fristen und Löschwegen** (Plan §5), gestaffelt nach §8 (Freigabegates).
Umsetzung in Schritt 5 (Mandanten, Nutzer, Anmeldung, Rollen, RLS, Journal-Kompaktierung) und
Schritt 6 (Gesprächsdaten, Auswertung, Löschjob), jeweils mit eigenem Schrittplan.

## 2. Ausgangslage (Code, Stand `221484c`)

- Nutzer in einer JSON-Datei (`PACEMAKER_USERS_FILE`, `hybrid/auth.py`): `id` (`token_hex(8)`),
  `name`, `password_hash`, `disabled`, `login_version`. **Kein Mandantenbezug.** `resolve()`
  gleicht bei jeder Anfrage Sperre und `login_version` neu ab.
- Anmeldungen nur im Speicher, Ablauf über die monotone Prozessuhr; Neustart meldet alle ab.
- Sitzungslebenszyklus und Budget im append-only Journal (`journal.jsonl`) mit `local_id`,
  `user_id`, `provider_id`, Zustand, Grund; Wiederanlauf über `recover()`. Abgeschlossene
  Sitzungen werden aus dem Register entfernt und beim Neustart ausgesondert.
- Nach unbestätigtem Ersatzabschluss gilt die Sitzung als `beendet`; die Buchung ist als
  `unconfirmed` markiert.
- Transkript nur im Speicher (`hybrid/sideband.py`); Betriebslog mit Feld-Allowlist, darin
  `session_ref`, keine Nutzer-ID.

## 3. Begriffe

- **Mandant (`tenant`)**: eine Kundenorganisation. Jeder Nutzer gehört in Phase 1 genau einem
  Mandanten an. Pits eigene Tests und bestehende Nutzer laufen im internen Mandanten
  `onetry-intern`.
- **Mandantendaten**: jede Zeile mit Bezug zu Nutzer, Gespräch oder Kundenkonfiguration. Sie
  trägt `tenant_id` und, wo sie einem Nutzer gehört, `user_id` (auch in Kindtabellen, §4.2).

## 4. Datenmodell

### 4.1 Identitäten

Bestehende Identitäten bleiben erhalten (keine UUID-Umstellung): Schlüssel als `text` mit
Formatprüfung (`CHECK`). `users.id` übernimmt die heutige ID; `conversations.id` ist die
`local_id` aus dem Journal; neue Mandanten erhalten eine zufällige ID im selben Stil. Die
Migration legt `onetry-intern` an und ordnet alle bestehenden Nutzer zu. Ein Reset der
Testdaten wäre eine ausdrückliche Entscheidung Pits.

### 4.2 Tabellen

| Tabelle | Inhalt | Schritt |
|---|---|---|
| `tenants` | `id`, `name`, `status`, `created_at` | 5 |
| `users` | `id`, `tenant_id`, Login-Name, `password_hash`, `disabled`, `login_version`, `status` (`aktiv`/`loeschung`), `created_at`, `UNIQUE (tenant_id, id)` | 5 |
| `logins` (nur falls persistiert, §10) | SHA-256 der zufälligen Login-ID, `tenant_id`, `user_id` (zusammengesetzter FK auf `users (tenant_id, id)`), `login_version`, `expires_at` (absolute Wanduhrzeit) | 5 |
| `conversations` | `id`, `tenant_id`, `user_id`, Persona und Version, Szenario, Start, Ende, Endgrund, **Abschluss** (`bestaetigt`/`unbestaetigt`), **Vollständigkeit** (`vollstaendig`/`unvollstaendig`/`transkript_verloren`), **Auswertung** (`ausstehend`/`ausgewertet`/`nicht_auswertbar` + Grund), Kosten in Mikro-Dollar mit `estimated`/`unconfirmed` aus dem Budget, `expires_at`, `UNIQUE (tenant_id, user_id, id)` | 6 |
| `transcripts` | Turns (Sprecher, Text, Zeit) | 6 |
| `evaluations` | Framework-ID und -Version, Persona-Version, Scoring-Version, Gesamt- und Maximalpunkte; nur bei `ausgewertet` | 6 |
| `evaluation_criteria` | je Framework-Feld: stabiler Schlüssel `criterion_key` (z. B. `bant.budget`), **Live-Status** (`nicht_angesprochen`/`angesprochen`), **Abgleich** (`geklaert`/`teilweise`/`offen`, Schritt 2 §10), Wert aus der Persona, Beleg (Turn, Zeit, Ausschnitt), Tipp; `UNIQUE (conversation_id, criterion_key)` | 6 |
| `point_entries` | Punktposten: Art (`ereignis`/`hilfe`/`transkript`), Punkte, Zeit, fachlicher Schlüssel `event_key`, `UNIQUE (conversation_id, event_key)` | 6 |
| `key_moments` | Ausschnitt, Begründung | 6 |
| `tenant_frameworks` (reserviert) | kundenspezifisches Framework | Phase 2 |

- **Kindtabellen** (`transcripts` bis `key_moments`) tragen `tenant_id`, `user_id`,
  `conversation_id` und verweisen zusammengesetzt auf `conversations (tenant_id, user_id, id)`.
  So kann keine Zeile auf ein Gespräch eines anderen Nutzers oder Mandanten zeigen, die
  Policies bleiben einheitlich (§6.2), und Nutzerlöschung erreicht alle Tabellen direkt.
  Verworfen: Kindtabellen ohne `user_id` mit `EXISTS`-Policy auf das Gespräch.
- `conversations (tenant_id, user_id)` verweist auf `users (tenant_id, id)`.
- **Standard-Frameworks** (z. B. BANT) sind in Phase 1 versioniert im Code; `evaluations`
  speichert ID und Version. Kundenkonfiguration bleibt Phase 2.
- **Punkte und Hilfen:** `event_key` ist fachlich stabil, z. B. `hilfe:<hilfe_id>:<stufe>`,
  `transkript`, `ereignis:<ereignis_id>`; derselbe Kauf ergibt immer denselben Schlüssel.
  Im Gespräch bucht das Register Kauf und Freischaltung gemeinsam unter der Sitzungssperre im
  Speicher (ein Kauf je Schlüssel; Tipp bzw. Transkript erst danach ausgeliefert); persistiert
  wird mit dem Abschluss (§4.3). Nach einem Absturz ist das Gespräch ohnehin nicht auswertbar.
- **Notizen** der Auswertungsseite werden für den serverseitigen Abgleich **flüchtig
  übermittelt und nicht gespeichert**; nur das Abgleichergebnis landet in
  `evaluation_criteria`. Eine Speicherung der Notizen wäre eine eigene Entscheidung mit Frist.
- Vertragstests mit ersetztem Auswertungsmodell (lokal): doppelter Hilfekauf, Transkript
  freischalten, Abgleich je Kriterium, Gesamt- und Maximalpunkte.
- **Score** nur bei `vollstaendig` und bestätigtem bzw. regulärem Ende; sonst
  `nicht_auswertbar` mit Grund und ohne `evaluations`-Zeile (Plan §4).
- **Nie gespeichert:** Rohaudio (Plan §5), SDP, Provider-Schlüssel, aus Stimme oder Prosodie
  abgeleitete Merkmale (Emotionserkennung ausgeschlossen, CLAUDE.md).

### 4.3 Übergang Journal → `conversations` (wiederanlauffest)

Budget und Sitzungslebenszyklus bleiben in Phase 1 im Journal (eine Prozessinstanz,
geprüfter Wiederanlauf). Die Datenbank wird beim Abschluss geschrieben, nicht beim Start
(kein zusätzlicher Datenbankschritt im Startpfad).

- Der Journal-Startsatz erhält zusätzlich `tenant_id`, Persona/Szenario und Version sowie die
  Startzeit (Wanduhr), damit der Datensatz auch nach einem Absturz vollständig ist.
- Nach Abschluss und Budgetbuchung schreibt das Register `conversations` **und alle
  Kindzeilen in einer einzigen Transaktion** und hängt danach `conversation_synced` ans
  Journal. Kindzeilen haben stabile Schlüssel (`(conversation_id, turn_index)`,
  `criterion_key`, `event_key`).
- **Eine vorhandene `conversations`-Zeile beweist eine vollständige Übertragung** (alles oder
  nichts). Jede Wiederholung prüft zuerst diese Zeile: Existiert sie, wird nichts geschrieben,
  nur `conversation_synced` nachgetragen (`ON CONFLICT (id) DO NOTHING`, kein `DO UPDATE`).
  Rekonstruierte Ersatzdaten überschreiben damit nie vollständigere Daten.
- `recover()` behält abgeschlossene Sitzungen ohne `conversation_synced` und überträgt sie
  erneut. Fehlt die Zeile, ist das Transkript verloren: Ersatzdatensatz mit Vollständigkeit
  `transkript_verloren`, Auswertung `nicht_auswertbar`, Kosten aus dem Budget.
- Welche Zeilen beim Abschluss und welche bei der späteren Auswertung entstehen, regelt §6.4.
- Für gelöschte oder in Löschung befindliche Nutzer wird nicht übertragen (§7.1).
- Ist die Datenbank nicht erreichbar, bleibt der Satz im Journal; Wiederholung mit Backoff,
  Betriebslog `db_sync_ausstehend`. Neue Starts bleiben davon unberührt; ob das so bleiben
  soll, entscheidet der Schrittplan 6.
- Fehlertests (lokal): Absturz vor/nach Budgetbuchung, vor/nach Datenbank-Commit, vor/nach
  `conversation_synced`; Datenbankausfall; doppelte Übertragung. Nach jedem Fall: genau ein
  Datensatz, und Inhalt, Status, Kosten und Kindzeilen einer bereits committeten Übertragung
  sind unverändert.

## 5. Zugriffsschicht im Server

- **Nur der Server spricht mit der Datenbank.** Kein Datenbankzugriff aus dem Browser,
  keine öffentliche Datenbank-API.
- Ein schmales Modul (z. B. `hybrid/store.py`) kapselt alle Abfragen, analog zur
  Provider-Kapselung (CLAUDE.md). Handler erhalten nur Funktionen wie
  `list_conversations(ctx)`, nie eine rohe Verbindung.
- Jede Anfrage läuft in einer Transaktion mit Mandanten- und Nutzerkontext aus der geprüften
  Anmeldung, nie aus Anfragefeldern:
  `SELECT set_config('app.tenant_id', $1, true), set_config('app.user_id', $2, true)`
  (`true` = nur für die Transaktion, entspricht `SET LOCAL`). Sitzungsweite `SET`-Befehle
  sind verboten; bei Connection-Pooling würden sie an fremde Anfragen weitergereicht.
- Zusätzlich filtert jede Abfrage selbst auf `tenant_id` und `user_id` (erste Linie);
  RLS (§6) ist die zweite Linie, falls ein Filter fehlt.
- Asynchroner Treiber, damit der Event-Loop nicht blockiert (CLAUDE.md); Auswahl
  (`asyncpg` oder `psycopg` 3 async) mit Abhängigkeits- und Datenflussprüfung in Schritt 5.
- Anwendungslogs enthalten bei Datenbankfehlern nur SQLSTATE und einen festen Fehlercode,
  nie Meldungstext, `DETAIL`, Parameter oder Treiberausnahmen (wie heutige Oplog-Allowlist).

## 6. RLS-Konzept

### 6.1 Rollen

| Rolle | Login | Genutzt von | Zweck | Rechte |
|---|---|---|---|---|
| `onetry_owner` | nur Migration | Migrationen | Eigentümer von Schema, Tabellen, Views und Kontextfunktionen (§6.2) | kein Laufzeitzugriff |
| `onetry_auth` | `NOLOGIN` | niemand direkt | Eigentümer **nur** der beiden Anmeldefunktionen (§6.3) | Spalten-`SELECT` auf Anmeldespalten von `users` und `logins`, eigene Policy |
| `onetry_app` | ja | Server, normale Zugriffsschicht | Anfragen der Nutzer | DML nach §6.2; `EXECUTE` auf die Anmeldefunktionen |
| `onetry_admin` | ja | nur Admin-CLI | Mandanten und Nutzer anlegen, sperren, **Löschung beauftragen** (§7.1) | `tenants`, `users`, `logins`; **kein** Zugriff auf Gesprächstabellen |
| `onetry_deleter` | ja | nur Löschauftrags-Task im Server, eigene Zugangsdaten und eigene Verbindung | protokollierte Löschaufträge vorbereiten (nur Richtung `loeschung`, §7.3) und Daten von Nutzern bzw. Mandanten **im Status `loeschung`** entfernen | Schlüsselspalten, einseitiges `UPDATE` und `DELETE` über eigene Policies (§6.2) |
| `onetry_retention` | ja | nur Fristlöschjob | abgelaufene Zeilen löschen | Schlüsselspalten und `DELETE` über eigene Policies (§6.2) |

Für **alle** Rollen außer `onetry_owner` gilt: kein Superuser, kein `BYPASSRLS`, keine
Mitgliedschaft in anderen OneTry-Rollen (kein `SET ROLE`); `onetry_app`, `onetry_admin`,
`onetry_deleter` und `onetry_retention` sind zudem nicht Eigentümer von Tabellen, Schema oder
Funktionen. `FORCE ROW LEVEL SECURITY` bindet auch den Tabelleneigentümer, **nicht** aber
Superuser und Rollen mit `BYPASSRLS`.

### 6.2 Policy-Matrix (Phase 1)

Kontextfunktionen (`SECURITY INVOKER`, Eigentümer `onetry_owner`):
`ctx_tenant()` liest `nullif(current_setting('app.tenant_id', true), '')`,
`ctx_user()` liest `nullif(current_setting('app.user_id', true), '')`. Jede Policy für
`onetry_app` verlangt **beide** Werte (auch `tenants`). Ohne vollständigen Kontext ergibt das
NULL, die Policies lassen dann nichts durch. (`nullif`, weil eine Variable, die in der
Verbindung schon einmal per `SET LOCAL` gesetzt war, danach als leerer String gelesen wird,
sofern kein sitzungsweiter Wert existiert; sitzungsweite Werte sind nach §5 verboten.)
`SELECT`/`DELETE` nutzen `USING`, `INSERT` nutzt `WITH CHECK`, `UPDATE` beides. Auf jeder
Tabelle `ENABLE` und `FORCE ROW LEVEL SECURITY`. „Eigen“ heißt unten
`tenant_id = ctx_tenant() AND user_id = ctx_user()` (bei `users`: `id = ctx_user()`).

| Tabelle | `onetry_app` | Weitere Rollen |
|---|---|---|
| `tenants` | `SELECT`: `id = ctx_tenant() AND ctx_user() IS NOT NULL` | `onetry_admin`: alle Befehle; `onetry_deleter`: `SELECT` (`id`, `status`) ohne Zeileneinschränkung, `UPDATE` (`status`) nur mit `WITH CHECK (status = 'loeschung')`, `DELETE` bei `status = 'loeschung'`; FK `users.tenant_id → tenants.id` mit `ON DELETE RESTRICT` verhindert das Löschen nicht leerer Mandanten |
| `users` | `SELECT` eigen; Passwortänderung atomar mit `login_version + 1` und Login-Widerruf (Ausgestaltung Schrittplan 5) | `onetry_auth`: `SELECT` ohne Zeileneinschränkung, nur Anmeldespalten; `onetry_admin`: alle Befehle; `onetry_deleter`: `SELECT` (`id`, `tenant_id`, `status`, `disabled`, `login_version`) **ohne Zeileneinschränkung** (auch für die Leerheitsprüfung eines Mandanten), `UPDATE` (`status`, `disabled`, `login_version`) nur mit `WITH CHECK (status = 'loeschung' AND disabled)`, `DELETE` bei `status = 'loeschung'` |
| `logins` | `SELECT` (Schlüsselspalten), `INSERT`, `DELETE` (Abmelden) eigen | `onetry_auth`: `SELECT`; `onetry_admin`: `SELECT` (Schlüsselspalten)/`DELETE` ohne Zeileneinschränkung; `onetry_deleter`: `SELECT` (Schlüsselspalten)/`DELETE`, wenn der Nutzer `status = 'loeschung'` hat; `onetry_retention`: `SELECT`/`DELETE` bei `expires_at <= now()` |
| `conversations` | `SELECT`, `INSERT` eigen; `UPDATE` eigen nur auf Spalten `auswertung`, `auswertung_grund` | `onetry_retention`: `SELECT`/`DELETE` bei `expires_at <= now()`; `onetry_deleter`: `SELECT`/`DELETE`, wenn der Nutzer `status = 'loeschung'` hat |
| `transcripts`, `point_entries` | `SELECT`, `INSERT` eigen (`point_entries` auch bei der Auswertung, §6.4) | wie `conversations` (Kinder zusätzlich per Cascade) |
| `evaluation_criteria` | `SELECT`, `INSERT` eigen; `UPDATE` eigen nur auf `abgleich`, `wert`, `beleg`, `tipp` | wie `conversations` |
| `evaluations`, `key_moments` | `SELECT`, `INSERT` eigen | wie `conversations` |

- **Schlüsselspalten statt Inhalte:** Ein gezieltes `DELETE … WHERE` braucht Leserecht auf die
  Bedingungsspalten und eine passende `SELECT`-Policy. `onetry_deleter`, `onetry_retention`
  und (bei `logins`) `onetry_admin` erhalten `SELECT` nur auf Spalten wie `id`, `tenant_id`,
  `user_id`, `status`, `expires_at` (Spalten-Grants), nie auf Text-, Beleg- oder
  Punktespalten. Kein `RETURNING` über Inhaltsspalten.
- Die `onetry_deleter`-Policy prüft den Nutzerstatus über eine Unterabfrage auf `users`
  (`user_id IN (SELECT id FROM users WHERE status = 'loeschung')`); dafür die
  `users`-Policy für `onetry_deleter` oben. Damit kann der Löschpfad nur Daten beauftragter
  Löschungen entfernen.
- **Einseitiges `UPDATE`:** `onetry_deleter` kann Nutzer und Mandanten nur **in** den Status
  `loeschung` versetzen (sperren, `login_version` erhöhen), nie zurück. Policy ausdrücklich
  `FOR UPDATE … USING (true) WITH CHECK (…)`, getrennt von den statusgebundenen
  Lösch-Policies; ein `USING (status = 'loeschung')` würde gerade die Vorbereitung aktiver
  Nutzer verhindern. Er braucht das, damit
  der Server einen protokollierten, aber noch nicht vorbereiteten Auftrag nach Absturz oder
  Restore selbst nachholen kann (§7.3). Restrisiko: Ein kompromittierter Server könnte beliebige
  Nutzer zur Löschung markieren; jede solche Markierung ohne Protokolleintrag schreibt der Server
  als Betriebslog-Alarm, und D7 prüft, dass der Server nur protokollierte Aufträge vorbereitet.
- Für Fristlöschung und Löschauftrag reicht ein `DELETE`-Grant allein nicht: Ohne eigene
  Policy sieht die Rolle unter RLS nichts; mit `BYPASSRLS` fiele die Begrenzung weg.
- Indizes: `(tenant_id, user_id, …)` auf Nutzer- und Kindtabellen, `(tenant_id, id)` auf
  `users`, `(status)` auf `users`, `(expires_at)` für den Löschjob, Indizes für alle
  zusammengesetzten Fremdschlüssel.
- Views nur mit `security_invoker = true` (Postgres ≥ 15, Versionsangabe vor Umsetzung gegen
  die Doku prüfen). Ohne diese Option gelten Rechte und RLS-Lage des View-Eigentümers.
- **Phase 2:** Manager-Sicht als zusätzliche Policy mit Rollenprüfung (z. B. `memberships`),
  ohne Änderung der Datenzeilen.

### 6.3 Anmeldung vor dem Kontext

Zwei Abfragen brauchen Daten, bevor ein Kontext existiert: Nutzer per Login-Name finden und,
falls Logins persistiert werden, Login per Cookie-Hash auflösen. Dafür genau zwei Funktionen:

- `SECURITY DEFINER`, Eigentümer `onetry_auth`; `SECURITY DEFINER` umgeht RLS nicht, daher
  gilt für `onetry_auth` eine eigene `SELECT`-Policy auf `users`/`logins`.
- `SET search_path = pg_catalog, pg_temp` mit `pg_temp` ausdrücklich am Ende, alle Objekte
  schemaqualifiziert.
- `REVOKE EXECUTE … FROM PUBLIC`, `GRANT EXECUTE … TO onetry_app`.
- Rückgabe nur für genau einen normalisierten Namen bzw. genau einen Hash: `id`, `tenant_id`,
  `password_hash`, `disabled`, `login_version`, `status` (bzw. Login-Zeile mit Ablauf).
  Keine Listen.
- Danach wie heute: bei jeder Anfrage Sperre, Status, `login_version` und Ablauf neu prüfen.

### 6.4 Schreibvertrag Abschluss und Auswertung

| Tabelle | entsteht beim Abschluss (§4.3) | bei der Auswertung |
|---|---|---|
| `conversations` | ja, `auswertung = 'ausstehend'` oder `'nicht_auswertbar'` | nur `UPDATE` von `auswertung`, `auswertung_grund` |
| `transcripts` | ja | nein |
| `point_entries` | ja: Ereignisse, Hilfen, Transkript (`ereignis:…`, `hilfe:…`, `transkript`) | `INSERT` der Abgleichposten mit stabilen Schlüsseln (`kriterium:<criterion_key>`, `termin`) |
| `evaluation_criteria` | ja, mit Live-Status; `abgleich`, `wert`, `beleg`, `tipp` leer | nur `UPDATE` dieser vier Spalten |
| `evaluations`, `key_moments` | nein | `INSERT` |

- **Auslöser:** Die Auswertung startet, wenn die Seite die Notizen übermittelt (flüchtig,
  §4.2). Ohne Notizen bis zu einer Frist (Schrittplan 6) wird ohne Notizen ausgewertet.
- **Ablauf:** Modellaufruf **außerhalb** jeder Transaktion. Danach eine Transaktion:
  `UPDATE conversations SET auswertung = 'ausgewertet' WHERE id = … AND auswertung = 'ausstehend'`
  (beansprucht die Zeile mit Zeilensperre); trifft das 0 Zeilen, Abbruch ohne Schreiben. Sonst
  im selben Commit `evaluations`, `key_moments`, die Kriterienspalten und die Abgleichposten
  schreiben. `evaluations` speichert Gesamt- und Maximalpunkte; Gesamtpunkte = Summe aller
  `point_entries` des Gesprächs (Test D11). Die Punktregeln sind versioniert
  (Scoring-Version in `evaluations`).
- Zwei gleichzeitige Auswertungen: Die zweite wartet auf die Zeilensperre, trifft danach
  0 Zeilen und schreibt nichts (ein Modellaufruf ist dann verschwendet, aber nichts doppelt).
  Das setzt Isolation `READ COMMITTED` voraus; Isolation und Fehlerbehandlung legt Schrittplan 6
  fest.
- Eine Wiederholung der Abschlussübertragung (§4.3, `DO NOTHING`) berührt diese Spalten nie.

## 7. Aufbewahrung und Löschung

**Löschgraph.** `conversations` ist Elternzeile aller Gesprächsdaten; Kindtabellen hängen mit
`ON DELETE CASCADE` daran. Damit ein Gespräch keine noch gültigen Ergebnisse mitnimmt, gilt
`conversations.expires_at` = späteste Frist seiner Kinder; Kinder mit kürzerer Frist
(`transcripts`) löscht der Job vorher einzeln. Das Modul `store.py` setzt die Fristen; ein Test
prüft die Bedingung, weil Postgres sie nicht tabellenübergreifend erzwingt.

- **Fristen** setzt Pit (Plan §5); Gates siehe §8. Ein täglicher Job mit `onetry_retention`
  löscht abgelaufene Zeilen.

### 7.1 Nutzerlöschung (wiederanlauffest)

Die Admin-CLI (`onetry_admin`) beauftragt; der Server führt mit `onetry_deleter` aus, weil nur
er Register und Journal hält. Jeder Schritt ist idempotent; nach einem Absturz setzt der Server
an derselben Stelle fort.

1. **Protokoll zuerst** (CLI): Eintrag ins Löschprotokoll (§7.3) und dessen Bestätigung,
   **bevor** irgendetwas gelöscht wird (Write-ahead).
2. **Beauftragen und sperren** (CLI mit `onetry_admin`, oder Server mit `onetry_deleter` beim
   Replay, §7.3): `status = 'loeschung'`, `disabled = true`, `login_version + 1`. Ab hier weist
   `resolve()` neue Anfragen ab; Logins sind über die Version widerrufen und werden in
   Schritt 7 gelöscht. Stürzt die CLI zwischen Schritt 1 und 2 ab, holt der Server Schritt 2
   aus dem Protokoll nach.
3. **Verbindlicher Sperrzeitpunkt** (Server): Der Löschauftrags-Task fragt `users.status`
   regelmäßig ab (Takt ≤ 5 s) und beim Wiederanlauf. Er trägt die Nutzer-ID **unter der
   Registersperre** in eine Sperrliste ein. Jeder Start prüft diese Liste unter derselben
   Sperre, bevor er reserviert. **Ab dem Eintrag** wird jeder Start abgewiesen; ein Start, der
   die Anmeldung vorher passiert hat und die Registersperre erst danach erhält, scheitert hier.
4. **Erfassen, dann außerhalb abwarten** (Server): **Unter** der Registersperre nur:
   Sperrliste setzen (Schritt 3), alle Registereinträge des Nutzers erfassen, auch startende
   und initialisierende, und ihre Abschlussabsicht (Endgrund `nutzer_geloescht`) markieren.
   Danach Sperre **freigeben** und außerhalb `end()` aufrufen und auf die Start- bzw.
   Abschlussaufgaben warten (diese brauchen die Registersperre selbst). Endzustand:
   Budgetabschluss (auch unbestätigter Ersatzabschluss nach 120 s) **oder**
   `erzeugung_ungeklaert`. Ein erfolgreiches `end()` allein gilt nicht als Endzustand.
5. **Übertragung verwerfen:** Für jede Sitzung des Nutzers ohne `conversation_synced`
   (Schritt 6) bzw. jede abgeschlossene Sitzung (Schritt 5) hängt der Server
   `conversation_discarded` ans Journal; `recover()` überträgt sie nie mehr.
6. **`erzeugung_ungeklaert`:** Die Reserve bleibt gebunden (bekannte Lücke aus Schritt 1),
   aber ohne Nutzerbezug: Der Server hängt `session_unlinked` an; die Kompaktierung schreibt
   die Sitzung ohne `user_id` weiter (§7.2). Die Regel „1 Gespräch je Nutzer“ braucht diese
   Zuordnung nicht mehr, weil der Nutzer gesperrt ist.
7. **Datenbank** (Server, `onetry_deleter`): `conversations` des Nutzers (Kinder per
   Cascade), `logins`, `users`-Zeile.
8. **Journal-Kompaktierung** (§7.2): danach keine `user_id` des Nutzers mehr im Journal; die
   Kosten bleiben in der Monatssumme bzw. als offene Reserve ohne Nutzerbezug.

**Vertragsende:** CLI setzt `tenants.status = 'loeschung'` und beauftragt alle Nutzer des
Mandanten wie oben; der Server löscht die `tenants`-Zeile, sobald keine Nutzer mehr existieren.

### 7.2 Journal-Kompaktierung (Vertrag, Umsetzung Schritt 5)

Das Journal ist append-only und enthält `user_id` und `provider_id` je Sitzung; die heutigen
Leser (`journal.py`, `budget.py`) kennen nur Einzelereignisse.

- **Versioniertes Snapshot-Ereignis** `budget_snapshot` (Version 1) am Dateianfang: je Monat
  (nach Reservierungsbeginn) verbrauchte Mikro-Dollar und Anzahl geschätzter/unbestätigter
  Buchungen, ohne Nutzer- oder Provider-Bezug. Leser akzeptieren alte Journale ohne Snapshot
  unverändert (rückwärtskompatibel).
- **Summenregel:** neuer Snapshot = bisheriger Snapshot + Buchungen der in **dieser**
  Kompaktierung entfernten Sitzungen. Erhaltene Einzelereignisse sind im Snapshot **nicht**
  enthalten; der Replay addiert Snapshot und Einzelereignisse, ohne Doppelzählung.
- **Entfernt werden** (Budget- und Sitzungsereignisse derselben `local_id` nur gemeinsam):
  abgeschlossene Sitzungen mit Budgetabschluss und mit `conversation_synced` oder
  `conversation_discarded`. **In Schritt 5** (ohne Übertragung) genügt der Budgetabschluss.
- **Erhalten bleiben** vollständig: offene Reservierungen einschließlich Preisen, nicht
  abgeschlossene Sitzungen, abgeschlossene Sitzungen mit ausstehender Übertragung (Schritt 6).
  Sitzungen mit `session_unlinked` bleiben mit offener Reserve erhalten, aber ohne `user_id`
  und ohne Zuordnung beim Wiederanlauf.
- **Austausch** unter der Journal-Sperre: neue Datei schreiben, `fsync`, `rename`,
  Verzeichnis-`fsync`, Append-Dateideskriptor neu öffnen, Speicherzustand ersetzen. Ein Absturz
  hinterlässt entweder die alte oder die neue Datei, nie eine Mischung.
- Ausgelöst nach Nutzerlöschung und regelmäßig (z. B. täglich).

### 7.3 Löschprotokoll und Wiederherstellung

- **Inhalt:** nur `user_id` bzw. `tenant_id`, Art und Zeitpunkt des Auftrags (keine
  Gesprächs-IDs, keine Inhalte). Aufbewahrt für die Backup-Dauer.
- **Speicherort:** append-only, **außerhalb** des Datenbestands, der bei einer
  Wiederherstellung zurückgesetzt wird (eigenes Volume bzw. eigener EU-Speicher mit eigener
  Sicherung); Auswahl mit der Hosting-Entscheidung (G5). Ein Restore von Datenbank oder VM
  setzt das Protokoll damit nicht mit zurück.
- **Write-ahead:** Eintrag dauerhaft vor dem ersten Löschschritt (§7.1 Schritt 1).
- **Replay:** Nach jedem Start und nach jeder Wiederherstellung arbeitet der Server alle
  Einträge mit `onetry_deleter` ab (§7.1 ab Schritt 2), **bevor** er bereit ist: bis dahin
  `/healthz` 503 **und** Abweisung aller API-Anfragen (Anmeldung, Start, Daten), nicht nur der
  Health-Prüfung. Fristlöschungen ergeben sich aus `expires_at` (Löschjob sofort).
- `session_unlinked` erfordert in Schrittplan 5 gemeinsame Anpassungen von Journalvalidierung,
  Registeraufbau und `recover()` (heute verlangen sie eine Nutzer-ID bzw. erzeugen eine
  Ersatzzuordnung); kein späteres Ereignis darf die Zuordnung wieder einführen (D7c).

### 7.4 Weitere Regeln

- **Backups zählen mit.** Tatsächliche maximale Aufbewahrung = Frist + Backup-/PITR-Dauer
  (Datenbank und VM-Backups mit Journal). Diese Summe wird als Frist beschlossen, nicht nur
  die Tabellenfrist.
- **Betriebslog:** enthält `session_ref` = `conversations.id`. Solange die Gesprächszeile
  existiert, ist das Log darüber einem Nutzer zuordenbar; nach Löschung der Zeile und
  Kompaktierung des Journals im **aktiven Datenbestand** nicht mehr. In Backups bis zu deren
  Ablauf weiterhin. Das Betriebslog bekommt eine eigene Frist und einen eigenen Löschweg
  einschließlich Backups (G5).
- **Dienstleister:** Für Auswertungs- und Schlüsselmoment-Modelle Aufbewahrung beim Anbieter
  vor Schritt 6 klären und Löschung nachweisen (Plan §1).
- **Logs:** Datenbank-, Anbieter- und Anwendungslogs dürfen keine Inhalte enthalten.
  `log_statement = none` reicht nicht: Constraint-Fehler können Zeilenwerte in `DETAIL`
  ausgeben. Nachweis per Test (D8) und Anbieterprüfung.

## 8. Freigabegates

| Gate | Vor | Inhalt |
|---|---|---|
| G5 | Umsetzung Schritt 5 | Anbieter und AVV (Pit); Fristen und Löschwege für Nutzer, Logins, Journal, Betriebslog, Löschprotokoll und deren Backups; Login-Persistenz entschieden |
| G6 | Umsetzung Schritt 6 | Fristen für Transkript, Auswertung, Schlüsselmomente inkl. Backups; Dienstleister-Aufbewahrung und Löschnachweis; Datenflussprüfung der Auswertungsmodelle |

## 9. Abnahme (Tests)

Gegen ein echtes Postgres (lokal im Container, synthetische Daten, ohne externen Dienst);
Mocks reichen für RLS nicht. **D1–D9 laufen in Schritt 5 auf dem Teilschema und in Schritt 6
erneut auf dem vollständigen Schema.**

| # | Kriterium |
|---|---|
| D1 | Mandant X mit Nutzern A und B, Mandant Y mit Nutzer C. Je Tabelle und Befehl: A liest und ändert nur eigene Zeilen; nichts von B oder C ist sichtbar oder änderbar, weder über die API noch direkt mit `onetry_app` und Kontext von A. |
| D2 | Je Tabelle ohne Kontext, nur mit Mandant und nur mit Nutzer: `SELECT` liefert 0 Zeilen (auch `tenants`), `INSERT` schlägt fehl, `UPDATE`/`DELETE` ändern nachweislich nichts. |
| D3 | `INSERT`/`UPDATE` mit fremder `tenant_id`/`user_id` und Umbiegen eines Kind-Fremdschlüssels auf ein Gespräch von B bzw. C werden abgewiesen. |
| D4 | Katalogtest, getrennt nach: (a) Tabelleninventar – jede Tabelle steht in einer Freigabeliste mit erwarteter Policy-Lage, neue Tabellen lassen den Test scheitern; `relrowsecurity` und `relforcerowsecurity` überall; Views mit `security_invoker`. (b) Eigentum – Schema, Tabellen, Views, Kontextfunktionen gehören `onetry_owner`, genau die zwei Anmeldefunktionen `onetry_auth`, sonst nichts. (c) Rollen – alle Rollen außer `onetry_owner` (einschließlich `onetry_auth`) sind kein Superuser, ohne `BYPASSRLS`, ohne Mitgliedschaft in anderen OneTry-Rollen; `onetry_auth` ist `NOLOGIN`. (d) Rechte – `EXECUTE` auf die Anmeldefunktionen nur für `onetry_app`, nicht für `PUBLIC`; `onetry_deleter`/`onetry_retention` haben auf Gesprächstabellen nur Schlüsselspalten; `onetry_admin` hat dort gar keine Rechte; Spalten-`UPDATE` von `onetry_app` nur wie in §6.2. |
| D5 | Kein Kontextleck bei echter Verbindungswiederverwendung im Pool: nacheinander A, C, ohne Kontext; dazu nach Rollback, nach SQL-Fehler, nach abgebrochener Anfrage. Jede Transaktion sieht nur, was ihr Kontext erlaubt. |
| D6 | Anmeldefunktionen liefern nur die festgelegten Felder für genau einen Namen bzw. Hash, keine Listen; `PUBLIC` hat kein `EXECUTE`. Widerruf bei Sperre, Passwortänderung (atomar mit Versionserhöhung, auch bei gleichzeitig laufender Anmeldung) und Löschung, Ablauf (Wanduhr), Abmelden; Mandant kommt nur aus der Anmeldung. |
| D7 | (a) Löschjob entfernt nur abgelaufene Zeilen, auch bei absichtlich ungefiltertem `DELETE` als `onetry_retention`; `conversations.expires_at` ≥ Fristen der Kinder. (b) Nutzer- und Vertragslöschung mit den echten Rollen und Statements erreichen alle Tabellen, Logins und das Journal; `onetry_deleter` löscht nichts von Nutzern ohne `status = 'loeschung'`, auch bei ungefiltertem `DELETE`, und kann keine Inhaltsspalten lesen; Abmelden mit `onetry_app` funktioniert; ein Mandant im Status `loeschung` mit noch einem aktiven Nutzer wird nicht gelöscht; `onetry_deleter` kann keinen Nutzer oder Mandanten aus `loeschung` zurücksetzen und bereitet nur protokollierte Aufträge vor. (c) Löschablauf §7.1 mit kontrollierten Unterbrechungspunkten nach Anmeldung, vor Registereintritt und während `create`/`attach`: Starts nach dem Sperrlisteneintrag werden abgewiesen, früher eingetretene erfasst und bis zum Endzustand abgewartet; Abschlussaufgaben erhalten während des Wartens die Registersperre (keine Verklemmung); Absturz nach jedem Schritt setzt korrekt fort, auch zwischen Protokolleintrag und Statusänderung (Server holt Schritt 2 mit `onetry_deleter` nach); ausstehende Übertragung bei Datenbankausfall wird verworfen; Löschung nach `CreateUnclear` und nach Absturz ohne Provider-ID endet mit Reserve ohne Nutzerbezug, und weder Wiederanlauf noch spätere Journalereignisse führen die Zuordnung wieder ein. (d) Kompaktierung §7.2 auf Schritt-5-Teilschema und vollständigem Schema: Budget und Wiederanlauf identisch vor und nach Kompaktierung, mit Mischung aus entfernbaren und zurückgehaltenen Sitzungen, bei zwei aufeinanderfolgenden Kompaktierungen, über einen Monatswechsel, bei parallelem Append und bei Absturz während der Kompaktierung; danach keine `user_id` des gelöschten Nutzers im Journal. (e) Zuordenbarkeit im aktiven Datenbestand nach abgeschlossener Löschung: keine `session_ref` aus dem Betriebslog führt über Datenbank, Journal oder Löschprotokoll zum Nutzer; Backups gesondert nach §7.4. (f) Restore eines Stands vor der Löschung, danach Replay aus dem Löschprotokoll vor Bereitschaft: Ergebnis wie ohne Restore; API-Anfragen vor Abschluss des Replays werden abgewiesen. |
| D8 | Logs inhaltsfrei: mit synthetischem Erkennungstext absichtlich Constraint- und Abfragefehler auslösen; Datenbanklog, Anwendungslog und Betriebslog enthalten den Text nicht. |
| D9 | Migration: bestehender Nutzer kann sich anmelden, offene Reservierung und Wiederanlauf bleiben konsistent, alle Nutzer in `onetry-intern`. |
| D10 | Übergang Journal → Datenbank nach §4.3 einschließlich aller Absturz- und Ausfallfälle; nach dem Fenster „Commit erfolgt, `conversation_synced` fehlt“ sind Inhalt, Status, Kosten und Kindzeilen unverändert. |
| D11 | Schreibvertrag §6.4 mit den echten Rollen: Abschluss vor Notizeingabe, spätere Auswertung, Auswertung ohne Notizen nach Frist, Wiederholung der Auswertung, zwei gleichzeitige Auswertungen (genau ein Ergebnis), Wiederholung der Abschlussübertragung nach Auswertung (Ergebnis unverändert); Gesamtpunkte = Summe der Posten einschließlich Hilfsabzügen und Abgleichposten. |

## 10. Offene Entscheidungen

| Punkt | Wer | Bis |
|---|---|---|
| Datenbankanbieter (selbst betrieben auf der Hetzner-VM, Managed Postgres eines EU-Anbieters, Supabase o. Ä.) inkl. AVV, Standort von Backups und Supportzugriff | Pit (Auswahlvorschlag Claude) | G5 |
| Fristen (§7, §8) | Pit | G5 / G6 |
| Login-Name global eindeutig oder je Mandant | Claude (Vorschlag: global, E-Mail) | G5 |
| Anmeldungen persistieren (kein Abmelden bei Neustart) | Claude | G5 |
| Neue Starts bei länger nicht erreichbarer Datenbank sperren? | Claude / Pit | Schrittplan 6 |
| Budget je Mandant statt global; Journal in die Datenbank | Pit / Claude | Phase 1 nicht nötig |
| Treiber (`asyncpg` / `psycopg` 3) | Claude | Schrittplan 5 |

**Anbieterkriterien** (Prüfpunkte, nicht geprüft): EU-Verarbeitung einschließlich Backups,
Logs und Supportzugriff; AVV verfügbar; Postgres ≥ 15; Backup- und PITR-Dauer konfigurierbar;
Verschlüsselung at rest; keine Inhalte in Anbieter-Telemetrie oder -Logs; kein Superuser- oder
`BYPASSRLS`-Zwang für die Laufzeitrolle; bei US-Anbietern Zugriff nach US-Recht als eigener
Prüfpunkt.

## 11. Ablauf

1. Codex-Review abgeschlossen (Runde 5: freigabefähig als Rahmenplan).
2. Rahmenplan freigegeben (Pit, 2026-10-29). Offen: Anbieter, Fristen und Gate G5 (Pit).
3. Schritt 5: Migration, `tenants`, `users`, Anmeldung, Rollen, RLS, Journal-Kompaktierung,
   Tests D1–D6, D7 (ohne Gesprächstabellen), D8, D9 (eigener Schrittplan).
4. Gate G6, dann Schritt 6: Gesprächsdaten, Auswertung, Löschjob, Übergang Journal →
   Datenbank, D1–D11 auf dem vollständigen Schema (eigener Schrittplan).

## 12. Reviews Codex (2026-10-29)

„Eingearbeitet“ heißt: im Plan beschrieben, nicht durch Tests nachgewiesen.

**Runde 5** (gezielte Nachprüfung) – Votum: **freigabefähig als Rahmenplan**; keine P1/P2.
P3 übernommen: Vorbereitungspolicies als `USING (true) WITH CHECK (…)` (§6.2). Verbindlich in
**Schrittplan 5**: konkrete SQL-Statements und Policies, `session_unlinked` in Journal,
Register und `recover()`, atomare Passwortänderung; D7b/c weisen `aktiv → loeschung`,
Versionserhöhung und Abweisung der Rückrichtung mit echten Statements nach. Verbindlich in
**Schrittplan 6**: Scoring-Gewichte, Postenarten, Auswertung unter `READ COMMITTED`.
Nicht extern verifiziert: Postgres-Versionsangaben, Anbieterfähigkeiten, EU-/AVV-Zusagen.

**Runde 4** – Votum: nicht freigabefähig (P1 blockiert). Alle Befunde übernommen (in Runde 5
als behoben bewertet):
P1 Replay mit Serverrollen nicht ausführbar → `onetry_deleter` mit einseitigem `UPDATE` nur
Richtung `loeschung` und `logins`-Policy (§6.1, §6.2), §7.1 Schritt 2, §7.3, D7b/c/f · P2
Warten unter der Registersperre → §7.1 Schritt 4 (nur Erfassen unter der Sperre), D7c · P2
Leerheitsprüfung Mandant → `SELECT` der Schlüsselspalten ohne Zeileneinschränkung, FK
`ON DELETE RESTRICT`, D7b · P2 Punkte aus dem Abgleich → §6.4 (Abgleichposten,
Gesamt = Summe), D11 · P2 Passwortänderung atomar mit Versionserhöhung → §6.2, D6, Ausgestaltung
Schrittplan 5 (laut Codex nicht freigabeblockierend) · Hinweise `session_unlinked`, D7f
(API-Abweisung), Supabase-Satz entfernt.

**Runde 3** – Votum: nicht freigabefähig. Alle Befunde aufgegriffen (in Runde 4 bewertet:
1, 2, 4 behoben; 3, 5, 6, 7 teilweise, in Runde 4 weitergeführt):
P1 Schritt 5 ohne Freigabemerkmal für die Kompaktierung → §7.1 Schritt 5, §7.2 („in Schritt 5
genügt der Budgetabschluss“), D7d · P1 `erzeugung_ungeklaert` blockiert die Löschung →
§7.1 Schritt 4 und 6 (`session_unlinked`, Reserve ohne Nutzerbezug), §7.2, D7c · P2
verbindlicher Sperrzeitpunkt, Erfassen auch startender Sitzungen → §7.1 Schritt 3–4, D7c · P2
Snapshot-Summenregel → §7.2, D7d · P2 Schreibvertrag Abschluss/Auswertung → §6.4, §6.2
(Spalten-`UPDATE`), D11 · P2 Löschprotokoll außerhalb des Restore-Bestands, Write-ahead,
Replay → §7.3, D7f · P2 privilegierter Löschpfad → neue Rolle `onetry_deleter`, nur für
Nutzer/Mandanten im Status `loeschung`; `onetry_admin` ohne Zugriff auf Gesprächstabellen
(§6.1, §6.2) · P3 `onetry_auth` in D4c.

**Runde 2** – Votum: nicht freigabefähig. Alle Befunde aufgegriffen (in Runde 3 bewertet:
1, 6, 7 behoben; 2, 3, 4, 5, 8 teilweise, in Runde 3 weitergeführt):
P1 Admin-Löschung und Abmelden ohne Leserechte/`SELECT`-Policy → §6.2 (Schlüsselspalten),
D7b · P1 Nutzerlöschung vs. Kompaktierung bei nicht übertragenen Sitzungen, konkurrierender
Start → §7.1, D7c · P1 Wiederholung nach Commit beschädigt Daten → §4.3 (Zeile = vollständige
Übertragung, `DO NOTHING`), D10 · P2 Kompaktierungsvertrag → §7.2, D7d · P2 Ergebnisvertrag
Kriterien und Hilfen → §4.2 · P2 Eigentum je Objektklasse → §6.1, D4 · P2 `tenants` bei
Teilkontext, `ctx_user()` → §6.2, D2 · P2 Betriebslog zuordenbar → §7.4, G5, D7e ·
zusätzlich FK `logins → users` → §4.2.

**Runde 1** – Votum: noch nicht freigeben. Alle Befunde aufgegriffen; in Runde 2 als teilweise
erledigt bewertet und dort weitergeführt:
P1 Anmeldefunktion ohne RLS-Weg → §6.1, §6.3 · P1 Löschrolle ohne Policy → §6.2 ·
P1 Journal → `conversations` nicht wiederanlauffest → §4.3, D10 · P1 Löschweg ohne Kindtabellen
und Journal → §4.2, §7, D7 · P2 Policy-Matrix → §6.2 · P2 Abschluss/Auswertbarkeit → §4.2 ·
P2 bestehende IDs → §4.1, D9 · P2 Anmeldung als Vertrag → §6.3, D6 · P2 Ergebnisvertrag
Punkte/Hilfen/Framework → §4.2 · P2 Tests → D1–D5, D8, §9 · P2 Gates → §8 · P2 Logs → §5, §7,
D8 · P3 Postgres-Aussagen → §6.1, §6.2.
