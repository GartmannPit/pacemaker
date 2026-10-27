# Lasttest Stack `live` — 1/5/10/20 gleichzeitige Gespräche (2026-10-27)

**Präregistrierung:** [docs/phase-1-lasttest.md](../../docs/phase-1-lasttest.md) ·
**Kennzeichnung:** Baseline/Referenz (`api.openai.com`, keine EU-Residenz), synthetische Clips.

## Lauf

| Punkt | Wert |
|---|---|
| Ort | EU-Mess-VM (`pacemaker-mess-vm`, 2 vCPU, Hetzner) |
| Git | `4ed2b71`, sauber |
| Stack | `live`, `gpt-live-1`, Hintergrundmodell `gpt-4.1-mini`, Pipecat 1.12.0, Python 3.12.3 |
| Region | `referenz` |
| Fixtures | `agent/fixtures/audio`, `fixtures_sha` `3b448838cad8` (wie 2026-10-15) |
| Reihe | `E, L5, E, L10, E, L20, E`, je Sitzung 10 Clips, Start 20:49–21:16 MEZ |
| Messpunkt | Clip-Ende → erstes Persona-Audio am Ausgabe-Transport der VM (**Agent-Ausgabe**, keine Browser-E2E); daneben Server-Audio-Ankunft (`live_diag`) |
| Netz | RTT zu `api.openai.com` p50 13,9–14,2 ms über alle Blöcke |
| Kosten | 39 Sitzungen, 6124 s Live-Sitzungszeit ≈ **5,10 $** (Schätzung 5,85 $) |

## Ergebnis je Stufe (ohne Kaltstart-Turns)

| Stufe | Sitzungen | Turns gewertet (n) | Agent p50 / p90 ms | Server p50 / p90 ms | p90 / E | CPU Mittel / Max % | Dienstfehler-Sitzungen | Urteil Skript |
|---|--:|--:|--:|--:|--:|--:|--:|---|
| E (gepoolt) | 4 | 24 | 1839 / 2710 | 1670 / 2419 | 1,00 | 5 / 57 | 1 | Referenz |
| L5 | 5 | 40 | 1984 / 3010 | 1717 / 2658 | 1,11 | 17 / 100 | 0 | unklar |
| L10 | 10 | 82 | 1909 / 2717 | 1735 / 2492 | 1,00 | 31 / 101 | 0 | unklar |
| L20 | 20 | 166 | 1997 / 2871 | 1807 / 2521 | 1,06 | 43 / 101 | 6 | nicht bestanden |

Ausschlüsse: Kaltstarts je Sitzung (E 4, L5 5, L10 10, L20 20); Status `keine_turn_erkennung`
(E 2, L10 4, L20 8) und `keine_antwort` (L10 1, L20 2); `zerfallen` mit gültiger Latenz
enthalten (wie Summary §28). Kaltstart-Turns Agent p50: E 1571, L5 1770, L10 1775, L20 1791 ms.

## Einordnung (Nachtrag, nicht präregistriert)

- **Dienstfehler kamen vom aufgebrauchten OpenAI-Guthaben, nicht von der Last.** Die 6
  Fehlersitzungen in L20 traten erst 20:10:43–20:11:16 auf, nachdem alle 10 Clips eingespielt
  waren, beim Auflegen; die Anrufer-Logs nennen 36-mal „credits“. Der letzte Block 7-E wurde
  beim Start mit `credit_balance_exhausted` abgelehnt. Kein Rate-Limit-Fehler in der Reihe.
- Die Skript-Urteile „unklar“ für L5 und L10 folgen aus der Präregistrierung: L5 liegt mit
  1,11 im Band 1,1–1,3; L10 gilt als unklar, weil die Referenz wegen 7-E nicht vollständig ist
  und Status ausgeschlossen wurden. L20 „nicht bestanden“ allein wegen der Guthaben-Fehler.
- **Latenz unter Last:** p90 je Stufe 1,00–1,11 × Einzelgespräch, also innerhalb der
  20-%-Grenze. Server-Audio-Ankunft (OpenAI) verschiebt sich ähnlich wenig (p90 2419 → 2521 ms
  bei 20). Bis 20 gleichzeitige Gespräche ist kein Lasteffekt erkennbar.
- **TPM-Limit:** Das in der Konsole angezeigte Limit von 30.000 TPM für `gpt-live-1` hat bei
  20 gleichzeitigen Gesprächen nicht gegriffen. GPT-Live meldet je Sitzung nur Sekunden,
  keine Tokens; der Token-Export der Konsole führt `gpt-live-1` nicht auf.
- **VM:** Mittel 43 % bei 20 Gesprächen, kurze Spitzen auf 100 %. Für 20 reicht die
  2-vCPU-VM; darüber oder mit Browser-Transport ist sie der erste Engpass.
- Orientierend: n = 40–166 Turns je Stufe, eine Runde. Keine belastbare p90-Aussage auf
  wenige Prozent (CLAUDE.md, Messvertrag).

## Folgerung

Für den ersten Kunden mit 20 Nutzern zeigt dieser Lauf keinen Hinweis auf ein Last- oder
Kontingentproblem bei OpenAI. Voraussetzung im Betrieb: ausreichendes Guthaben bzw.
Budgetgrenze mit Warnung, da ein leeres Guthaben laufende Gespräche beim Auflegen und neue
Sitzungen sofort abbricht. Eine Wiederholung nur für die formalen Urteile ist nicht geplant.
