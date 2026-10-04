# EU-Mess-VM (Hetzner Cloud)

**Zweck:** Alle Latenzmessungen laufen von hier statt vom Entwicklungsrechner.

- **Stabile Messbedingungen** — der Hauptgrund. Am 2026-10-04 schwankte die Netzwerklaufzeit
  der Entwicklungsleitung zu Azure zwischen ~23 und 48–84 ms; dieselbe Konfiguration lieferte
  p90 1153 und 2178 ms. Das überdeckt Optimierungen von 100–300 ms
  (`experiments/summaries/2026-10-03-llm-modellvergleich-deployment-typen.md` §13.6).
- **Realistische Werte:** Im Produkt läuft der Agent auf einem EU-Server; Nürnberg/Falkenstein →
  Azure Frankfurt ~5–10 ms.
- **Basis für LiveKit** (Browser-Zugang, `infra/docker-compose.yml`) — für die Messungen noch
  nicht nötig.

**Compliance:** Hetzner Online GmbH, Rechenzentren in Deutschland, AVV im Kundenkonto
(Hetzner Console → Einstellungen/Datenschutz) abschließbar. Auf dem Server liegen dieselben
Azure-Schlüssel wie lokal (`agent/.env`); Zugriff nur per SSH-Key.

---

## 1. Konto (einmalig, Sie)

1. Konto anlegen: <https://accounts.hetzner.com/signUp> — Identitätsprüfung und Zahlungsmittel
   werden verlangt.
2. In der Cloud Console (<https://console.hetzner.cloud>) ein Projekt anlegen, z. B.
   `pacemaker`.
3. Optional: AVV abschließen (Kundenkonto → Datenschutz).

## 2. Server anlegen (Sie)

Im Projekt **„Server hinzufügen"** (Add Server):

| Feld | Wert |
|---|---|
| Standort | **Nürnberg** oder **Falkenstein** (Deutschland) |
| Image | **Ubuntu 24.04** |
| Typ | **Shared vCPU, x86** (Intel/AMD), kleinster Typ mit **2 vCPU / 4 GB RAM** (bisher `CX22`; Bezeichnung kann sich geändert haben). Kein ARM — nicht alle Audio-/ML-Pakete sind dort getestet |
| Netzwerk | Öffentliche IPv4 **an** (GitHub und manche APIs brauchen IPv4), IPv6 an |
| SSH-Schlüssel | **„SSH-Key hinzufügen"** → Inhalt von `~/.ssh/pacemaker_hetzner.pub` einfügen (steht auch in `infra/cloud-init.yaml`), Name `pacemaker-hetzner` |
| Firewall | keine nötig (die VM richtet `ufw` selbst ein); optional eine Hetzner-Firewall mit nur TCP 22 eingehend |
| Backups / Volumes | aus |
| **Cloud config** | **gesamten Inhalt von `infra/cloud-init.yaml` einfügen** |
| Name | `pacemaker-mess-vm` |

**„Kostenpflichtig erstellen"** — danach die **öffentliche IPv4** notieren und mir mitteilen.

Kosten: grob 4–5 € pro Monat, stundengenau abgerechnet (aktuellen Preis bei der Bestellung
prüfen). Nach Phase 0 Server **löschen** (Herunterfahren allein kostet weiter).

## 3. Einrichtung abwarten (automatisch, ~5 Min.)

Cloud-Init legt den Benutzer `pacemaker` an, schaltet Passwort- und Root-Login ab, aktiviert
die Firewall (nur SSH), installiert Pakete und `uv`, klont das Repo und führt `uv sync` aus.
Fertig, wenn `/home/pacemaker/cloud-init-fertig` existiert.

Verbindung vom Entwicklungsrechner:

```bash
ssh -i ~/.ssh/pacemaker_hetzner pacemaker@<IPv4>
```

## 4. Secrets und Test-Audios (ich, nach Ihrer Freigabe)

```bash
# Schlüssel übertragen (nur über SSH, nie über Git)
scp -i ~/.ssh/pacemaker_hetzner agent/.env pacemaker@<IPv4>:pacemaker/agent/.env
ssh -i ~/.ssh/pacemaker_hetzner pacemaker@<IPv4> 'chmod 600 pacemaker/agent/.env'

# Auf der VM: Test-Audios erzeugen (gitignored) und Netzwerk prüfen
cd pacemaker/agent
~/.local/bin/uv run python -m pacemaker_agent.tests.generate_fixtures
cd .. && bash infra/rtt-check.sh 20
```

## 5. Messen

```bash
cd ~/pacemaker && git pull
bash infra/rtt-check.sh 10                        # vorher
cd agent && AZURE_OPENAI_DEPLOYMENT=gpt-4.1-nano \
  ~/.local/bin/uv run python -m pacemaker_agent.tests.synthetic_caller --stack azure-eu --turns 30
cd .. && bash infra/rtt-check.sh 10               # nachher
```

Lange Läufe in `tmux` starten (`sudo apt install tmux`), damit ein Verbindungsabbruch sie nicht
beendet. Rohdaten bleiben in `experiments/runs/` auf der VM; Zusammenfassungen kommen wie
bisher per Git ins Repo.

## 6. Nach Phase 0

Server in der Cloud Console **löschen**. Den SSH-Key `pacemaker-hetzner` aus dem Projekt und
`~/.ssh/pacemaker_hetzner*` lokal entfernen. Azure-Schlüssel, die auf der VM lagen, rotieren.
