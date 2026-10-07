# Nächste Schritte Phase 0

> **Überholt** durch [Prüfung der Kritik — überarbeiteter Plan](./2026-10-07-pruefung-kritik-naechste-schritte.md) §4.
> Insbesondere fehlten hier die übrigen Muss-Kriterien des Phase-0-Plans, und der Browser ist
> dort „Kann", nicht Voraussetzung der Abnahme.

**Stand:** 2026-10-07
**Grundlage:** [Ergebnisse und Messreihe auf der EU-Mess-VM](../experiments/summaries/2026-10-03-llm-modellvergleich-deployment-typen.md) §14,
[unabhängige Projektbewertung](./2026-10-07-unabhaengige-projektbewertung.md) und
[deren Einordnung](./2026-10-07-einordnung-projektbewertung.md).

## Ausgangslage

- Bester EU-Stack (`azure-eu`, `gpt-4.1-nano`, alle Optimierungen) auf der EU-Mess-VM:
  **p50 ~900 ms, p90 1014–1206 ms** über drei Läufe. Das Kriterium p90 < 900 ms ist weiterhin
  um ~100–300 ms verfehlt.
- Die Messung endet beim ersten Audio — oft beim kurzen Einstieg („Hm, nee."). Wann der
  eigentliche Inhalt kommt, ist nicht gemessen.
- Gemessen wird nur mit sauberen synthetischen Clips über einen lokalen Transport. Browser,
  echte Sprache, Barge-in und Rollentreue sind nicht nachgewiesen.
- **Phase 0 ist nicht bestanden.** Weiterarbeiten: ja.

## Leitlinie

**Erst eine verlässliche, vollständige und glaubwürdige Unterhaltung messen, dann deren Tempo
optimieren.** Die letzten Tage haben vor allem Latenz optimiert; die Messkette hat nicht Schritt
gehalten. Weitere Latenzversuche lohnen erst, wenn ihre Wirkung sauber messbar ist und am
echten Endgerät ankommt.

Die Reihenfolge folgt deshalb den Abhängigkeiten, nicht dem erwarteten Latenzgewinn.

---

## Schritt 1 — Messkette reparieren

**Wer:** Claude · **Aufwand:** ca. ½ Tag

**Inhalt:**
- **Manifest je Lauf:** `run_id`, Git-Revision, Pipecat-Version, Deployment und Deployment-Typ,
  Filtermodus, STT-Segmentierung, VAD, Aufwärmen, Prompt- und Fixture-Hash. Die Auswertung fasst
  nur Läufe mit identischer Konfiguration zusammen und wertet sonst je Lauf aus.
- **Status je angebotener Äußerung:** beantwortet / Timeout / Audiofehler / abgebrochen.
  Fehlerrate getrennt ausweisen, statt Ausfälle still aus den Quantilen fallen zu lassen.
- **Zweite Kennzahl „Zeit bis zum Inhalt":** Ende der Nutzeräußerung → erstes Audio des Satzes
  nach dem kurzen Einstieg. Daneben Kaltstart (erster Turn) getrennt ausweisen.
- **Einheitliche Metrikdefinition** in `CLAUDE.md`, Phase-0-Plan und Collector: geschätztes
  Sprechende (VAD-Erkennung − `stop_secs`) → erstes Bot-Audio. So misst Pipecat tatsächlich.
- **Überdehnte Aussagen korrigieren** (Liste in der Einordnung, §4).
- Danach eine Kontrollmessung auf der VM: `mini` und `nano`, Reihenfolge je Wiederholung
  wechselnd.

**Warum jetzt und zuerst:**
1. **Die bisherigen Zahlen sind nur eingeschränkt belastbar.** Die Auswertung kann
   Konfigurationen nicht unterscheiden; bisher wurde per Hand sortiert. Ein heute gefundener
   Fehler (RTT-Dateien im Messordner) zeigt, wie leicht dabei etwas schiefgeht.
2. **Die wichtigste offene Frage hängt daran:** Ein Teil der jüngsten Gewinne kommt vom kurzen
   Einstieg. Ohne „Zeit bis zum Inhalt" wissen wir nicht, ob die Persona tatsächlich schneller
   *antwortet* oder nur schneller „Hm" sagt.
3. **Jeder spätere Schritt misst damit.** Browser, Robustheitskorpus und Architekturversuche
   brauchen dieselbe Messkette. Sie jetzt zu reparieren ist billiger als jede Auswertung später
   zu wiederholen.
4. **Ausfälle gehören zur Qualität.** Ein stummer Turn pro Gespräch ist für Nutzer schlimmer als
   200 ms mehr Latenz. Das muss sichtbar sein.

## Schritt 2 — Browser-Durchstich

**Wer:** Claude (Firewall-Freigabe mit Pit abstimmen) · **Aufwand:** 1–2 Tage

**Inhalt:**
- LiveKit auf der EU-Mess-VM (`infra/docker-compose.yml`), Firewall gezielt für LiveKit öffnen.
- Minimaler Web-Client in `web/` (Vite + TypeScript): verbinden, sprechen, hören, Transkript,
  Latenzanzeige. Kein Dashboard, kein Scoring.
- Agent mit LiveKit-Transport (`--transport livekit`).
- Prüfen: Latenz am Endgerät, Barge-in (Persona hört bei Unterbrechung auf), Audioqualität.
- KI-Transparenz im Client sichtbar (Constraint aus `CLAUDE.md`).

**Warum als zweites:**
1. **Das Abnahmekriterium ist ohne Browser nicht prüfbar.** Phase 0 verlangt einen Durchstich
   im Browser, und Barge-in lässt sich nur dort sinnvoll testen.
2. **Der Browser fügt eigene Latenz hinzu** (WebRTC-Jitterbuffer, Wiedergabepuffer, Netz des
   Nutzers). Grob 50–150 ms, die bisher in keiner Zahl stecken. Wie weit wir wirklich von
   900 ms entfernt sind, zeigt erst diese Messung.
3. **Der synthetische Ausgang ist eine Simulation.** Er verwirft Audio und simuliert nur die
   Abspieldauer. Ob Unterbrechungen, Audio-Stopp und Wiedergabe am Endgerät funktionieren, ist
   nicht nachgewiesen.
4. **Nach Schritt 1**, weil die Browser-Messungen sonst mit derselben unzuverlässigen Auswertung
   bewertet würden.

## Schritt 3 — Robustheitskorpus mit echter Sprache

**Wer:** Pit (Aufnahmen), Claude (Aufnahmeliste, Anleitung, Auswertung) · **Aufwand:** ca. 1 Stunde
Aufnahme · **parallel zu Schritt 1 und 2**

**Inhalt:**
- 20–30 Äußerungen wie ein echter SDR: Denkpausen von 300–1000 ms, Selbstkorrekturen, Zahlen,
  Firmennamen, Mehrsatzäußerungen, kurze Zwischenrufe. Claude erstellt die Liste mit
  Regieanweisungen und eine kurze Aufnahmeanleitung.
- Gewollte Gesprächsgrenzen vorher markieren.
- Schriftliche Einwilligung in der Doku (eigene Stimme, nur für Tests, nicht weitergeben).
- Auswertung: vorzeitige Antworten, fehlende Satzteile, unnötige Wartezeit. Nur Inhalt und
  Timing, **keine Emotions- oder Prosodieanalyse** (`CLAUDE.md`).
- Zusätzlich die bestehenden Clips als Gespräch **ohne wiederholten Opener** abspielen.

**Warum jetzt (parallel):**
1. **Die sauberen Clips verdecken die schwierigen Fälle.** Wir haben interne Pausen bewusst auf
   unter 200 ms gedrückt, um reproduzierbar zu messen. Echte Menschen machen genau diese Pausen —
   und dort entscheidet sich, ob die Persona dazwischenredet oder unnötig wartet.
2. **Mehrere Entscheidungen hängen daran:** Die 100-ms-Segmentierung (E3) ist nur für saubere
   Clips belegt; das 900-ms-Ziel ist wertlos, wenn es durch voreiliges Unterbrechen erreicht wird.
3. **Kein Engpass für Claude:** Die Aufnahmen kann Pit unabhängig von Schritt 1 und 2 machen; sie
   liegen dann bereit, wenn die Messkette steht.

## Schritt 4 — Latenz weiter senken, ein Hebel zur Zeit

**Wer:** Claude (Azure-Region ggf. Pit) · **Aufwand:** je Hebel ½–1 Tag plus Messreihe

**Inhalt, in dieser Reihenfolge:**
1. **Azure TextStream für die TTS:** Text fließt während der LLM-Generierung in einen laufenden
   Syntheseauftrag (WebSocket-v2-Endpoint), statt pro Satz eine Anfrage zu stellen. Eigener
   schmaler Adapter, Vergleich Satzmodus gegen TextStream mit gleicher Stimme, blind anhören.
2. **Region der Azure-OpenAI-Ressource prüfen:** Von der VM 28 ms statt ~5 ms wie zu Azure
   Speech. Ggf. Deployment in Germany West Central.
3. **Spekulativer LLM-Start:** Anfrage schon auf stabilem Zwischentranskript starten, nur
   übernehmen, wenn das finale Transkript übereinstimmt; **Audio erst nach bestätigter
   Turn-Grenze**. Mehrkosten und verworfene Anfragen mitmessen.

**Warum erst jetzt und so:**
1. **Erst mit Schritt 1–3 ist ein Gewinn messbar und relevant:** Die Streuung gleicher
   Konfigurationen liegt bei ~100–190 ms p90. Effekte dieser Größe brauchen mehrere Läufe und
   eine Auswertung, die Konfigurationen sauber trennt.
2. **Ein Hebel zur Zeit,** damit jeder Effekt zuordenbar bleibt. Gewinne werden gemessen, nicht
   aus Teilwerten addiert (p90 einer Summe ist nicht die Summe der p90).
3. **TextStream zuerst,** weil er die TTS-Zeit senkt, ohne einen festen Einstieg zu erzwingen —
   er verbessert auch die „Zeit bis zum Inhalt". Er ersetzt die Idee, kurze Einstiege vorab zu
   vertonen; die würde den Effekt nur auf das erste Audio verlagern.
4. **Spekulativer Start zuletzt,** weil er den größten Umbau und das größte Risiko hat (Persona
   darf nie auf einen halben Satz antworten).

## Schritt 5 — Filtersignal behandeln (vor dem Produktpfad)

**Wer:** Claude · **Aufwand:** ca. ½ Tag

**Inhalt:** Bei `finish_reason: content_filter` des asynchronen Azure-Inhaltsfilters TTS-
Warteschlange und Audioausgabe sofort stoppen; Verhalten der Persona danach festlegen.

**Warum:** Der asynchrone Filter (E2) ist der größte Latenzgewinn, liefert Text aber vor der
Prüfung aus. Bereits gesprochene Sprache lässt sich nicht zurückholen; verbleibende Ausgabe muss
abbrechen. Für Messläufe unkritisch, vor echten Nutzern Pflicht.

---

## Bewusst zurückgestellt

| Thema | Grund |
|---|---|
| VAD-/Segmentierungs-Kurve (100/200/300 ms) | Sinnvoll erst mit Robustheitskorpus (Schritt 3) |
| Realtime mit serverseitiger Turn-Erkennung | Schwerer Antwort-Tail im bisherigen Test; offene Compliance-Frage zu Rohaudio |
| Kurze Einstiege vorab vertonen | Verschiebt nur das erste Audio; TextStream ist der sauberere Weg |
| Änderung des 900-ms-Kriteriums | Erst nach Browser-Messung und Nutzerbeobachtung entscheiden |
| Scoring, Dashboard, Nutzerprüfung | Nicht Phase 0; Nutzerprüfung („lernen SDRs etwas?") als Merkposten für Phase 1 |

## Entscheidungen für Pit

1. Reihenfolge so übernehmen (Messkette → Browser, parallel Robustheitskorpus → Latenz)?
2. Zusage für die Aufnahmen des Robustheitskorpus?
3. Freigabe, die VM-Firewall für LiveKit zu öffnen (Schritt 2)?
4. Neue Commits pushen, damit die VM den aktuellen Stand per `git pull` holt.
