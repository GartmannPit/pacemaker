# Bestandsaufnahme der Phase-0-Muss-Kriterien

**Stand:** 2026-10-08 abends · **Verfasser:** Claude · **Bezug:**
[Phase-0-Plan §2](./phase-0-proof-of-concept.md), [überarbeiteter Plan §4](./2026-10-07-pruefung-kritik-naechste-schritte.md)

Phase 0 gilt laut Plan erst als **bestanden**, wenn alle Muss-Kriterien erfüllt und dokumentiert
sind. Stand heute: **ein Kriterium nachgewiesen verfehlt, keines vollständig erfüllt.** Eine
Fortführung trotz offener Kriterien ist möglich, aber dann nicht als „bestanden" zu bezeichnen.

Legende: **erfüllt** = nachgewiesen mit Beleg · **verfehlt** = nachgewiesen nicht erfüllt ·
**teilweise** = Teile belegt, Rest offen · **ungeprüft** = keine belastbare Messung.

## Muss

| # | Kriterium | Status | Belege | Kleinster nächster Schritt | Wer |
|---|---|---|---|---|---|
| 1 | **Latenz** p90 < 900 ms, EU-Stack, ≥ 30 Turns von der EU-VM | **verfehlt** | Beste EU-Konfiguration (`azure-eu`, nano, Variante B): p90 je Lauf 1058 / 1231 / 1152 ms, p50 ~980 ms (Summary §15.2, 3 × 30 Turns, VM). Realtime p90 1254–2048 ms (§9, §12). US-Referenz Stack A p90 1501 ms (§12, nicht optimiert, Laptop). | Entscheidung: (a) begrenzter Architektur-Prototyp mit Abbruchkriterium oder (b) bewusste Fortführung mit verfehltem Kriterium bzw. Überprüfung der Schwelle mit echten Gesprächen | Pit (Entscheidung), Claude (Vorschlag) |
| 2 | **Sprachqualität**: beide Gründer, 1–5, Mittel ≥ 3,5, möglichst blind A/B | **ungeprüft** | Keine Bewertung. Stimme `de-DE-ConradNeural` nur informell gehört (Pits Probeläufe §15.4). | Blind-A/B-Paket (mehrere deutsche Azure-Stimmen, gleiche Persona-Sätze, zufällige Dateinamen, Bewertungsbogen) | Claude erzeugt, **beide Gründer bewerten** |
| 3 | **Barge-in** ≤ 300 ms in ≥ 9/10 Fällen | **ungeprüft** | `allow_interruptions=True` (`pipeline.py`); Unterbrechungen in Robustheitsreihen vorhanden, aber nie Start→Verstummen gemessen. Abbruchpfad für das Filtersignal des asynchronen Inhaltsfilters fehlt. | (1) Synthetische Messung serverseitig mit Pits Aufnahmen R23/R24 und Hörersignal R22; (2) 10 Live-Fälle mit Headset | Claude baut/misst, **Pit spricht (2)** |
| 4 | **Rollen-Konsistenz** über 10 Gespräche à ~5 Min., Keyword-Filter + LLM-Judge | **ungeprüft**, bekannte Mängel | Pits Probeläufe (§15.4, Nebentests 2026-10-08): Persona wiederholt den Prompt-Beispielsatz „Ich hab ehrlich gesagt keine drei Minuten" wörtlich, kann nicht auflegen (verabschiedet sich und redet weiter), Assistenten-Floskel „Kann ich sonst noch was für Sie tun?". Prompt verlangt „Du bist KEINE KI" — Konflikt mit KI-Transparenz (`CLAUDE.md`). | Prompt bereinigen + Auflege-Mechanismus; 10 Textgespräche mit verschiedenen Anrufertypen + Judge; danach einige Sprachgespräche | Claude; **Gründer** für Sprachgespräche |
| 5 | **EU-Compliance dokumentiert** je Subdienstleister; Latenzdifferenz EU vs. US beziffert | **teilweise** | Entwurf [`phase-0-eu-compliance.md`](./phase-0-eu-compliance.md): Regionen per DNS belegt, Deployment-Typ Data Zone EU, CLOUD-Act-Exposition benannt, Differenz als Stack-Vergleich beziffert (nicht fair: unterschiedlich optimiert). Offen: Microsoft-DPA für die Subscription, Hetzner-AVV, EU-Data-Boundary-Status Azure Speech, Missbrauchsüberwachung 30 Tage. | EUDB-Status recherchieren; DPA/AVV prüfen | Claude recherchiert, **Pit prüft DPA/AVV** |
| 6 | **Transkript + Timing** mit Zeitstempeln je Sprecherwechsel, als Datei exportierbar | **teilweise** | `metrics/transcript.py` schreibt je Lauf JSONL mit Rolle, Text, Unterbrechung und Zeitstempel **des Eintrags** (Turn-Ende), nicht Beginn/Ende je Sprecherwechsel. Kein lesbarer Export. | Beginn/Ende je Redebeitrag erfassen, Export als Markdown/CSV | Claude |
| 7 | **Kosten** pro Gesprächsminute je Stack, STT/LLM/TTS getrennt | **ungeprüft** | Nur Tokenzahlen je Lauf (§7, §9.4, §11.4). | Verbrauch aus einem Gesprächslauf (Audio-Sekunden, Tokens inkl. Cache, TTS-Zeichen) × aktuelle Preislisten | Claude |
| 8 | **Reproduzierbarkeit**: Dritte Person startet laut `README.md` in < 30 Min. ein Gespräch | **ungeprüft**, README veraltet | `README.md` beschreibt Stand „Woche 1" (mini, OpenAI in Germany West Central, keine Hinweise zu Python-Installation unter Windows, Data Zone, Inhaltsfilter). | README aktualisieren, Probelauf aus frischem Klon (Claude), dann **dritte Person** | Claude, **Kollege** |
| 9 | **Ergebnisdokument** `docs/phase-0-ergebnisse.md` mit Vergleichstabelle, Stack-Empfehlung, Go/No-Go | **fehlt** | — | Nach 2–8 schreiben; Go/No-Go-Einschätzung auch bei verfehlter Latenz | Claude schreibt, **Pit/Marvin entscheiden** |

## Soll

| Kriterium | Status | Beleg |
|---|---|---|
| Zweiter EU-Stack (C, souverän) vermessen | ungeprüft | Nicht aufgebaut. |
| Speech-to-Speech-Referenz (D) | erfüllt | Summary §9, §12: Realtime p90 1254 ms (30 Turns), Vorteil aus der Turn-Erkennung (~245 ms), Modell selbst nicht schneller. Persona-Treue dort ungeprüft. |
| VAD/Turn-Parameter grob getunt | erfüllt (grob) | §16–§18: Segmentierung 100 ms, VAD-Stopp 0,2 s, VAD-Start 0,1 s (vorläufig). |
| „Was uns überrascht hat" | offen | Teil des Ergebnisdokuments. |

## Weitere offene Punkte mit Abnahmerelevanz

| Punkt | Status | Beleg / nächster Schritt |
|---|---|---|
| Robustheit mit echter Sprache (Schritt C) | Befund, nicht abgeschlossen | §16–§18: gut die Hälfte der Sitzungen mit Denkpausen zerfällt; kein VAD-Parameter behebt das. Fehlt: zusammenhängendes Gespräch, Prüfung der Mindestinfo, getrennte Fehlerklassen. |
| Einwort-Antworten | Befund | „OK."/„Verstehe." warten ~1 s auf das Turn-Ende (Smart Turn: unvollständig), §18. |
| Smart Turn vs. Prosodie-Verbot | **offen, nicht entschieden** | Einordnung §2.3 (`2026-10-08-einordnung-pruefung-robustheitsprobe.md`); dokumentierte Klärung steht aus. |
| KI-Transparenz der Persona | **Konflikt** | Prompt: „Du bist KEINE KI". `CLAUDE.md`: KI-Natur jederzeit erkennbar. |
| Abbruch bei Filtersignal (asynchroner Inhaltsfilter) | fehlt | Phase-0-Compliance §3; gemeinsamer Abbruchpfad mit Barge-in. |

## Reihenfolge der nächsten Schritte

1. Testablauf festlegen ([`phase-0-testablauf-gespraech.md`](./phase-0-testablauf-gespraech.md)).
2. Persona: Prompt bereinigen, KI-Transparenz, Auflegen (Voraussetzung für 4 und das Gespräch).
3. Zusammenhängendes Gespräch + Barge-in/Hörersignale synthetisch (Kriterien 3, Schritt C).
4. Rollentreue-Test (Kriterium 4).
5. Transkript-Export, Kosten, Compliance-Recherche, README, Stimmproben (Kriterien 2, 5–8).
6. Ergebnisdokument mit Go/No-Go-Einschätzung (Kriterium 9) und — falls gerechtfertigt — genau
   einem begrenzten Architektur-Prototyp als Vorschlag.
