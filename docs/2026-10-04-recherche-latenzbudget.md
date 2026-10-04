# Recherche: Ist das 900-ms-Latenzbudget fundiert?

**Datum:** 2026-10-04
**Anlass:** Kein gemessener Stack erreicht das Phase-0-Kriterium „p90 < 900 ms", auch die
US-Baseline nicht (1501 ms p90, siehe
[`experiments/summaries/2026-10-03-llm-modellvergleich-deployment-typen.md`](../experiments/summaries/2026-10-03-llm-modellvergleich-deployment-typen.md) §12).
Frage: Ist die Schwelle belegt oder gesetzt?
**Status:** Recherche abgeschlossen. **Entscheidung über eine neue Schwelle offen** —
`CLAUDE.md` und `phase-0-proof-of-concept.md` sind unverändert.

---

## 1. Kurzfassung

Die 900 ms sind **plausibel, aber nicht belegt**. In den Projektunterlagen gibt es keine
Quelle. Die Forschung stützt eine Wahrnehmungsschwelle von **~700–800 ms für
Mensch-zu-Mensch-Gespräche**; für Gespräche mit Maschinen liegt die Toleranz bei **~1–2 s**.
„p90 < 900 ms" als K.-o.-Kriterium ist strenger als alles, was sich belegen lässt.

## 2. Herkunft im Projekt

| Dokument | Formulierung | Quelle |
|---|---|---|
| `Pacemaker.md`, Z. 62 | „< 700–900 ms **anstreben** (Mensch-zu-Mensch-Pausen liegen bei ~200 ms, alles über ~1,2 s wirkt ‚robotisch')" | keine |
| `Pacemaker.md`, Z. 96 | „Beweisen, dass < 900 ms Latenz … überhaupt erreichbar ist" | keine |
| `docs/phase-0-proof-of-concept.md` §0, §2 | „**p90** der E2E-Antwortzeit < 900 ms" als Abnahmekriterium | keine |
| `CLAUDE.md` | „p90 < 900 ms, Ziel p50 < 700 ms" als harter Produkt-Constraint | keine |

Aus einem Zielkorridor („anstreben") wurde schrittweise ein hartes p90-Kriterium — also eine
Schwelle, die 90 % aller Antworten einhalten müssen. Die 1,2-s-Angabe ist ebenfalls unbelegt.

## 3. Befunde aus der Forschung

### 3.1 Mensch-zu-Mensch

| Studie | Befund | Bedeutung |
|---|---|---|
| Stivers et al. 2009, *PNAS* 106(26) — 10 Sprachen | Pausen zwischen Sprecherwechseln liegen im Mittel bei ~200 ms; alle Sprachen innerhalb ±250 ms um den Durchschnitt. Langsamste: Dänisch (~0,5 s), schnellste: Japanisch (~7 ms). In allen Sprachen längere Pausen bei widersprechenden oder ausweichenden Antworten. Deutsch nicht in der Stichprobe | Menschen erwarten sehr schnelle Wechsel |
| Roberts & Francis (Roberts, Francis & Morgan 2006, *Speech Communication*) | Pausen 200–1200 ms in 100-ms-Schritten: zwischen 200 und 700 ms kein signifikanter Unterschied; **zwischen 700 und 800 ms** sinkt die wahrgenommene Bereitschaft des Antwortenden deutlich | Wahrnehmungsschwelle ~700–800 ms |
| Kendrick & Torreira 2015, *Discourse Processes* | Telefonkorpus: Ab ~**700 ms** Pause überwiegen ablehnende („dispreferred") gegenüber zustimmenden Antworten | Lange Pausen werden als Zögern/Ablehnung gelesen |

### 3.2 Mensch-Maschine

| Studie | Befund | Bedeutung |
|---|---|---|
| Shiwa, Kanda, Imai, Ishiguro, Hagita 2009, *Int. J. of Social Robotics* | Reaktionszeiten 0–3 s eines Gesprächsroboters verglichen: Präferenz-Gipfel bei **1 s**; Empfehlung: Antwort innerhalb **2 s**. Mit Füllwörtern („ähm …", „also …") wurden auch längere Verzögerungen kaum bemerkt bzw. nicht als störend empfunden | Bei Maschinen gilt ein anderer Maßstab; Füllwörter wirken |

### 3.3 Branchenangaben (keine Studien)

Voice-AI-Anbieter nennen verbreitet eine „800-ms-Regel" (Ende der Nutzeräußerung bis erstes
Audio). Das sind Erfahrungswerte aus Blogs, keine Studien. Eine dort zitierte
„Stanford-HCI-Studie" (unter 700 ms nicht unterscheidbar, über 1,5 s unnatürlich) ließ sich
**nicht auffinden** — nicht als Beleg verwenden.

## 4. Einordnung für Pacemaker

1. **900 ms liegen am Rand der Mensch-zu-Mensch-Schwelle** (700–800 ms) und deutlich unter der
   Maschinen-Toleranz (1–2 s). Als Ziel plausibel, als hartes p90-Kriterium nicht belegt.
2. **Produktspezifisches Argument für einen strengen Wert** (bisher nicht in der Strategie):
   Pausen ab ~700 ms werden als Zögern oder Ablehnung gelesen (§3.1). Antwortet die Persona
   technisch bedingt langsam, kann ein SDR das als Einwand-Signal missdeuten — das verfälscht
   genau das Gespräch, das trainiert werden soll. Das ist das stärkste Argument für ein
   strenges Ziel.
3. **Unsere Messung entspricht der erlebten Pause.** Pipecats `UserBotLatencyObserver` misst ab
   dem tatsächlichen Sprechende (VAD-Erkennungszeitpunkt minus `stop_secs`). Im Browser über
   WebRTC kommen Netz- und Puffer-Latenz hinzu (Größenordnung 50–150 ms, nicht gemessen). Die
   erlebte Pause ist also eher länger als die Messwerte.
4. **Füllwörter sind belegt wirksam** (§3.2). Ein sofortiges „Hm" oder „Moment …" der Persona
   würde die Wartezeit entschärfen und passt zu einer abweisenden Persona. Offen: Ob das als
   Latenz-„Trick" dem Trainingszweck widerspricht und wie die Messdefinition damit umgeht
   (erstes Audio = Füllwort?).

## 5. Vorschlag (zur Entscheidung)

| | Bisher | Vorschlag |
|---|---|---|
| Ziel | p50 < 700 ms | **p50 < 800 ms** (Wahrnehmungsschwelle laut §3.1) |
| Mindestanforderung | p90 < 900 ms (K.-o.) | **p90 < 1500 ms** (innerhalb der Maschinen-Toleranz laut §3.2) |
| Begründung | keine Quelle | Quellen aus §3, produktspezifisches Argument aus §4.2 |

Zusätzlich eine kleine **Wahrnehmungsprobe** mit echten Testgesprächen: Ab welcher Latenz
lesen SDRs die Pausen der Persona als Zögern? Das ersetzt die Literatur nicht, prüft aber das
Argument aus §4.2 direkt am Produkt.

Zum Vergleich der aktuelle Stand (bereinigte Messkette): Bester EU-Stack p50 1361 ms / p90
1628 ms, US-Baseline p50 1224 / p90 1501 ms. Auch der Vorschlag wäre also noch nicht erreicht —
er verschiebt das Ziel auf eine belegbare Größe, nicht auf den Messstand.

Bei Annahme anzupassen: `CLAUDE.md` (Latenzbudget), `docs/phase-0-proof-of-concept.md` §0, §2,
Risiko-Tabelle, sowie `E2E_TARGET_P90_MS` in `agent/src/pacemaker_agent/metrics/aggregate.py`.

## 6. Quellen

- Stivers, T. et al. (2009): Universals and cultural variation in turn-taking in conversation.
  *PNAS* 106(26), 10587–10592. <https://forms.mpi.nl/node/50939>
- Populärwissenschaftliche Zusammenfassung (National Geographic):
  <https://www.nationalgeographic.com/science/phenomena/2009/06/19/pregnant-pauses-and-rapid-fire-how-do-different-cultures-take-turns-to-talk/>
- Roberts, F., Francis, A. L. & Morgan, M. (2006): The interaction of inter-turn silence with
  prosodic cues in listener perceptions of „trouble" in conversation. *Speech Communication*.
  <https://emcawiki.net/Roberts2006>
- Übersichtsartikel mit Kendrick & Torreira (2015) und Roberts & Francis:
  <https://pmc.ncbi.nlm.nih.gov/articles/PMC4689543>
- Shiwa, T., Kanda, T., Imai, M., Ishiguro, H. & Hagita, N. (2009): How Quickly Should a
  Communication Robot Respond? Delaying Strategies and Habituation Effects. *International
  Journal of Social Robotics*. <https://unpaywall.org/10.1007%2FS12369-009-0012-8>
- Sekundärquelle zu Shiwa et al. (Arxiv 2025): <https://arxiv.org/pdf/2507.22352>
- Branchenblogs (keine Studien): <https://www.twig.so/blog/voice-ai-agents-latency-budget-800ms>,
  <https://www.parloa.com/labs/insights/the-latency-paradox/>

Hinweis: Die Zahlen zu Roberts & Francis, Kendrick & Torreira und Shiwa et al. stammen aus
Zusammenfassungen und Sekundärquellen; die Originalartikel wurden nicht im Volltext geprüft.
Vor einer Verwendung nach außen (Website, Vertrieb) gegenlesen.
