# Herkunft der Design-Skills (geprüfte Kopien)

Übernommen am 2026-10-28 für Phase 1, Schritt 2 (`docs/phase-1-schritt-2-web.md` §8). Inhalte vor
Aufnahme durchgesehen (Anweisungen an die Agenten). Identische Kopien unter `.claude/skills/`
(Claude Code) und `.agents/skills/` (Codex); Aktualisierung nur bewusst, mit erneuter Durchsicht.

| Skill | Quelle | Stand | Lizenz | Weggelassen |
|---|---|---|---|---|
| impeccable | github.com/pbakaus/impeccable, Release `skill-v4.8.0` (`universal.zip`, SHA-256 `82e6f6ff3a2b18f4…`) | 2026-10-26 | Apache-2.0 | `scripts/` (Engine-Launcher mit Binär-Download, Live-Browser-Modus), Hooks (`.claude/settings.json`, `.codex/hooks.json`), Subagenten für Bildgenerierung und Live-Bearbeitung |
| emil-design-eng, review-animations, break-ui | github.com/emilkowalski/skills @ `a81dbca` | 2026-10-28 | MIT | übrige Skills (React-/Bibliotheks-, Swift-, Expo-bezogen) |
| web-interface-guidelines | github.com/vercel-labs/web-interface-guidelines @ `434b7f9`, `command.md` mit Skill-Kopf | 2026-10-05 | MIT | `install.sh` |

Regeln für dieses Projekt:
- Impeccable läuft ohne Engine im dokumentierten Ersatzweg („Launcher unavailable“): Kontext aus
  `PRODUCT.md`/`DESIGN.md`. **`npx impeccable` und den Launcher nicht ausführen** (lädt ein
  Binärprogramm nach, Konzept-Abfrage an impeccable.style, Telemetrie standardmäßig an).
- Vorschläge, die React, Tailwind, UI-Bibliotheken, CDNs oder externe Schriften voraussetzen,
  gelten hier nicht (CLAUDE.md: kein UI-Framework, CSP, keine Drittanbieter-Ressourcen).
- Nur synthetische Inhalte in Screenshots und Prüfungen.
