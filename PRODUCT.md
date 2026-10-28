# Product
<!-- impeccable:product-schema 1 -->

## Platform
web

## Users
SDRs (Sales Development Representatives) in B2B-SaaS-Vertriebsteams. Sie üben Kaltakquise und
Erstgespräche am Laptop mit Headset, tagsüber, zwischen echten Calls – im Büro (auch
Großraum, Kollegen in Hörweite) und im Homeoffice (Pit, 2026-10-28). Ein Übungsgespräch dauert
höchstens 10 Minuten; währenddessen sprechen sie, hören zu und werfen nur Blicke auf den
Bildschirm.

## Product Purpose
OneTry (vormals Pacemaker) ist ein deutschsprachiger KI-Rollenspielpartner für Vertriebstraining: Ein SDR führt
ein Echtzeit-Telefongespräch mit einer KI-Persona (zuerst Markus Brandt, Head of Operations bei
einem Logistik-Mittelständler mit rund 180 Mitarbeitern, Kaltakquise). Ziel: realistisches,
jederzeit verfügbares Üben; später Transkript, Scoring nach Inhalt und Struktur und
Schlüsselmomente. Strategie: `Pacemaker.md`.

## Positioning
Echtzeit-Sprachrollenspiel auf Deutsch mit Personas, die Einwände, Zeitdruck und verdeckte
Schmerzpunkte haben; Auswertung ausschließlich nach Gesprächsinhalt und -struktur, nie nach
Stimme oder Emotion.

## Operating Context
Browser (Chrome/Edge und Firefox verbindlich, Safari nach Aufwand), Mikrofon und Headset,
Anmeldung mit Name und Passwort. Ablauf: anmelden → Gespräch starten → sprechen und zuhören,
Live-Transkript → Ende durch eigenes Beenden, Auflegen der Persona, Zeitlimit (10 min) oder
Inaktivität. In Phase 1 sieht jeder Nutzer nur eigene Gespräche; kein Manager-Dashboard.

## Capabilities and Constraints
- Schritt 2 (Phase 1): eine Persona, eine Gesprächsseite; kein Scoring, kein Verlauf, keine
  Persona-Auswahl, Stimme serverseitig fest.
- Web-only, Vite + TypeScript ohne UI-Framework, keine Laufzeitabhängigkeiten, strikte CSP
  (keine Inline-Skripte/-Stile, keine Drittanbieter-Ressourcen, Schriften selbst gehostet).
- Kein Audio-Mitschnitt, keine Auswertung von Stimme oder Emotion; lokale Pegelanzeige nur für
  die Sprach-Animation (ohne Speicherung, ohne Bewertung). Transkript nur im Speicher der Seite.
- Offen: Scoring, Ergebnisse, Verlauf, Self-Service-Login (spätere Schritte).

## Brand Commitments
- Name „OneTry“ (Pit, 2026-10-28; vormals Pacemaker). Logo: Zeichen aus offenem Ring und
  Pfeil (Navy `#04143B`, Orange `#FD5803`), Wortmarke „OneTry“; Original-Datei steht aus.
- UI-Texte Deutsch in der Sie-Form, kein Marketing-Ton.
- KI-Transparenz: Die KI-Natur des Gesprächspartners ist jederzeit erkennbar.
- Landingpage-Entwurf `index_1.html` (Navy `#1E223D`, Orange `#F5451B`, Space Grotesk + Inter):
  für die App **nicht verbindlich**. Gewählt (Pit, 2026-10-28): Entwurf C „Bühne“ in der
  Farbwelt Ultramarin (`docs/phase-1-schritt-2-web.md` §9).

## Evidence on Hand
Keine echten Kundendaten, Logos, Testimonials oder Zahlen. Entwürfe verwenden synthetische
Gesprächsinhalte und kennzeichnen sie nicht als echt.

## Product Principles
1. Das Gespräch steht im Vordergrund; die Oberfläche tritt zurück, solange gesprochen wird.
2. Zustand ist immer klar: verbunden, wer spricht, wie viel Zeit bleibt, wie es endete.
3. Ehrlich über die KI und über Daten: nichts versprechen, was das System nicht garantiert.
4. Übung, kein Prüfungsdruck: Abbrüche und Fehler werden sachlich erklärt, nicht bewertet.

## Accessibility & Inclusion
Tastaturbedienung, sichtbare Fokuszustände, Kontrast nach WCAG 2.2 AA, `aria-live` für Status
und Transkript, `prefers-reduced-motion` respektieren.
