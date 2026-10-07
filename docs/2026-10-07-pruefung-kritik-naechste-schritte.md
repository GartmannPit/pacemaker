# Prüfung der Kritik an den nächsten Schritten — überarbeiteter Plan

**Stand:** 2026-10-07
**Bezug:** [Kritische Einordnung (Codex)](./2026-10-07-kritische-einordnung-naechste-schritte.md),
[Analyse der Einordnung (Codex)](./2026-10-07-analyse-claude-einordnung.md),
[bisheriger Plan](./2026-10-07-naechste-schritte.md) — **dieser wird durch §4 ersetzt.**

---

## 1. Ergebnis

Die Kritik ist **berechtigt und an zwei Stellen grundlegend**:

1. **Mein Plan endete vor der Phase-0-Abnahme.** Sieben Muss-Kriterien aus dem
   [Phase-0-Plan](./phase-0-proof-of-concept.md) §2 kamen als Aufgaben nicht vor.
2. **Ich habe den Browser falsch begründet.** Im Phase-0-Plan steht die Web-Ansicht unter
   „Kann", nicht unter „Muss". Meine Aussage „ohne Browser ist das Abnahmekriterium nicht
   prüfbar" ist formal falsch. Der Browser bleibt produktseitig wichtig (Web-only-Constraint),
   ist aber für Phase 0 eine Entscheidung, keine Voraussetzung.

Dazu kommen mehrere berechtigte Präzisierungen. Widerspruch habe ich keinen.

## 2. Nachgeprüft

| Aussage | Geprüft an | Ergebnis |
|---|---|---|
| Phase-0-Plan enthält weitere Muss-Kriterien (Sprachqualität, Barge-in, Rollen-Konsistenz, EU-Doku, Transkript+Timing, Kosten, Reproduzierbarkeit, Ergebnisdokument) | `phase-0-proof-of-concept.md` Z. 93–103 | **Zutreffend.** Neun Muss-Kriterien, mein Plan deckte im Kern nur Latenz ab. |
| Web-Ansicht ist „Kann" | `phase-0-proof-of-concept.md` Z. 112–114 | **Zutreffend.** |
| LiveKit-Setup ist ein Entwicklungs-Setup | `infra/docker-compose.yml` (`--node-ip 127.0.0.1`), `infra/livekit.yaml` (`use_external_ip: false`, `devkey: secret`) | **Zutreffend.** Für Browserzugriff auf die VM fehlen Domain/TLS, angekündigte IP, eigene Keys, serverseitige Raumtokens, ggf. TURN. |
| September-Doku setzt spekulativen LLM-Start mit `wait_for_transcript=False` gleich und erklärt ihn für widerlegt | `2026-09-07-latenz-ansaetze-plausibilitaetspruefung.md` §1 Z. 22–42, Tabelle Z. 200 | **Zutreffend.** Meine Aussage in der Einordnung §3.5 („Habe ich so auch nicht behauptet") war **falsch**. Die September-Doku muss korrigiert werden. |
| Pipecat beendet die LLM-TTFB-Messung vor der Prüfung auf Textinhalt | `pipecat/services/openai/base_llm.py` Z. 501–504 vs. Z. 541 | **Zutreffend.** Ein leeres erstes Paket beendet die Messung. |
| RTT-Fix: neue Dateien im Unterordner, alte Datei, laufende Instanz | `infra/messreihe.sh`; VM: Datei nach Ende der Reihe kopiert, alte RTT-Datei nach `rtt/` verschoben | **Teilweise überholt:** Beides ist auf der VM erledigt (nach Ende der Reihe). **Offen bleibt:** Der Aggregator gruppiert weiterhin nur nach Stack und Modell. |

## 3. Präzisierungen, die ich übernehme

| # | Punkt | Konsequenz |
|---|---|---|
| 3.1 | Filtersignal, Barge-in und verworfene Antworten brauchen **denselben Abbruchpfad** | Gemeinsamer Abbruchpfad wird Teil von Schritt B (Barge-in ist ohnehin Muss), nicht letzter Schritt. Mit deterministisch eingespeistem Filtersignal testen. Abbruch erscheint als Ergebnisstatus — auch in Messläufen. |
| 3.2 | „Zeit bis zum Inhalt" ist nicht „Audio des zweiten Satzes" | Zwei Begriffe: **Beginn des Hauptsatzes** (automatisch, Hilfsmetrik) und **Beginn der relevanten Antwort** (manuell annotiert, Qualitätsmetrik, mit vorab festgelegten Beispielen). „Nein." kann bereits relevant sein. |
| 3.3 | Transkript-Zeitstempel sind Aggregator-Ereignisse, kein Hörbeginn | Für die Annotation ausgerichteter Audiomitschnitt; Zeitstempel nicht als Hörbeginn interpretieren. |
| 3.4 | TextStream ist eine Hypothese | Formulierung „kann die Latenz senken". Ehrlicher noch: Auf der VM liegt die TTS-Zeit bei `nano` nur noch bei 105–128 ms, die Satzwartezeit bei ~14 ms — viel Spielraum für TextStream bleibt beim ersten Audio nicht. Möglicher Nutzen eher bei natürlichen Einstiegen ohne erzwungenen Kurzsatz. Priorität sinkt. |
| 3.5 | Neben dem ersten Paket auch das **erste verwertbare Textdelta** erfassen | Teil der Messhygiene (Schritt A). |
| 3.6 | Stabile RTT vor/nach einem Lauf schließt Netzwerkeffekte im Lauf nicht aus | Formulierung in Summary §14 entschärfen. |
| 3.7 | Aufwärmen auf der VM nicht kausal belegt | Kein Vergleichslauf ohne Aufwärmen auf der VM. „Kein auffälliger Erstturn-Nachteil" statt „wirkt". |
| 3.8 | 150 ms sind keine feste Nachweisgrenze | Formulierung in §14 korrigieren: Nachweisbarkeit hängt von Versuchsanordnung und Stichprobe ab. |
| 3.9 | ½ Tag für die Messkette ist zu optimistisch | In drei prüfbare Teile zerlegt (Schritt A), Aufwand je Teil. |
| 3.10 | Bei Data-Zone-Deployments kann Inferenz innerhalb der EU-Zone geroutet werden | Unsere Deployments **sind** Data Zone. Die 28 ms RTT zeigen nur den Ressourcen-Endpoint, nicht den Inferenzort. Diagnose bleibt klein und parallel; ein neues Deployment nur, wenn sie einen klaren Hebel zeigt. |
| 3.11 | Robustheitskorpus: eine Stimme ist nur eine erste Probe; Einwilligungstext muss Azure-Verarbeitung nennen | Als „erste Robustheitsprobe" kennzeichnen; auch spontane Äußerungen; pro Aufnahme Referenztext, Pausen, gewollte Turn-Grenze, erwartete Mindestinformation. Anleitung nennt Verarbeitung durch Azure, Speicherort, Löschung. |
| 3.12 | Segmentierungskurve gehört nach dem Korpus wieder in den Plan | Aus „zurückgestellt" in Schritt C verschoben. Der 100-ms-Default braucht diese Validierung. |
| 3.13 | Jeder Architekturhebel braucht ein vorab festgelegtes Abbruchkriterium | Übernommen: reproduzierbarer Gewinn bei gleicher Qualität und Fehlerrate, sonst zurück zur Referenz und Versuch abschließen. |
| 3.14 | Spekulativer Start: Audio erst nach bestätigter Turn-Grenze **und** verifiziertem finalen Transkript; verworfene Kandidaten verändern den Kontext nicht | Übernommen in die Versuchsbeschreibung. |
| 3.15 | Messreihen gegenbalancieren | Nächste Reihe: Reihenfolge je Wiederholung wechseln (A-B, B-A, A-B). |

## 4. Überarbeiteter Plan

Gliederung nach den **Muss-Kriterien des Phase-0-Plans**. Aufwände sind Orientierung, keine Zusage.

### A — Messhygiene (Claude, ca. 1–1,5 Tage)

| Teil | Inhalt | Abschlusskriterium |
|---|---|---|
| A1 Lauftrennung | Manifest je Lauf (`run_id`, Git-Revision, Pipecat-Version, Deployment/Typ, Filtermodus, Segmentierung, VAD, Aufwärmen, Prompt-/Fixture-Hash), Aggregation je `run_id` | Eine Tabelle je Lauf; historische Läufe mit rekonstruierten Werten, Unbekanntes als „unbekannt" |
| A2 Turn-Bilanz | `utterance_id` beim Einspeisen, Zuordnung zu erkannten Turns und Antworten, genau ein Endstatus je Äußerung (beantwortet / Timeout / Audiofehler / abgebrochen / zerfallen / Antwort auf unvollständige Eingabe) | Summe der Status = Zahl angebotener Äußerungen; Fehler bleiben in der Bilanz |
| A3 Timing | Erstes Paket, erstes Textdelta, erstes Audio, Beginn Hauptsatz; Kaltstart separat und in der Gesamtbilanz | Alle vier Zeitpunkte je Turn in der Tabelle |
| A4 Doku-Korrekturen | Metrikdefinition (`CLAUDE.md`, Plan, Collector); Überdehnungen aus der Einordnung §4; September-Doku zum spekulativen Start; Formulierungen §14 (3.6–3.8) | Korrigierte Stellen im Commit benannt |

**Parallel:** Azure-Deployment-Diagnose (Region, Routing) · Aufnahmeliste für Schritt C.

**Warum zuerst:** Jeder folgende Schritt misst damit; Ausfälle, Konfigurationen und
Antwortbeginn müssen sauber unterscheidbar sein, bevor weitere Zahlen interpretiert werden.

### B — Muss-Kriterien, die ohne Browser prüfbar sind (Claude + Gründer)

| Muss-Kriterium | Aufgabe | Wer |
|---|---|---|
| **Barge-in** ≤ 300 ms in ≥ 9/10 Fällen | Gemeinsamer Abbruchpfad (Barge-in + Filtersignal + verworfene Antwort): Synthese stoppen, gepuffertes Audio verwerfen, verspätete Chunks blockieren. 10 gezielte Fälle lokal mit Headset, Messung Nutzerstart → Persona verstummt | Claude baut/misst, Pit spricht |
| **Rollen-Konsistenz** über 10 Gespräche à ~5 Min. | Skript ohne Wiederholung; Rollenbruch-Check mit Keyword-Filter **und** LLM-Judge über das Transkript (Budget, Geduld, kein KI-Bruch). Zunächst synthetisch, dann einige Gründer-Gespräche | Claude, Gründer |
| **Sprachqualität** Mittel ≥ 3,5 | Beide Gründer bewerten unabhängig auf 1–5-Skala, möglichst blind A/B | Gründer |
| **Transkript + Timing** exportierbar | Transkript mit Zeitstempeln je Sprecherwechsel als Datei (Basis vorhanden, Export ergänzen) | Claude |
| **EU-Compliance dokumentiert** | Je Dienst: Region, Deployment-Typ, AVV/DPA, CLOUD-Act-Exposition; Latenzdifferenz zur US-Baseline als beobachteter Stack-Unterschied | Claude recherchiert, Pit prüft AVVs |
| **Kosten pro Gesprächsminute** | STT/LLM/TTS getrennt, inkl. Aufwärmen | Claude |
| **Reproduzierbarkeit** | `README.md` so, dass eine dritte Person lokal in < 30 Min. ein Gespräch startet; Probelauf durch jemand anderen | Claude, Testperson |

**Warum jetzt:** Diese Kriterien sind Teil der Abnahme, größtenteils günstig und unabhängig von
der Latenzfrage. Der Abbruchpfad ist für Barge-in ohnehin nötig und deckt den asynchronen
Filter mit ab.

### C — Robustheitsprobe (Pit Aufnahmen, Claude Auswertung)

- Erste Robustheitsprobe mit Pits Stimme (20–30 Äußerungen, gesteuerte und spontane), Einwilligung
  mit Nennung von Azure-Verarbeitung, Speicherort, Löschung.
- Segmentierungs-/VAD-Kurve (100/200/300 ms) gegen vorzeitige Antworten und fehlende Satzteile.
- Bestehende Clips als zusammenhängendes Gespräch ohne wiederholten Opener.

**Warum:** Validiert den 100-ms-Default und zeigt, ob Tempo auf Kosten des Verstehens gewonnen
wird — Voraussetzung, bevor weitere Latenzhebel beurteilt werden.

### D — Latenz-Kriterium: Kontrollmessung, dann höchstens gezielte Hebel

1. Gegenbalancierte Messreihe (`nano`/`mini`) auf der VM mit der neuen Messkette.
2. Nur wenn p90 weiterhin über 900 ms liegt: **ein** Hebel zur Zeit mit vorab festgelegtem
   Abbruchkriterium. Reihenfolge nach Prüfung von §3.4 neu: spekulativer LLM-Start (größter
   möglicher Hebel auf die ~350 ms Turn-Erkennung + ~360 ms LLM, aber größter Umbau) vor
   TextStream (wenig Spielraum beim ersten Audio).

### E — Browser (Entscheidung offen)

Im Phase-0-Plan „Kann". Für das Produkt (Web-only) unverzichtbar, aber mit realem
Infrastrukturaufwand: Domain, TLS, eigene LiveKit-Keys, serverseitige Raumtokens, angekündigte
IP und Medienports, ggf. TURN; Client-Hörbeginn getrennt von Server-Audioanfang messen.

**Optionen:** (a) noch in Phase 0 nach B, (b) als erster Schritt von Phase 1.
**Empfehlung:** (b) — Phase 0 zuerst mit den Muss-Kriterien abschließen; der Browserpfad ist
dann der natürliche Start von Phase 1 und profitiert vom fertigen Abbruchpfad.

### F — Ergebnisdokument und Go/No-Go

`docs/phase-0-ergebnisse.md`: Vergleichstabelle (Latenz p50/p90/p95 je Lauf, Fehlerraten,
Sprachqualität, EU-Compliance, Kosten/Min), Stack-Empfehlung, offene Kriterien, „Was uns
überrascht hat", bewusste Go/No-Go-Entscheidung — auch für den Fall, dass p90 < 900 ms nicht
erreicht wird.

## 5. Entscheidungen für Pit

1. Überarbeiteten Plan (A → B, parallel C → D → F) übernehmen?
2. Browser in Phase 0 (Option a) oder als Start von Phase 1 (Option b, Empfehlung)?
3. Zusage für Barge-in-Tests mit Headset (B) und Aufnahmen der Robustheitsprobe (C)?
4. Wer außer Pit testet die Reproduzierbarkeit (dritte Person)?
