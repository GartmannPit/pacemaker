# Pacemaker — Technische Ausarbeitungsstrategie

*Basierend auf dem Website-Entwurf (index_1.html), Stand 20.08.2026*

---

## 1. Was der Entwurf bereits zeigt

Der Entwurf ist deutlich mehr als ein Mockup — er enthält bereits produktrelevante Entscheidungen, die die technische Architektur direkt vorwegnehmen:

- **Produktkern:** KI-Sprachrollenspiel für SDR-Training im deutschen B2B-SaaS-Vertrieb. Persona antwortet in Echtzeit per Sprache, hält Rolle (Budget, Geduldsschwelle, Einwände), liefert danach Transkript + Scoring.
- **Vier Trainingsszenarien:** Kaltakquise, Einwandbehandlung, Preisverhandlung, Umgang mit Widerstand.
- **Compliance-Versprechen, die bereits öffentlich gemacht werden:** ausschließliche Verarbeitung/Speicherung in der EU (Frankfurt), AVV mit Kunden und Subdienstleistern, Löschkonzept, EU-AI-Act-Transparenzpflicht ("KI-Natur jederzeit kenntlich"), **keine Emotionserkennung**.
- **Noch offene technische Platzhalter im Code:** `BOOKING_URL` und `FORM_ENDPOINT` sind leer, Impressum/Datenschutz sind als TODO markiert, kein Video eingebunden.

Das ist wichtig: Ihr habt auf der Landingpage bereits konkrete, überprüfbare Zusagen gemacht (EU-Hosting, keine Emotionserkennung, AI-Act-Konformität). Das ist gut fürs Marketing, bedeutet aber, dass die Architektur diese Zusagen von Tag 1 an einhalten muss — nicht nachträglich reparieren.

---

## 2. Quellenprüfung

Ich habe die drei im Code zitierten Quellen recherchiert:

| Quelle | Aussage auf der Seite | Prüfergebnis |
|---|---|---|
| **The Bridge Group, „SDR Models, Motions & Metrics", 2025** | Ramp-up 3,0 Monate; 40 % Fluktuation; 351 B2B-Unternehmen | **Bestätigt.** Der Bericht existiert, ist die 10. Auflage einer seit 2007 laufenden Studie, basiert auf 351 B2B-Unternehmen. Aktuelle Auswertungen (z. B. Prospeo, 2026) beziffern den Ramp-up mit "3,0 Monate – der niedrigste Wert seit 2010". Die Fluktuationszahl liegt je nach Sekundärquelle zwischen 34–40 %; 40 % ist am oberen, aber plausiblen Rand. Der 83-%-SaaS-Anteil ließ sich nicht separat verifizieren, ist aber für die Bridge-Group-Klientel plausibel. |
| **Sopro, „State of Prospecting 2025"** | Lead-Kosten international vergleichbar | **Bestätigt.** Report existiert (400+ befragte Entscheider, ausgewertete Outreach-Daten). Sopro selbst nennt je nach Kanal $25 (Referral) bis $840 (Messen), Multichannel-Durchschnitt ~$188. |
| **HubSpot CPL/CAC Benchmarks 2025** | dito | Die im Code verlinkte Studie ist eigentlich von **2022** (URL: `2022-cpl-and-cac-benchmarks`) — das solltet ihr entweder aktualisieren oder die Jahreszahl im Fließtext korrigieren, sonst wirkt es beim Nachprüfen unseriös. |
| **150–400 € pro qualifiziertem B2B-Lead (DE)** | eigene Markteinschätzung, extern gestützt | Die internationalen Benchmarks (Sopro, First Page Sage, HubSpot) liegen für B2B-SaaS-Leads bei rund $150–310 (blended), je nach Kanal auch deutlich darüber. Der Korridor ist **plausibel, aber nicht direkt für Deutschland belegt** — ich würde im Footnote-Text ergänzen, dass es sich um eine Übertragung internationaler Benchmarks handelt, nicht um eine deutsche Primärquelle. Das erhöht die Glaubwürdigkeit, statt sie zu untergraben.

**Empfehlung:** HubSpot-Link auf eine aktuelle Version (2025/26) austauschen und im Fließtext explizit kennzeichnen, welche Zahl aus welchem Land/welcher Studie stammt. Investoren und Sales-Manager, die selbst nachschauen, werden das honorieren.

---

## 3. Die zentrale technische Spannung, die zuerst geklärt werden muss

Ihr versprecht auf der Seite: *"Verarbeitung und Speicherung ausschließlich in der EU"* und *"Sprachdaten Ihrer Mitarbeiter gehören nicht in die USA"*. Das ist ein hartes, prüfbares Kundenversprechen — und es kollidiert mit der Realität der aktuell besten Voice-AI-Anbieter:

- **OpenAI Realtime / ElevenLabs Conversational AI / Anthropic API** sind US-Unternehmen. EU-Datenresidenz existiert mittlerweile (OpenAI EU-Projekte seit Anfang 2026, Azure OpenAI EU Data Zone, AWS Bedrock eu-central-1), ist aber an "eligible customer"-Status gebunden, bringt **200–500 ms Zusatzlatenz** und löst die **US-CLOUD-Act-Problematik nicht** — ein US-Mutterkonzern kann weiterhin zur Herausgabe verpflichtet werden, auch wenn die Server in Frankfurt stehen. "EU-Hosting" ist juristisch etwas anderes als "EU-Souveränität", und das Kleingedruckte in eurem AVV muss das sauber abbilden, sonst ist die Landingpage-Aussage angreifbar.
- **Latenz ist bei einem Live-Rollenspiel geschäftskritisch.** Ein Verkaufsgespräch-Simulator, der 300 ms zu spät antwortet, wirkt nicht mehr wie ein Mensch. Das ist kein Nice-to-have, sondern Kernfunktionalität.

**Konkrete Optionen, geordnet nach Kompromiss:**

1. **EU-souveräne Modelle (Mistral, Aleph Alpha/PhariaAI):** Mistral hat einen Pariser Mutterkonzern und einen eigenen EU-Datacenter-Fokus — aktuell die praktikabelste "wirklich europäische" Option für Text/Reasoning. Sprachqualität und Realtime-Fähigkeiten sind (Stand jetzt) aber hinter OpenAI/ElevenLabs.
2. **US-Modell über EU-Region (Azure OpenAI EU Data Zone, AWS Bedrock eu-central-1):** Bestes Verhältnis aus Qualität und Compliance-Aufwand; CLOUD-Act-Risiko bleibt, ist aber vertraglich (SCCs, DPA) abbildbar und in der Praxis der Branchenstandard, den auch viele deutsche Enterprise-Kunden akzeptieren.
3. **Self-Hosting offener Modelle (Llama/Qwen/Mistral auf Hetzner/STACKIT/OVH):** höchste Kontrolle, höchster Betriebsaufwand, aktuell schlechtere Sprachqualität als die Hyperscaler-Angebote.

**Meine Empfehlung für den Start:** Pipeline modular bauen (STT / LLM / TTS als austauschbare Komponenten), im Pilotbetrieb pragmatisch mit EU-Region eines etablierten Anbieters starten (Option 2), und in der AVV-Dokumentation transparent machen, dass "EU-Hosting" ungleich "EU-Souveränität" ist. Wenn Enterprise-Kunden das explizit fordern, Migration auf Option 1 oder 3 als Enterprise-Tier anbieten — genau da, wo eure Preisstaffelung ohnehin schon einen "Enterprise"-Tarif mit individuellem AVV vorsieht.

---

## 4. Architektur-Bausteine

### 4.1 Voice-Pipeline (das Herzstück)

```
Nutzer spricht ─▶ STT (Streaming) ─▶ Persona-Engine (LLM + Zustand) ─▶ TTS (Streaming) ─▶ Nutzer hört
                       │                        │
                       └── Transkript-Log ───────┴──▶ Scoring-Pipeline (async, nach Gesprächsende)
```

- **Latenzbudget:** Für ein glaubwürdiges Gespräch solltet ihr eine Ende-zu-Ende-Antwortzeit von < 700–900 ms anstreben (Mensch-zu-Mensch-Pausen liegen bei ~200 ms, alles über ~1,2 s wirkt "robotisch"). Das bestimmt eure Anbieterwahl stärker als reine Textqualität.
- **Streaming ist Pflicht**, nicht optional: STT muss Teilergebnisse liefern, LLM muss Token-Stream ausgeben, TTS muss chunk-weise synthetisieren, sonst addieren sich die Einzellatenzen.
- **Turn-Taking/Unterbrechung:** Realistische Verkaufsgespräche leben von Unterbrechungen ("Ich hab ehrlich gesagt keine drei Minuten") — das ist in eurem eigenen Hero-Mockup schon so dargestellt. Das erfordert Voice-Activity-Detection mit Barge-in-Fähigkeit, nicht nur simples Frage-Antwort.

### 4.2 Persona-Engine

- **Systemprompt + Zustandsmaschine statt reines Fine-Tuning:** Budgetgrenzen, Geduldsschwelle, Abbruchverhalten lassen sich zuverlässiger über einen strukturierten Zustand (z. B. "Geduld: 3/10, sinkt bei jeder Wiederholung") plus Prompt-Instruktionen abbilden als über Fine-Tuning eines Basismodells — einfacher zu debuggen, schneller zu iterieren, und pro Persona/Branche wiederverwendbar.
- **Rollen-Konsistenz ("bleibt in der Rolle"):** Das ist euer größtes Qualitätsrisiko. LLMs neigen dazu, aus der Rolle zu fallen oder zu hilfsbereit zu werden. Braucht: (a) harte Guardrails im Systemprompt, (b) eine Nachbearbeitungs-/Prüfschicht, die Rollenbrüche erkennt, (c) kontinuierliches Testen mit echten SDR-Gesprächsausschnitten als Regressionstests.
- **Branchenspezifische Personas ("Team"-Tarif verspricht das):** braucht eine Persona-Konfigurationsschicht (Branche, Produkt, typische Einwände), die Kunden ohne Prompt-Engineering-Kenntnisse selbst befüllen können — sonst bindet jede neue Kundenpersona Entwicklerzeit, was gegen euer Preismodell rechnet.

### 4.3 Scoring & Feedback

- **Explizit KEINE Emotionserkennung** — das ist nicht nur ein Marketingversprechen, sondern seit Februar 2025 eine **verbotene KI-Praxis nach Art. 5 EU-AI-Act** (Emotionserkennung am Arbeitsplatz), unabhängig vom späteren Zeitplan für Hochrisiko-Pflichten. Das bedeutet konkret: keine Prosodie-/Stimmlagen-Analyse zur Gefühlserkennung, kein "Stress-Score" o. ä. Euer Scoring darf sich nur auf Gesprächs**inhalt und -struktur** stützen (Redeanteil, Einwandbehandlung, Gesprächsführung) — das deckt sich mit dem, was ihr auf der Seite schreibt, muss aber technisch auch wirklich so gebaut sein (Audit-fest, falls je geprüft).
- **Scoring-Pipeline:** asynchron nach Gesprächsende, nicht Realtime — entkoppelt Qualität der Analyse von Latenzdruck. Transkript → strukturierte Analyse (Redeanteil-Berechnung aus Turn-Timestamps, Einwand-Erkennung über Klassifikation, Scoring-Rubrik) → Dashboard.
- **Nachvollziehbarkeit:** Da Scoring potenziell (auch wenn ihr das in der FAQ einschränkt) in Personalentscheidungen einfließen könnte, sollte jede Bewertung nachvollziehbar auf Transkript-Stellen zurückführbar sein — sonst wird die FAQ-Aussage ("kein Beurteilungsinstrument") in der Praxis schwer haltbar.

### 4.4 Datenschutz & Löschkonzept (technisch, nicht nur vertraglich)

- **Verschlüsselung:** TLS 1.3 in Transit, AES-256 at Rest — Standard, aber im AVV-Dokument technisch nachweisbar hinterlegen.
- **Löschkonzept technisch umsetzen:** automatisierte Retention-Policies (z. B. Rohaudio nach X Tagen löschen, Transkript nach Y Monaten), nicht manuell. Das ist prüfbar und wird bei ernsthaften Enterprise-Kunden abgefragt.
- **Mandantentrennung:** Da ihr Personas pro Kunde anpasst (Team-Tarif), muss die Datenarchitektur von Anfang an Multi-Tenant-fähig sein (getrennte Datenräume pro Kunde), nicht nachträglich aufgesetzt.
- **AVV-Kette:** Nicht nur mit dem Endkunden, auch mit jedem Subdienstleister (STT-, LLM-, TTS-Anbieter) — das ist bereits als Zusage auf der Seite formuliert, muss also vor dem ersten zahlenden Kunden tatsächlich unterschrieben vorliegen.

### 4.5 Dashboard & Infrastruktur

- **Manager-Dashboard** (Team-Tarif-Feature): braucht Aggregation über Nutzer hinweg, Trendanalyse ("dieselbe Schwachstelle im Team"), Rollen- und Rechtekonzept (wer sieht wessen Transkripte).
- **Hosting:** Frankfurt-Region ist im Text bereits festgelegt — AWS eu-central-1, Azure Germany West Central oder deutsche Anbieter (STACKIT, Hetzner Cloud) sind die naheliegenden Kandidaten; Wahl hängt von der Voice-Provider-Entscheidung aus Abschnitt 3 ab, da beide im selben Netz möglichst latenzarm zusammenspielen sollten.
- **Web-only, kein Rollout nötig** (wie versprochen): spricht für eine reine Browser-Lösung mit WebRTC für Audio-Streaming statt nativer App — technisch anspruchsvoller in der Latenzoptimierung, aber deckt euer "in Tagen startklar"-Versprechen.

---

## 5. Priorisierte Roadmap (MVP → Pilot → Skalierung)

**Phase 0 — Technischer Proof of Concept (2–4 Wochen)**
Ein einziges Szenario (z. B. Kaltakquise), eine Persona, Ende-zu-Ende-Latenztest mit 2–3 verschiedenen Voice-Provider-Kombinationen. Ziel: Beweisen, dass < 900 ms Latenz mit akzeptabler Sprachqualität auf Deutsch überhaupt erreichbar ist — das ist das größte technische Risiko und sollte vor allem anderen validiert werden.

**Phase 1 — MVP für Pilotkunden (6–10 Wochen)**
Alle vier Szenarien, Standard-Personas, Transkript + einfaches Scoring, Self-Service-Login, Löschkonzept technisch implementiert, ein AVV-fähiger Anbieter-Stack festgezurrt.

**Phase 2 — Team-Tarif-Fähigkeit (parallel/danach)**
Manager-Dashboard, konfigurierbare Personas ohne Entwicklereingriff, Mandantentrennung, Priority-Support-Prozesse.

**Phase 3 — Enterprise**
CRM-/LMS-Anbindung, SLA, ggf. EU-souveräner Modell-Stack als Option für Kunden mit strengeren Anforderungen als Standard-DPA/SCC.

---

## 6. Formulierungen entschärfen, wo die Technik noch nicht so weit ist

Die Landingpage macht an mehreren Stellen absolute Zusagen, die vor dem ersten Kunden entweder technisch/vertraglich abgesichert sein müssen — oder eben vorsichtiger formuliert werden sollten. Grundprinzip: von *"ist"/"erfüllt"* zu *"ausgelegt auf"/"schließen ab"/"orientiert an"* wechseln, solange der zugrundeliegende Zustand noch nicht final und geprüft ist.

### Hosting & Datenresidenz

| Original | Risiko | Abschwächung |
|---|---|---|
| „Verarbeitung und Speicherung ausschließlich in der EU — Hosting im Rechenzentrum Frankfurt" | Nennt einen konkreten Standort. Sobald zusätzlich eine EU-Region eines US-Anbieters (Azure/AWS eu-central-1) genutzt wird oder der Hyperscaler wechselt, stimmt der Satz nicht mehr exakt | „Verarbeitung und Speicherung ausschließlich in der EU" (Frankfurt als Regelfall im AVV nennen, nicht im Marketingtext festnageln) |
| „Sprachdaten Ihrer Mitarbeiter gehören nicht in die USA" | Absolutaussage. Bei US-Subdienstleistern (auch mit EU-Region) bleibt das CLOUD-Act-Risiko technisch bestehen | „Sprachdaten Ihrer Mitarbeiter werden in der EU verarbeitet" (sagt, wo verarbeitet wird, ohne eine juristische Unangreifbarkeit zu behaupten, die mit US-Subdienstleistern nicht haltbar ist) |

### Rechtliche Konformität

| Original | Risiko | Abschwächung |
|---|---|---|
| „Transparenzpflichten des EU AI Act erfüllt" | Behauptet abgeschlossene Compliance zu einem Gesetz, dessen Fristen sich zuletzt verschoben haben (Digital Omnibus, Dez. 2027/Aug. 2028 für Hochrisiko-Pflichten) — klingt wie ein bereits bestandener Audit | „Ausgelegt auf die Transparenzpflichten des EU AI Act — die KI-Natur des Gesprächspartners ist jederzeit erkennbar" |
| Hero-Note: „DSGVO-konform" (als Fakt neben „Kein Setup nötig") | Absolute Zertifizierungs-Anmutung, obwohl es keine Zertifizierung für DSGVO gibt | „DSGVO-orientiert entwickelt" — oder ganz weglassen und die Aussage nur im DSGVO-Abschnitt (mit mehr Kontext) treffen |
| FAQ: „…haben mit allen eingesetzten Dienstleistern entsprechende Verträge" | Behauptet, alle Sub-AVVs seien bereits unterschrieben — muss vor dem ersten Kundengespräch tatsächlich stimmen, sonst nachprüfbar falsch | „…und schließen mit allen eingesetzten Dienstleistern entsprechende Verträge ab" (Prozess statt vollendete Tatsache, bis die Verträge wirklich vorliegen) |
| Nutzen-Karte: „Kein Erklärungsnotstand gegenüber Ihrer IT oder dem Betriebsrat" | Impliziert, dass gar keine offenen Fragen mehr auftauchen können | „Sie haben eine klare Antwort für IT und Betriebsrat parat" (liefert die Grundlage, verspricht aber nicht, dass keine Rückfragen kommen) |

### Persona / Produktleistung

| Original | Risiko | Abschwächung |
|---|---|---|
| FAQ „Klingt die KI wirklich wie ein echter Gesprächspartner?" → Antwort verspricht Budgetgrenzen, hartnäckige Einwände, Geduldsschwelle als bereits fertiges Verhalten | Genau der in Abschnitt 4.2 beschriebene größte Qualitätsrisiko-Punkt (Rollen-Konsistenz) — vor dem ersten Live-Test nicht als fertige Tatsache verkaufen | „Die Personas sind darauf ausgelegt, in der Rolle zu bleiben…" statt „sind so angelegt, dass sie in der Rolle bleiben" |
| „In Tagen startklar" | Realistisch für Standard-Personas (Starter-Tarif), aber sobald „eigene Personas für Ihr Produkt" (Team-Tarif) dazukommen, nicht mehr in Tagen erledigt | Auf den Starter-Tarif beziehen oder „meist innerhalb weniger Tage" |

### Was bewusst **nicht** abgeschwächt werden sollte

- **„Keine Emotionserkennung"** — seit Februar 2025 keine Kür, sondern eine verbotene Praxis nach Art. 5 EU-AI-Act am Arbeitsplatz. Hier lohnt sich sogar eine *härtere* Formulierung, kein Zurückrudern — ein echtes, technisch auch tatsächlich eingehaltenes Unterscheidungsmerkmal.
- Die Bridge-Group-/Sopro-Zahlen im ROI-Rechner — bereits vorsichtig formuliert ("kein Einsparversprechen") und extern belegt.
- Der Pilotphase-Hinweis bei den Preisen — genau die richtige Absicherung, so beibehalten.

---

## 7. Vor dem ersten Kundengespräch zu klären

Diese Punkte sind aktuell TODOs im Code oder Lücken in der Argumentationskette und sollten vor Live-Betrieb geschlossen sein:

1. **Impressum & Datenschutzerklärung** sind im Footer explizit als TODO markiert — vor Livegang und insbesondere vor dem ersten Formular-Absenden rechtlich zwingend.
2. **`FORM_ENDPOINT` und `BOOKING_URL`** sind Platzhalter — ohne echtes Backend läuft aktuell jede Lead-Anfrage ins Leere (das Formular zeigt zwar einen Hinweis, das ist aber nur für den Testbetrieb tragbar).
3. **AVV mit Sub-Dienstleistern** (STT/LLM/TTS-Anbieter) müssen tatsächlich existieren, bevor ihr das auf der Seite als Fakt kommuniziert.
4. **HubSpot-Quelle** auf aktuelle Version aktualisieren (siehe Abschnitt 2).
5. **EU-Hosting vs. EU-Souveränität** — intern eine ehrliche Linie festlegen, wie ihr das gegenüber sicherheitsbewussten Kunden kommuniziert, bevor ein technisch versierter Prospect das im Sales-Gespräch hinterfragt.
6. **Formulierungen aus Abschnitt 6 durchgehen** und im Text ersetzen, bevor die Seite live geht — insbesondere die Absolutaussagen zu Hosting-Standort, AI-Act-Konformität und bereits unterschriebenen Sub-AVVs.

---

## Kurzfazit

Das Produktkonzept ist klar und die Positionierung (DSGVO, EU-Hosting, keine Emotionserkennung, AI-Act-konform) ist ein echter Wettbewerbsvorteil im deutschen Markt — vorausgesetzt, die Architektur hält, was der Text verspricht. Das größte technische Risiko ist nicht die KI-Qualität, sondern die **Kombination aus Echtzeit-Sprachlatenz und EU-Datenresidenz-Anforderung** — diese Entscheidung sollte vor allen anderen Architekturfragen fallen, weil sie Anbieterwahl, Kostenstruktur und Compliance-Aussagen gleichzeitig bestimmt.