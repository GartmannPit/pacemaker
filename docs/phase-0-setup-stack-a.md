# Phase 0 — Zugänge für Stack A (US-Baseline)

Stack A misst die technische Obergrenze: „Wie schnell geht es mit den schnellsten Anbietern
überhaupt?" Definition laut [`phase-0-proof-of-concept.md`](./phase-0-proof-of-concept.md) §1.3:

| Stufe | Anbieter | Modell |
|---|---|---|
| STT | Deepgram | Nova-3 (Deutsch) |
| LLM | OpenAI (direkt, nicht Azure) | `gpt-4.1-mini` |
| TTS | ElevenLabs | Flash v2.5 |

> **Nur Referenz, nie Produktpfad (`CLAUDE.md`).** Alle drei verarbeiten in den USA. Stack A
> läuft ausschließlich mit den synthetischen Test-Clips aus `generate_fixtures.py` — keine
> echten Stimmen, keine Gespräche mit realen Personen, keine Kundendaten. Messläufe tragen
> `stack: "baseline"` und werden in Summaries als „Baseline/Referenz" ausgewiesen.

Die Oberflächen der Anbieter ändern sich häufig — Menüpunkte können anders heißen als unten
beschrieben. Entscheidend ist jeweils: Konto, Zahlungsweg/Guthaben, API-Key, Ausgabenlimit.

---

## 1. Deepgram (STT)

1. Konto anlegen: <https://console.deepgram.com/signup>. Neue Konten bekommen in der Regel ein
   Startguthaben, das für viele Messläufe reicht — keine Kreditkarte nötig.
2. Projekt: Beim ersten Login wird ein Projekt angelegt; sonst eines anlegen (Name z. B.
   `pacemaker-phase0`).
3. API-Key: Im Projekt **API Keys → Create a New API Key**.
   - Rolle/Berechtigung: die niedrigste angebotene (z. B. „Member"), keine Admin-Rechte.
   - Ablauf: wenn angeboten, ein Ablaufdatum setzen (z. B. 90 Tage).
   - Den Key sofort kopieren — er wird nur einmal angezeigt.
4. In `agent/.env`: `DEEPGRAM_API_KEY=<key>`
5. Prüfen: Deepgram Nova-3 unterstützt Deutsch (`language=de`). Falls die Konsole bei
   „Models" etwas anderes zeigt, Bescheid geben — dann passen wir das Modell an.

**Kosten pro Messlauf:** ~2,5 min Audio → wenige Cent.

## 2. OpenAI (LLM)

1. Konto anlegen bzw. einloggen: <https://platform.openai.com/>. Das ist die **API-Plattform**,
   unabhängig von einem ChatGPT-Abo (ChatGPT Plus enthält kein API-Guthaben).
2. Organisation/Projekt: Unter **Settings → Projects** ein Projekt anlegen
   (z. B. `pacemaker-phase0`), damit Key und Kosten getrennt bleiben.
3. Guthaben: **Settings → Billing** — Prepaid-Guthaben aufladen. Der Mindestbetrag liegt
   üblicherweise bei 5 $; das reicht für sehr viele Läufe. Auto-Recharge **aus** lassen.
4. Ausgabenlimit: **Settings → Limits** (bzw. Projekt-Limits) ein Monatsbudget setzen,
   z. B. 10 $.
5. Modellzugriff: Im Projekt unter **Limits/Models** sicherstellen, dass `gpt-4.1-mini`
   erlaubt ist (bei neuen Projekten meist Standard).
6. API-Key: **API Keys → Create new secret key**, dem Projekt zuordnen, Berechtigung
   „Restricted" mit Schreibrecht nur für *Model capabilities / Chat Completions* reicht;
   „All" geht auch. Sofort kopieren.
7. In `agent/.env`: `OPENAI_API_KEY=<key>`

Hinweis: Über die API gesendete Daten werden laut OpenAI standardmäßig nicht zum Training
verwendet, aber bis zu 30 Tage zur Missbrauchserkennung gespeichert — ein Grund mehr, nur
synthetische Clips zu verwenden.

**Kosten pro Messlauf:** ~55.000 Input-Tokens (großteils gecacht) → ~1–2 Cent.

## 3. ElevenLabs (TTS)

1. Konto anlegen: <https://elevenlabs.io/>. Der kostenlose Plan enthält API-Zugriff und ein
   monatliches Zeichenkontingent. Ein Messlauf braucht grob 3.000–5.000 Zeichen; reicht das
   Kontingent nicht für mehrere Läufe, auf den kleinsten bezahlten Plan wechseln.
2. API-Key: Unter **Developers → API Keys** (bzw. Profil → API Keys) **Create API Key**.
   - Berechtigungen einschränken, wenn angeboten: *Text to Speech* (Zugriff) und *Voices*
     (lesen), alles andere aus.
   - Zeichen-/Credit-Limit für den Key setzen, wenn angeboten.
   - Sofort kopieren.
3. Stimme wählen: Eine **männliche Stimme**, die gut Deutsch spricht (Persona Markus Brandt).
   Flash v2.5 ist mehrsprachig — auch Standard-Stimmen sprechen Deutsch. Unter **Voices** eine
   Stimme auswählen, Probe auf Deutsch anhören, dann die **Voice ID** kopieren (über das
   Stimmen-Menü „Copy Voice ID" oder in den Stimmen-Details).
   - Stimmen aus der Community-Bibliothek sind im kostenlosen Plan über die API ggf.
     eingeschränkt — im Zweifel eine der vorinstallierten Stimmen nehmen.
4. In `agent/.env`:
   ```
   ELEVENLABS_API_KEY=<key>
   ELEVENLABS_VOICE_ID=<voice-id>
   ```

**Kosten pro Messlauf:** im kostenlosen Kontingent bzw. Cent-Bereich.

## 4. Abschluss

1. Alle vier Werte in `agent/.env` eintragen (Vorlage: Abschnitt „Stack A" in
   `agent/.env.example`). Keys **nicht** in Chat, Commits oder Doku kopieren.
2. Bescheid geben — dann folgt:
   - Pipecat-Extras `deepgram`, `elevenlabs`, `openai` in `agent/pyproject.toml`, `uv sync`
   - `_build_baseline()` in `stacks.py`
   - Probelauf (3 Turns), dann 30-Turn-Lauf mit
     `uv run python -m pacemaker_agent.tests.synthetic_caller --stack baseline --turns 30`
3. Nach Abschluss von Phase 0: Keys in allen drei Konsolen widerrufen.

**Gesamtkosten Stack A** für einige Messläufe: deutlich unter 5 $ (im Wesentlichen das
OpenAI-Mindestguthaben).
