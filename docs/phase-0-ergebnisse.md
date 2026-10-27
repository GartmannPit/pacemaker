# Phase 0 — Ergebnisse

**Stand:** 2026-10-27 · **Verfasser:** Claude · **Status:** ABGESCHLOSSEN durch
Gründerentscheidung (§8). §1–§7 dokumentieren den Stand vom 2026-10-14 (Azure-Kaskade) und
bleiben als Befund unverändert; was davon überholt ist, steht in §8.
**Bezug:** [Phase-0-Plan](./phase-0-proof-of-concept.md) · [Bestandsaufnahme](./2026-10-08-bestandsaufnahme-muss-kriterien.md) ·
[Testablauf](./phase-0-testablauf-gespraech.md) · Messprotokoll: [Summary §1–§27](../experiments/summaries/2026-10-03-llm-modellvergleich-deployment-typen.md)

## 1. Kurzfassung

> **Entscheidung (§8):** Sprachpfad OpenAI GPT-Live (`gpt-live-1`) statt Azure-Kaskade
> (2026-10-15); die gemessene GPT-Live-Latenz ist als angemessen beschlossen, das Ziel
> p90 < 900 ms gilt nicht mehr als Muss (2026-10-27). Weiter mit Phase 1
> ([Entwurf](./phase-1-mvp.md)).

Phase 0 sollte beantworten, ob eine deutsche Sprach-Persona mit **< 900 ms p90** Antwortzeit,
**akzeptabler Sprachqualität** und **EU-Datenresidenz** erreichbar ist.

- **Latenz: verfehlt.** Bester EU-Stack (`azure-eu`, `gpt-4.1-nano`) p90 1058–1231 ms je Lauf,
  p50 ~980 ms. Das Modell, das die Persona trägt (`gpt-4.1-mini`), liegt bei p90 1250–1455 ms.
  Auch die US-Referenz und der Realtime-Stack lagen darüber. Danach geprüft und ohne
  ausreichenden Gewinn: neuere Modelle (`gpt-5.4-mini`, `gpt-6-luna`, §22), spekulativer LLM-Start
  (−126 ms p50 allein, §23; zusammen mit der Vorverbindung nur −16 ms, §27), andere EU-STT-Dienste (Deepgram Flux EU, Gladia, §24), Azure
  TTS-Text-Streaming (langsamer, §25), Deepgram Aura-2 als TTS (langsamer, §26). Übernommen:
  TTS-Vorverbindung (−95 ms p50 / −107 ms p90, §26).
- **Barge-in: verfehlt.** Serverseitig ≤ 300 ms nur in 0/10 (Default) bzw. 3/10 Fällen; die Zeit
  steckt in der Bestätigung des Sprechbeginns. Hörersignale („Mhm") unterbrechen die Persona fast
  immer.
- **Rollentreue: mit `gpt-4.1-mini` im Textmodus erfüllt**, mit `nano` nicht. Im
  zusammenhängenden Sprachgespräch (T1) inhaltlich solide (Information übergangen 3/53), aber die
  Persona spricht bei Denkpausen in gut einem Drittel der Äußerungen hinein.
- **Sprachqualität, Reproduzierbarkeit durch Dritte, AVV-Prüfung: [offen, Gründer].**
- **Kosten:** bis 0,029 $ (~2,7 ct) je Gesprächsminute (`azure-eu`/`mini`, gemessen in T1).

**Phase 0 ist nicht bestanden.** Zwei Muss-Kriterien sind nachgewiesen verfehlt, drei hängen an
Gründer-Bewertungen.
Die Go/No-Go-Einschätzung in §6 behandelt, ob und wie es trotzdem weitergehen kann.

## 2. Muss-Kriterien

| # | Kriterium | Status | Ergebnis | Beleg |
|---|---|---|---|---|
| 1 | Latenz p90 < 900 ms (EU, ≥ 30 Turns, VM) | **verfehlt** | nano p90 1058–1231 ms; mini 1250–1455 ms; alle weiteren Hebel ohne ausreichenden Gewinn | §15, §14, §21–§24, §9, §12 |
| 2 | Sprachqualität ≥ 3,5 (beide Gründer) | **[offen]** | Blind-A/B-Paket bereit (`tests/voice_samples.py`) | — |
| 3 | Barge-in ≤ 300 ms in ≥ 9/10 | **verfehlt** | 0/10 (VAD-Start 0,2 s), 3/10 (0,1 s), serverseitig; Live-Test **[offen]** | §19 |
| 4 | Rollen-Konsistenz, 10 Gespräche | **erfüllt (Textmodus, mini)** | 0/10 Rollenbrüche, Gespräche 4–6 Beiträge; nano verfehlt | §20 |
| 5 | EU-Compliance dokumentiert | **teilweise** | Regionen, Deployment-Typ, CLOUD Act, EUDB recherchiert; DPA/AVV-Prüfung **[offen, Pit]** | [Faktenblatt](./phase-0-eu-compliance.md) |
| 6 | Transkript + Timing exportierbar | **erfüllt** | Beginn/Ende je Redebeitrag, Export Markdown/CSV | `metrics/transcript_export.py` |
| 7 | Kosten pro Minute je Stack | **erfüllt** | `azure-eu`/mini bis 0,029 $, /nano bis 0,027 $, US-Referenz 0,042 $ (T1-Verbrauch) | §3.4, §21 |
| 8 | Reproduzierbarkeit durch Dritte | **[offen]** | README neu; Installation aus frischem Klon geprüft | `README.md` |
| 9 | Ergebnisdokument | dieses Dokument | | |

**Soll:** Speech-to-Speech-Referenz erfüllt (§9, §12), VAD/Turn grob getunt (§16–§19); zweiter
EU-Stack (souverän) nicht gebaut.

## 3. Ergebnisse im Einzelnen

### 3.1 Latenz

| Stack / Modell | Bedingungen | E2E p50 | E2E p90 | Quelle |
|---|---|--:|--:|---|
| `azure-eu` / `nano`, optimiert | VM, 3 × 30 Turns, kein Einstieg | ~980 | 1058–1231 je Lauf | §15 B |
| `azure-eu` / `mini`, mit Einstieg | VM, 3 × 30 Turns | 1043–1119 | 1227–1324 | §14 |
| `azure-eu` / `mini`, optimiert | VM, 3 × 30 Turns | 1084–1270 | 1250–1455 je Sitzung | §21 |
| `azure-eu` / `mini`, Gespräch T1 | VM, Pits Aufnahmen, ohne F1/F2 | 1187 | 1830 | §21 |
| `azure-eu` / `mini` + spekulativer Start | VM, 3 × 30 Turns (gepoolt) | 1056 | 1298 | §23 |
| `azure-eu` / `mini` + TTS-Vorverbindung (Default seit 14.10.) | VM, 3 × 30 Turns (gepoolt) | 1106 | 1335 | §26 |
| dto., Kontrollbedingung des Kombi-Versuchs | VM, 3 × 30 Turns (gepoolt, alle beantworteten) | 1076 | 1337 | §27 |
| dto. + spekulativer Start | VM, 3 × 30 Turns (gepoolt, alle beantworteten) | 1060 | 1340 | §27 |
| `mini` mit Deepgram Flux (EU) statt Azure STT | VM, 2 × 30 Turns (gepoolt, Vormittag) | 1362 | 1718 | §24 |
| `mini` mit Gladia (EU) statt Azure STT | VM, 2 × 30 Turns (gepoolt, Vormittag) | 1546 | 1840 | §24 |
| Realtime `gpt-realtime-2.1` (`minimal`) | Laptop | 1208 | 2048 | §11/§12 |
| US-Referenz (Deepgram, OpenAI, ElevenLabs) | Laptop, nicht optimiert | 1224 | 1501 | §12 |

Zerlegung (nano, p50): Turn-Erkennung ~350 ms, LLM bis erster Text ~360 ms, TTS ~110–130 ms.
Zerlegung (mini, p50, 72 Turns): Sprechende → Turn-Ende 348 ms, → erster Text +344 ms, → erstes
Audio +414 ms. Der erste Abschnitt ist im Wesentlichen das Warten auf das finale Azure-Transkript;
selbst ein Start genau beim Sprechende ließe ~760 ms p50 / ~1070 ms p90 übrig (§23).
Wirksame Hebel waren asynchroner Inhaltsfilter (−265 ms), TTS-Randstille 0 (−330 ms Inhalt),
Aufwärmen, Segmentierung 100 ms; nicht wirksam: längerer VAD-Stopp, Kontextkürzung, Smart-Turn-CPU.

### 3.2 Sprecherwechsel mit echter Sprache (Robustheitsprobe, Pits Aufnahmen)

- Gut die Hälfte der gezielt pausenreichen Äußerungen zerfällt (Persona antwortet in einer
  Denkpause); weder Segmentierung noch VAD-Stopp 0,2–0,6 s beheben das (§16, §17).
- „OK." wird mit Default-VAD erst nach ~3,2 s beantwortet (Sprechbeginn nicht erkannt); VAD-Start
  0,1 s behebt das, wurde nach der vorab festgelegten Regel aber nicht übernommen (§18, §19).
- Einwort-Antworten warten ~1 s auf das Turn-Ende (Smart Turn hält sie für unvollständig).
- Simulation „Antwort zurückhalten" (Codex-Vorschlag): wirkt erst ab ~1,5 s Wartefrist und kostet
  dann ~0,9 s bei jeder Antwort (`metrics/hold_simulation.py`).
- **Zusammenhängendes Gespräch (T1, `mini`, 63 Äußerungen):** F2 zerfallen 29/63, F3 Persona
  spricht hinein 23/63, F1 Sprechbeginn verpasst 3/63, F4 Information übergangen 3/53, F6 0.
  Persona legt frühestens nach 9 Äußerungen auf (§21).

### 3.3 Barge-in und Hörersignale

Siehe Summary §19. Verstummen nach hörbarem Beginn des Zwischenrufs: p50 469 / p90 553 ms
(VAD-Start 0,2 s) bzw. 306 / 333 ms (0,1 s). Davon ~30 ms Pipeline, der Rest VAD-Bestätigung.
„Mhm" unterbricht in 4/5 bzw. 3/4 Fällen. Kein spätes Audio nach dem Abbruch.

### 3.4 Kosten (Listenpreise, USD, Pay-as-you-go)

| Baustein | Preis | Quelle |
|---|---|---|
| Azure STT (S0, Germany West Central) | 1,00 $ / Audio-Stunde | Azure Retail Prices API |
| Azure Neural TTS | 15 $ / 1 Mio. Zeichen | ebd. |
| `gpt-4.1-nano` Data Zone | 0,11 / 0,028 (Cache) / 0,44 $ je 1 Mio. Tokens | ebd. |
| `gpt-4.1-mini` Data Zone | 0,44 / 0,11 / 1,76 $ je 1 Mio. Tokens | ebd. |

Je Gesprächsminute aus T1 (15 Gesprächsminuten, LLM ohne Cache-Rabatt, STT als Spanne
Sprachdauer–Gesprächsdauer): `azure-eu`/mini **bis 0,029 $** (STT 0,012–0,017, LLM 0,003,
TTS 0,009), /nano bis 0,027 $. US-Referenz bei gleichem Verbrauch 0,042 $ (TTS teurer).

### 3.5 EU-Compliance

Siehe [Faktenblatt](./phase-0-eu-compliance.md): Alle Produktdienste in EU-Regionen (Speech
Germany West Central, OpenAI Sweden Central Data Zone EU, Server Hetzner DE); Microsoft als
US-Mutter (CLOUD Act) benannt; Azure Speech/OpenAI nicht auf der EUDB-Ausschlussliste. Offen:
DPA/AVV, Product Terms, Missbrauchsüberwachung (30 Tage), Smart Turn vs. Prosodie-Verbot
([Einordnung](./2026-10-08-einordnung-smart-turn-prosodie.md)).

## 4. Stack-Empfehlung für Phase 1

> **Überholt** durch die Gründerentscheidung für GPT-Live (§8). Die Kaskade bleibt Rückfall.

**`azure-eu` mit `gpt-4.1-mini`** (Data Zone EU), Azure Speech S0 Germany West Central, Stimme
**[offen: Blind-A/B]**, asynchroner Inhaltsfilter, Prompt-Durchgang 2. Begründung: einziger
getesteter EU-Stack, der die Persona trägt (§20); `nano` ist ~150 ms schneller, legt aber fast
sofort auf. Latenzabstand zur Vorgabe bewusst in Kauf genommen, siehe §6. Neuere Modelle
(`gpt-5.4-mini`, `gpt-6-luna`) sind langsamer bis zum ersten Satz (§22); Deepgram Flux (EU) ist als
STT gleich schnell und als Alternative vorbereitet (§24), AVV ungeprüft. Spekulativer Start als
abschaltbare Option vorhanden, nicht empfohlen ohne T1-Lauf und Kostenmessung (§23). TTS mit
Sprache `de-DE` und Vorverbindung nach Unterbrechungen (Default, §26).

## 5. Was uns überrascht hat

1. **Kleine Infrastruktur-Details kosteten mehr als Modellwahl:** gepufferter Inhaltsfilter
   (~265 ms) und Azure-TTS-Randstille (~1 s zwischen Sätzen) waren die größten Einzelhebel.
2. **Das schnellere Modell trägt die Rolle nicht.** Latenz und Rollentreue ziehen bei der
   Modellwahl in entgegengesetzte Richtungen.
3. **Echte Sprache verhält sich anders als synthetische Clips:** Denkpausen, kurze Antworten und
   Hörersignale waren mit TTS-Clips unsichtbar.
4. **Barge-in scheitert nicht am Abbruch, sondern am Erkennen** — und schnelleres Erkennen macht
   Hörersignale zu Unterbrechungen.
5. **Messhygiene war Voraussetzung:** Ohne Turn-Protokoll, Manifeste und vorab festgelegte
   Kriterien hätten mehrere Befunde anders ausgesehen (Randstille, Lauf-Streuung ±50–100 ms,
   ungültige Läufe durch Dienstfehler).

## 6. Go/No-Go-Einschätzung

> **Entschieden** (§8): weder Option A mit Kaskade noch B/C, sondern Wechsel auf GPT-Live.

**Entscheidungsgrundlage für das Gespräch Pit/Marvin (Plan, Woche 4, Schritt 24). Die
Entscheidung treffen die Gründer.**

### 6.1 Was feststeht

- **900 ms p90 sind mit heutigen EU-Diensten nicht erreichbar.** Geprüft wurden alle Hebel aus der
  Risikotabelle des Plans („Falls knapp verfehlt: S2S-Stack und aggressiveres
  Streaming/Endpointing prüfen, bevor No-Go") und darüber hinaus: Speech-to-Speech (§9–§12),
  Endpointing/VAD/Segmentierung (§13–§19), Modelle (§14, §20, §22), spekulativer Start (§23),
  drei EU-STT-Dienste (§24), Azure TTS-Text-Streaming (§25). Bester gemessener Aufbau, der die
  Persona trägt: `azure-eu`/`gpt-4.1-mini`, **p50 ~1,05–1,3 s, p90 ~1,3–1,8 s** je nach
  Tageszeit und Optionen.
- **Korrektur (2026-10-14):** Eine erste Fassung dieses Abschnitts nannte „alle Hebel geprüft".
  Für den Abschnitt nach dem LLM traf das nicht zu; nachgeprüft in §25/§26: TTS-Text-Streaming
  und Aura-2 sind langsamer, die TTS-Vorverbindung bringt −95 ms p50 / −107 ms p90 und ist
  übernommen, die Azure-Server-Zeit schwankt zeitlich ohne Hebel auf unserer Seite. Eine
  zwischenzeitliche Schätzung „p50 ~0,9 s, p90 ~1,15–1,2 s" war zu optimistisch: Sie rechnete den
  kurzen Einstieg als Gewinn (er bringt nur den ersten Laut früher, der Inhalt kommt ~500 ms später,
  §15) und ~300 ms TTS-Neuaufbau (auf der VM ~80 ms). **Stand jetzt gemessen: p50 ~1,1 s, p90
  ~1,34 s** (mit Vorverbindung). Die Schätzung „mit spekulativem Start ~1,0 s / ~1,27 s" ist
  durch die Messung der Kombination widerlegt (§27: −16 ms p50, p90 unverändert): Das vollständige
  Transkript liegt erst ~300 ms nach dem Sprechende vor, ~70 ms vor dem Turn-Ende; mehr kann ein
  früherer LLM-Start nicht gewinnen. Ungemessen bleiben nur kleine Hebel (erste TTS-Anfrage an
  sicherer Teilsatzgrenze, OpenAI-Region). Die Lücke zu 900 ms p90 liegt bei ~350–450 ms.
- **Inhaltlich trägt der Stack:** Rollentreue erfüllt (§20), im Sprachgespräch Information in 3/53
  Fällen übergangen, kein Rollenbruch (§21). Kosten ~2,7 ct/Gesprächsminute.
- **Das größere Gesprächsproblem ist das Turn-Taking, nicht die Latenz:** Mit echter Sprache
  spricht die Persona bei Denkpausen in ~1/3 der Äußerungen hinein (T1, F3 23/63), und Hörersignale
  („Mhm") unterbrechen sie (§19). Das merkt ein Nutzer vermutlich stärker als 300 ms mehr
  Antwortzeit.

### 6.2 Was noch fehlt (Gründer)

Stimmbewertung Blind-A/B (Muss 2), Barge-in live mit Headset, README-Probelauf (Muss 8),
AVV-/DPA-Prüfung (Muss 5), Einordnung Smart Turn vs. Prosodie-Verbot. Fällt die Stimmbewertung
durch oder ist ein AVV nicht zu bekommen, ändert das die Lage stärker als jede Latenzzahl.

### 6.3 Optionen

| Option | Inhalt | Voraussetzung | Risiko |
|---|---|---|---|
| **A — Go mit angepasstem Ziel** | Phase 1 mit `azure-eu`/`mini`. Latenzziel neu: z. B. p50 ≤ 1,2 s, p90 ≤ 1,5 s. Früh ein Nutzertest: Empfinden SDRs ~1,2 s im Training als störend? Schwerpunkt Turn-Taking (Denkpausen, Hörersignale) | Muss 2, 5, 8 bestanden; Lasttest (Prio 0) | Nutzer empfinden die Pausen als unnatürlich; das Produktversprechen „ohne Verzögerung" (Landingpage) muss angepasst werden |
| **B — No-Go / Umbau** | Wenn ~900 ms für das Produkt unverzichtbar sind: Projekt in dieser Form anhalten | — | Kein Weg innerhalb der EU-Vorgaben in Sicht; Lockerung der Vorgaben (US-Dienste) widerspricht der Positionierung |
| **C — Warten und nachmessen** | Kein Phase-1-Start; Messwerkzeuge stehen, Nachmessung bei neuen Diensten (z. B. Flux-Updates, schnellere EU-Modelle) | — | Zeitverlust ohne Garantie |

### 6.4 Einschätzung (Claude)

Option A ist vertretbar, **wenn** die offenen Gründer-Punkte bestehen und ein früher Nutzertest
zeigt, dass ~1,2 s im Trainingskontext akzeptiert werden. Ob das so ist, kann ich aus den Messungen
nicht ableiten — normale Gesprächspausen liegen deutlich darunter, ein Trainingsgespräch mit einer
erkennbaren KI ist aber kein normales Telefonat. Unabhängig von der Option sollte die
Landingpage-Aussage „ohne Verzögerung" angepasst werden, solange das Ziel nicht erreicht ist.

## 7. Offene Punkte

| Punkt | Wer |
|---|---|
| Barge-in live mit Headset | Pit |
| Stimmbewertung Blind-A/B | beide Gründer |
| README-Probelauf | Kollege |
| DPA, Hetzner-AVV, Product Terms, Missbrauchsüberwachung | Pit |
| Smart Turn vs. Prosodie-Verbot | Pit |
| Aufnahmen der Robustheitsprobe löschen (Einwilligung) | nach Abschluss Phase 0 |
| Go/No-Go-Gespräch (§6) | Pit, Marvin |
| AVV Deepgram/Gladia prüfen, falls Flux als STT-Alternative in Frage kommt (§24) | Pit |
| **Prio 0 für Phase 1 — Lasttest gleichzeitiger Gespräche:** Alle Phase-0-Messungen laufen mit genau einem Gespräch (Messhygiene, Summary §13.6). Ob das System mehrere Nutzer gleichzeitig trägt, ist ungeprüft; im Tarif F0 scheiterte bereits die zweite STT-Verbindung („Quota exceeded“, Testablauf Nachtrag 2). Vorgehen: tatsächliche Kontingente auslesen (Azure Speech S0: gleichzeitige STT-Verbindungen; Azure OpenAI: TPM/RPM des Deployments), dann 1 / 5 / 10 synthetische Anrufer gleichzeitig (`synthetic_caller` parallel), je Stufe E2E-p50/p90, Fehlerquote und CPU-Last des Agents (Silero VAD + Smart Turn je Sitzung). Kriterium: keine Dienstfehler und Latenz unter Last nicht spürbar schlechter als im Einzelgespräch (Grenze mit dem neuen Latenzziel aus §6 festlegen; 900 ms sind auch einzeln nicht erreichbar). Hinweis: Auch mit Speech S0 trat am 2026-10-12 einmal „Quota exceeded" auf (§23). Nur ohne andere laufende Messung. Ergebnis bestimmt Kontingent-Anhebung, Deployment-Typ (Standard vs. reservierte Kapazität) und Agent-Dimensionierung. | Phase 1, Claude — vor allem anderen |
| **Kosten-ToDo STT-Streaming:** Die Pipeline streamt das Mikrofon das ganze Gespräch lang an Azure STT; abgerechnet wird gestreamtes Audio (~1,7 ct/Min., über die Hälfte der Speech-Kosten). Audio nur senden, wenn die lokale VAD Sprache erkennt (mit kurzem Vorlauf-Puffer, damit Wortanfänge nicht fehlen), könnte die Persona-Redezeit und Stille einsparen — grob bis zur Hälfte der STT-Kosten. Vorher prüfen: Abrechnungsbasis bei Azure bestätigen, Wiedereinstieg/Latenz des STT-Streams, Erkennungsgenauigkeit, Barge-in unverändert (läuft über die lokale VAD). | Phase 1, Claude |

## 8. Gründerentscheidung und Abschluss (2026-10-27)

### 8.1 Entscheidung

- **Sprachpfad:** OpenAI GPT-Live (`gpt-live-1`, Hintergrundmodell `gpt-4.1-mini`), Pit und
  Marvin am 2026-10-15 nach Browser-Schnelltest. Die Azure-Kaskade (`azure-eu`/`mini`) bleibt
  als Rückfall im Code.
- **Latenz:** Die gemessene GPT-Live-Latenz ist als angemessen beschlossen (Pit, 2026-10-27).
  Gemessen (Summary §28, nicht präregistriert, Region `referenz`): Agent-Ausgabe p50/p90
  1622/2452 ms mit synthetischen Clips, 2454/3324 ms mit Pits Aufnahmen; im Browser direkt per
  WebRTC Median 1215 ms (9 Clips). Damit ist GPT-Live **langsamer** als die Kaskade
  (p50 ~1,1 s, p90 ~1,34 s); ausschlaggebend waren Stimme, Gesprächsgefühl und Turn-Taking
  (kaum Hineinsprechen, keine Unterbrechung durch Hörersignale, §28).
  p90 < 900 ms gilt nicht mehr als Muss. Neue Zielwerte setzen die Gründer; bis dahin dürfen
  Änderungen die Latenz nicht ungemessen verschlechtern.
- **EU-Residenz:** EU-Projekt bei OpenAI beantragt, Freigabe ausstehend. Die Entwicklung wird
  davon nicht abhängig gemacht (Pit, 2026-10-27): Entwicklung und Tests über `referenz` mit
  synthetischen Daten und Pits eigener Stimme (Freigabe 2026-10-15). **Reale Nutzer (Pilot)
  erst nach EU-Freigabe und geprüftem OpenAI-DPA.**

### 8.2 Muss-Kriterien unter GPT-Live

| # | Kriterium | Stand mit GPT-Live |
|---|---|---|
| 1 | Latenz | durch Gründerentscheidung ersetzt (8.1); Lasttest gleichzeitiger Gespräche [offen], [Plan](./phase-1-lasttest.md) |
| 2 | Sprachqualität | Pit: alle 8 Stimmen im Browsertest „sehr gut“ (2026-10-27, informell, kein Blind-A/B); Marvin [offen] |
| 3 | Barge-in | Turn-Erkennung serverseitig durch GPT-Live; im T1-Lauf kaum Hineinsprechen (§28). Barge-in live mit Headset [offen] |
| 4 | Rollen-Konsistenz | T1 mit GPT-Live: Rolle durchgehend gehalten, Information übergangen 0/19 (Judge, §28) |
| 5 | EU-Compliance | EU-Projekt beantragt; OpenAI-DPA [offen, Pit]; Faktenblatt um OpenAI ergänzen [offen] |
| 6 | Transkript + Timing | erfüllt über den Pipecat-Pfad (Stack `live`) |
| 7 | Kosten | `gpt-live-1` 0,05 $/Min. Sitzungsdauer, sekundengenau, plus Hintergrundmodell (Preisliste 2026-10-27); Kaskade ~0,03 $ |
| 8 | Reproduzierbarkeit | [offen]; README beschreibt noch die Kaskade |

### 8.3 Offene Punkte aus §7, neu eingeordnet

| Punkt | Stand |
|---|---|
| Lasttest (Prio 0) | auf Stack `live` umgestellt: [phase-1-lasttest.md](./phase-1-lasttest.md), Umsetzung läuft |
| Barge-in live mit Headset | bleibt, jetzt mit GPT-Live (Pit) |
| Stimmbewertung | Pit erledigt (informell), Marvin offen |
| README-Probelauf | bleibt; README vorher auf GPT-Live umstellen |
| DPA/AVV | neu: OpenAI-DPA und EU-Freigabe (Voraussetzung Pilot); Hetzner-AVV bleibt |
| Smart Turn vs. Prosodie-Verbot | betrifft nur noch den Kaskaden-Rückfall |
| Aufnahmen der Robustheitsprobe löschen | von Pit zurückgestellt (2026-10-27); werden in automatischen Tests weiter genutzt |
| AVV Deepgram/Gladia, Kosten-ToDo STT-Streaming | entfallen mit GPT-Live (nur Kaskade) |
| Landingpage-Aussage „ohne Verzögerung“ (§6.4) | in `index_1.html` am 2026-10-27 keine Latenzaussage gefunden; vor Veröffentlichung erneut prüfen |
