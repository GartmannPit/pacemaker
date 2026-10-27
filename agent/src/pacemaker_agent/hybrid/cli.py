"""pacemaker-server: Server starten und Nutzer verwalten (Plan §3, Anmeldung).

    uv run pacemaker-server nutzer-anlegen <name>     # Passwort wird verdeckt abgefragt
    uv run pacemaker-server nutzer-sperren <name>
    uv run pacemaker-server nutzer-entsperren <name>
    uv run pacemaker-server serve

Konfiguration über Umgebungsvariablen (agent/.env.example).
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

from .auth import UserFile


def users_file() -> UserFile:
    path = os.environ.get("PACEMAKER_USERS_FILE")
    if not path:
        raise SystemExit("PACEMAKER_USERS_FILE ist nicht gesetzt.")
    return UserFile(Path(path).expanduser())


def cmd_add(name: str) -> None:
    first = getpass.getpass("Passwort: ")
    if first != getpass.getpass("Passwort wiederholen: "):
        raise SystemExit("Passwörter stimmen nicht überein.")
    try:
        user = users_file().upsert(name, first)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Nutzer {user.name} gespeichert.")


def cmd_disable(name: str, disabled: bool) -> None:
    try:
        user = users_file().set_disabled(name, disabled)
    except KeyError as exc:
        raise SystemExit(f"Unbekannter Nutzer: {name}") from exc
    print(f"Nutzer {user.name} {'gesperrt' if disabled else 'entsperrt'}.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="pacemaker-server")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for cmd in ("nutzer-anlegen", "nutzer-sperren", "nutzer-entsperren"):
        sub.add_parser(cmd).add_argument("name")
    sub.add_parser("serve")
    args = parser.parse_args(argv)
    if args.cmd == "nutzer-anlegen":
        cmd_add(args.name)
    elif args.cmd in ("nutzer-sperren", "nutzer-entsperren"):
        cmd_disable(args.name, args.cmd == "nutzer-sperren")
    else:
        from .server import serve  # Verdrahtung mit Register/Budget (Teil A)

        serve()


if __name__ == "__main__":
    main(sys.argv[1:])
