# Phase 0 — Ergebnisse

**Stand:** 2026-10-11 · **Verfasser:** Claude · **Status:** ENTWURF — offene Messungen und
Gründer-Bewertungen sind mit **[offen]** markiert.
**Bezug:** [Phase-0-Plan](./phase-0-proof-of-concept.md) · [Bestandsaufnahme](./2026-10-08-bestandsaufnahme-muss-kriterien.md) ·
[Testablauf](./phase-0-testablauf-gespraech.md) · Messprotokoll: [Summary §1–§20](../experiments/summaries/2026-10-03-llm-modellvergleich-deployment-typen.md)

## 1. Kurzfassung

Phase 0 sollte beantworten, ob eine deutsche Sprach-Persona mit **< 900 ms p90** Antwortzeit,
**akzeptabler Sprachqualität** und **EU-Datenresidenz** erreichbar ist.

- **Latenz: verfehlt.** Bester EU-Stack (`azure-eu`, `gpt-4.1-nano`) p90 1058–1231 ms je Lauf,
  p50 ~980 ms. Das Modell, das die Persona trägt (`gpt-4.1-mini`), ist langsamer **[offen:
  Kontrollmessung]**. Auch die US-Referenz und der Realtime-Stack lagen darüber.
- **Barge-in: verfehlt.** Serverseitig ≤ 300 ms nur in 0/10 (Default) bzw. 3/10 Fällen; die Zeit
  steckt in der Bestätigung des Sprechbeginns. Hörersignale („Mhm") unterbrechen die Persona fast
  immer.
- **Rollentreue: mit `gpt-4.1-mini` im Textmodus erfüllt**, mit `nano` nicht.
- **Sprachqualität, Reproduzierbarkeit durch Dritte, AVV-Prüfung: [offen, Gründer].**
- **Kosten:** ~3 ct je Gesprächsminute (`azure-eu`), Obergrenze **[offen: aus Gesprächslauf]**.

**Phase 0 ist nicht bestanden.** Zwei Muss-Kriterien sind nachgewiesen verfehlt, mehrere offen.
Die Go/No-Go-Einschätzung in §6 behandelt, ob und wie es trotzdem weitergehen kann.

## 2. Muss-Kriterien

| # | Kriterium | Status | Ergebnis | Beleg |
|---|---|---|---|---|
| 1 | Latenz p90 < 900 ms (EU, ≥ 30 Turns, VM) | **verfehlt** | nano p90 1058–1231 ms; mini **[offen]** | §15, §14, §9, §12 |
| 2 | Sprachqualität ≥ 3,5 (beide Gründer) | **[offen]** | Blind-A/B-Paket bereit (`tests/voice_samples.py`) | — |
| 3 | Barge-in ≤ 300 ms in ≥ 9/10 | **verfehlt** | 0/10 (VAD-Start 0,2 s), 3/10 (0,1 s), serverseitig; Live-Test **[offen]** | §19 |
| 4 | Rollen-Konsistenz, 10 Gespräche | **erfüllt (Textmodus, mini)** | 0/10 Rollenbrüche, Gespräche 4–6 Beiträge; nano verfehlt | §20 |
| 5 | EU-Compliance dokumentiert | **teilweise** | Regionen, Deployment-Typ, CLOUD Act, EUDB recherchiert; DPA/AVV-Prüfung **[offen, Pit]** | [Faktenblatt](./phase-0-eu-compliance.md) |
| 6 | Transkript + Timing exportierbar | **erfüllt** | Beginn/Ende je Redebeitrag, Export Markdown/CSV | `metrics/transcript_export.py` |
| 7 | Kosten pro Minute je Stack | **[offen: Messwerte]** | Werkzeug und Preise vorhanden | `metrics/costs.py`, §3.4 |
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
| `azure-eu` / `mini`, optimiert | VM, 3 × 30 Turns | **[offen]** | **[offen]** | Nachtrag 3 |
| Realtime `gpt-realtime-2.1` (`minimal`) | Laptop | 1208 | 2048 | §11/§12 |
| US-Referenz (Deepgram, OpenAI, ElevenLabs) | Laptop, nicht optimiert | 1224 | 1501 | §12 |

Zerlegung (nano, p50): Turn-Erkennung ~350 ms, LLM bis erster Text ~360 ms, TTS ~110–130 ms.
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
- Zusammenhängendes Gespräch (T1) **[offen]** — bisherige Läufe ungültig (Azure-STT-Kontingent).

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

Je Gesprächsminute (vorläufig aus Funktionstest, LLM ohne Cache-Rabatt): `azure-eu`/nano
~0,030 $, /mini ~0,032 $; davon STT ~0,017 $ und TTS ~0,012 $. US-Referenz bei gleichem Verbrauch
~0,052 $ (TTS teurer). **[offen: Werte aus T1-Gespräch]**

### 3.5 EU-Compliance

Siehe [Faktenblatt](./phase-0-eu-compliance.md): Alle Produktdienste in EU-Regionen (Speech
Germany West Central, OpenAI Sweden Central Data Zone EU, Server Hetzner DE); Microsoft als
US-Mutter (CLOUD Act) benannt; Azure Speech/OpenAI nicht auf der EUDB-Ausschlussliste. Offen:
DPA/AVV, Product Terms, Missbrauchsüberwachung (30 Tage), Smart Turn vs. Prosodie-Verbot
([Einordnung](./2026-10-08-einordnung-smart-turn-prosodie.md)).

## 4. Stack-Empfehlung für Phase 1

**`azure-eu` mit `gpt-4.1-mini`** (Data Zone EU), Azure Speech S0 Germany West Central, Stimme
**[offen: Blind-A/B]**, asynchroner Inhaltsfilter, Prompt-Durchgang 2. Begründung: einziger
getesteter EU-Stack, der die Persona trägt (§20); `nano` ist ~150 ms schneller, legt aber fast
sofort auf. Latenzabstand zur Vorgabe bewusst in Kauf genommen, siehe §6.

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

**[Entwurf — wird nach den offenen Messungen finalisiert.]**

## 7. Offene Punkte

| Punkt | Wer |
|---|---|
| T1 (Gespräch, mini) und Latenz-Kontrollmessung mini | Claude, sobald Azure STT wieder läuft (Tarif F0 → S0 am 2026-10-11) |
| Barge-in live mit Headset | Pit |
| Stimmbewertung Blind-A/B | beide Gründer |
| README-Probelauf | Kollege |
| DPA, Hetzner-AVV, Product Terms, Missbrauchsüberwachung | Pit |
| Smart Turn vs. Prosodie-Verbot | Pit |
| Aufnahmen der Robustheitsprobe löschen (Einwilligung) | nach Abschluss Phase 0 |
| **Kosten-ToDo STT-Streaming:** Die Pipeline streamt das Mikrofon das ganze Gespräch lang an Azure STT; abgerechnet wird gestreamtes Audio (~1,7 ct/Min., über die Hälfte der Speech-Kosten). Audio nur senden, wenn die lokale VAD Sprache erkennt (mit kurzem Vorlauf-Puffer, damit Wortanfänge nicht fehlen), könnte die Persona-Redezeit und Stille einsparen — grob bis zur Hälfte der STT-Kosten. Vorher prüfen: Abrechnungsbasis bei Azure bestätigen, Wiedereinstieg/Latenz des STT-Streams, Erkennungsgenauigkeit, Barge-in unverändert (läuft über die lokale VAD). | Phase 1, Claude |
