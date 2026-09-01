# EU-Mess-VM (Hetzner Cloud)

Zweck: Ab Woche 2 laufen **alle** Latenzmessungen von hier, nicht vom Entwicklerlaptop
— realistische Netzlatenz zu den Provider-Endpunkten. Siehe Phase-0-Plan §1.4.

## Provisionierung (Kurzform, wird in Woche 2 ausgearbeitet)

1. Hetzner-Cloud-Projekt anlegen, Standort **Nürnberg** oder **Falkenstein** (DE).
2. Server:
   - `CX22` (2 vCPU / 4 GB) reicht für den Agent + LiveKit.
   - `CPX31` (4 vCPU / 8 GB), falls self-hosted Whisper (Stack C) mit drauf soll.
3. Image: Ubuntu 24.04. SSH-Key hinterlegen, Passwort-Login deaktivieren.
4. Auf dem Server: Docker + `uv` installieren, Repo klonen, `agent/.env` mit denselben
   Azure-Keys befüllen.
5. Firewall: eingehend nur SSH (22) und LiveKit (7880–7882). Sonst alles zu.
6. Provider-Regionen möglichst nah wählen: Azure `Germany West Central` = Frankfurt,
   ~5–10 ms ab Nürnberg/Falkenstein.

## Messung durchführen

```bash
uv run python -m pacemaker_agent.tests.synthetic_caller --stack azure-eu --turns 30
uv run python -m pacemaker_agent.metrics.aggregate experiments/runs
```

## Kosten

`CX22` ~ 4 €/Monat. Nach Phase 0 Server löschen oder herunterfahren.
