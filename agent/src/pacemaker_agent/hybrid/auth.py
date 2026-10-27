"""Minimale Anmeldung (Plan §3): Nutzerdatei, scrypt, serverseitige Logins, Begrenzung.

Abweichung vom Plan, begründet: Das Cookie enthält nur eine zufällige Login-ID (32 Byte), die
der Server nachschlägt; ein HMAC-signiertes Cookie ist damit überflüssig. Widerruf (Logout,
Sperre, Passwortänderung) löscht serverseitig. Logins liegen nur im Speicher: Ein Neustart
meldet alle ab.
"""

from __future__ import annotations

import asyncio
import base64
import fcntl
import hashlib
import hmac
import json
import os
import secrets
import time
import unicodedata
from collections import OrderedDict
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

SCRYPT = {"n": 2**17, "r": 8, "p": 1, "dklen": 32}
SCRYPT_MAXMEM = 256 * 1024 * 1024
LOGIN_TTL_S = 12 * 3600
WINDOW_S = 15 * 60
MAX_FAILS_ACCOUNT = 5
MAX_FAILS_IP = 30
MAX_HASH_PARALLEL = 2
MAX_HASH_WAITING = 20
MIN_PASSWORD = 12


class AuthError(Exception):
    """Anmeldung abgewiesen; Meldung für Nutzer bewusst einheitlich."""


class RateLimited(Exception):
    def __init__(self, retry_after: int) -> None:
        super().__init__("zu viele Versuche")
        self.retry_after = retry_after


class Overloaded(Exception):
    """Zu viele gleichzeitige Passwortprüfungen."""


def normalize(name: str) -> str:
    return unicodedata.normalize("NFC", name).strip().lower()


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, maxmem=SCRYPT_MAXMEM, **SCRYPT)
    params = f"{SCRYPT['n']}${SCRYPT['r']}${SCRYPT['p']}"
    b64 = base64.b64encode
    return f"scrypt$v1${params}${b64(salt).decode()}${b64(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        kind, version, n, r, p, salt_b64, hash_b64 = stored.split("$")
        if kind != "scrypt" or version != "v1":
            return False
        salt, expected = base64.b64decode(salt_b64), base64.b64decode(hash_b64)
        digest = hashlib.scrypt(
            password.encode(),
            salt=salt,
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
            maxmem=SCRYPT_MAXMEM,
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest, expected)


# Für unbekannte Nutzer: gleicher Rechenaufwand, damit Antwortzeiten nichts verraten.
_DUMMY = hash_password(secrets.token_urlsafe(16))


@dataclass(frozen=True)
class User:
    id: str
    name: str
    password_hash: str
    disabled: bool = False
    login_version: int = 0  # erhöht bei Sperre und Passwortänderung → Logins ungültig


class UserFile:
    """Nutzerdatei (JSON). Verzeichnis 0700, Datei 0600, atomar geschrieben, gesperrt."""

    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def _locked(self):
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.path.parent, 0o700)
        lock = self.path.with_suffix(self.path.suffix + ".lock")
        with open(lock, "a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def load(self) -> dict[str, User]:
        """Beschädigte Datei → Fehler (Startverweigerung), fehlende Datei → leer."""
        if not self.path.exists():
            return {}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if data.get("version") != 1 or not isinstance(data.get("users"), list):
            raise ValueError("Nutzerdatei: unbekanntes Format")
        users = {}
        for row in data["users"]:
            user = User(
                id=str(row["id"]),
                name=normalize(str(row["name"])),
                password_hash=str(row["password_hash"]),
                disabled=bool(row.get("disabled", False)),
                login_version=int(row.get("login_version", 0)),
            )
            if user.name in users:
                raise ValueError("Nutzerdatei: doppelter Name")
            users[user.name] = user
        return users

    def _write(self, users: dict[str, User]) -> None:
        rows = [
            {
                "id": u.id,
                "name": u.name,
                "password_hash": u.password_hash,
                "disabled": u.disabled,
                "login_version": u.login_version,
            }
            for u in users.values()
        ]
        tmp = self.path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"version": 1, "users": rows}, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, self.path)
        os.chmod(self.path, 0o600)

    def upsert(self, name: str, password: str) -> User:
        """Anlegen oder Passwort setzen (bestehende ID bleibt)."""
        if len(password) < MIN_PASSWORD:
            raise ValueError(f"Passwort muss mindestens {MIN_PASSWORD} Zeichen haben")
        key = normalize(name)
        if not key or len(key) > 64:
            raise ValueError("Ungültiger Name")
        with self._locked():
            users = self.load()
            old = users.get(key)
            users[key] = User(
                id=old.id if old else secrets.token_hex(8),
                name=key,
                password_hash=hash_password(password),
                disabled=False,
                login_version=(old.login_version + 1) if old else 0,
            )
            self._write(users)
            return users[key]

    def set_disabled(self, name: str, disabled: bool) -> User:
        key = normalize(name)
        with self._locked():
            users = self.load()
            if key not in users:
                raise KeyError(name)
            old = users[key]
            version = old.login_version + (1 if disabled else 0)
            users[key] = User(old.id, old.name, old.password_hash, disabled, version)
            self._write(users)
            return users[key]


class _Window:
    """Fehlversuche je Schlüssel im gleitenden Fenster, Speicher begrenzt."""

    def __init__(self, limit: int, clock: Callable[[], float], max_keys: int = 10_000) -> None:
        self.limit, self.clock, self.max_keys = limit, clock, max_keys
        self.hits: OrderedDict[str, list[float]] = OrderedDict()

    def _fresh(self, key: str) -> list[float]:
        now = self.clock()
        hits = [t for t in self.hits.get(key, []) if now - t < WINDOW_S]
        if hits:
            self.hits[key] = hits
            self.hits.move_to_end(key)
        else:
            self.hits.pop(key, None)
        return hits

    def retry_after(self, key: str) -> int | None:
        hits = self._fresh(key)
        if len(hits) < self.limit:
            return None
        return max(1, int(WINDOW_S - (self.clock() - hits[0])) + 1)

    def add(self, key: str) -> None:
        self.hits.setdefault(key, []).append(self.clock())
        self.hits.move_to_end(key)
        while len(self.hits) > self.max_keys:
            self.hits.popitem(last=False)


@dataclass
class Login:
    user_id: str
    name: str
    expires: float
    login_version: int  # Abgleich mit der Nutzerdatei (Sperre, Passwortänderung)


class Auth:
    """Anmeldung prüfen, Logins führen und widerrufen."""

    def __init__(self, users: UserFile, *, clock: Callable[[], float] = time.monotonic) -> None:
        self.users = users
        self.clock = clock
        self._logins: dict[str, Login] = {}
        self._by_account = _Window(MAX_FAILS_ACCOUNT, clock)
        self._by_ip = _Window(MAX_FAILS_IP, clock)
        self._hash_slots = asyncio.Semaphore(MAX_HASH_PARALLEL)
        self._waiting = 0
        self._cache: tuple[float, dict[str, User]] = (-1.0, {})
        self._current()  # beschädigte Datei → Startverweigerung

    def _current(self) -> dict[str, User]:
        """Nutzerdatei nur bei Änderung neu lesen; die CLI ist ein eigener Prozess."""
        try:
            mtime = self.users.path.stat().st_mtime
        except FileNotFoundError:
            return {}
        if mtime != self._cache[0]:
            self._cache = (mtime, self.users.load())
        return self._cache[1]

    async def _verify(self, password: str, stored: str) -> bool:
        if self._waiting >= MAX_HASH_WAITING:
            raise Overloaded()
        self._waiting += 1
        try:
            async with self._hash_slots:
                return await asyncio.to_thread(verify_password, password, stored)
        finally:
            self._waiting -= 1

    async def login(self, name: str, password: str, ip: str) -> str:
        key = normalize(name)
        for window, k in ((self._by_account, key), (self._by_ip, ip)):
            wait = window.retry_after(k)
            if wait is not None:
                raise RateLimited(wait)
        user = (await asyncio.to_thread(self._current)).get(key)
        ok = await self._verify(password, user.password_hash if user else _DUMMY)
        if not ok or user is None or user.disabled:
            self._by_account.add(key)
            self._by_ip.add(ip)
            raise AuthError()
        login_id = secrets.token_urlsafe(32)
        self._logins[login_id] = Login(
            user.id, user.name, self.clock() + LOGIN_TTL_S, user.login_version
        )
        return login_id

    def resolve(self, login_id: str | None) -> Login | None:
        if not login_id:
            return None
        login = self._logins.get(login_id)
        if login is None:
            return None
        user = self._current().get(login.name)
        if (
            self.clock() >= login.expires
            or user is None
            or user.disabled
            or user.login_version != login.login_version
        ):
            # Ablauf, Sperre oder Passwortänderung (auch per CLI) widerrufen die Anmeldung.
            self._logins.pop(login_id, None)
            return None
        return login

    def logout(self, login_id: str | None) -> None:
        if login_id:
            self._logins.pop(login_id, None)

    def revoke_user(self, user_id: str) -> None:
        for key in [k for k, v in self._logins.items() if v.user_id == user_id]:
            del self._logins[key]
