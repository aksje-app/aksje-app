"""Persistent user store with authentication-specific backend separation."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import psycopg2  # type: ignore
except Exception:  # pragma: no cover
    psycopg2 = None  # type: ignore

from auth_persistence import (
    atomic_write_json,
    auth_database_url,
    auth_json_path,
    auth_storage_status,
    auth_using_postgres,
    read_json,
)

PBKDF2_ITERATIONS = 220_000
LEGACY_USERS_FILE = Path("app_users.json")


class DatabaseStarting(RuntimeError):
    pass


def _conn():
    if psycopg2 is None:
        raise RuntimeError("Autentiseringsdatabasedriver mangler")
    last_error = None
    for attempt in range(5):
        try:
            return psycopg2.connect(auth_database_url(), connect_timeout=5)
        except Exception as exc:
            last_error = exc
            text = str(exc).casefold()
            recoverable = any(token in text for token in (
                "not yet accepting connections", "recovery", "starting up",
                "connection refused", "could not connect",
            ))
            if not recoverable:
                raise
            if attempt < 4:
                time.sleep(0.75 * (attempt + 1))
    raise DatabaseStarting(f"Autentiseringsdatabasen starter fortsatt: {last_error}") from last_error


def hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_bytes(16)
    if isinstance(salt, str):
        salt = base64.b64decode(salt.encode("utf-8"))
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return {
        "salt": base64.b64encode(salt).decode("utf-8"),
        "hash": base64.b64encode(key).decode("utf-8"),
    }


def verify_password(password, salt, password_hash):
    candidate = hash_password(password, salt)["hash"]
    return hmac.compare_digest(candidate, password_hash)


def _users_file() -> Path:
    return auth_json_path("app_users.json")


def _migrate_legacy_file() -> None:
    target = _users_file()
    if target.exists() or not LEGACY_USERS_FILE.exists() or LEGACY_USERS_FILE.resolve() == target.resolve():
        return
    try:
        payload = json.loads(LEGACY_USERS_FILE.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and payload:
            for item in payload.values():
                if isinstance(item, dict):
                    item.setdefault("session_version", 1)
            atomic_write_json(target, payload)
    except Exception:
        pass


def init_user_store():
    status = auth_storage_status()
    if not status.get("ready"):
        raise RuntimeError(str(status.get("message") or "Autentiseringslageret er ikke klart"))
    if auth_using_postgres():
        conn = _conn()
        try:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS app_users (
                    username TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    active BOOLEAN NOT NULL DEFAULT TRUE,
                    session_version INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
            """)
            cur.execute("ALTER TABLE app_users ADD COLUMN IF NOT EXISTS session_version INTEGER NOT NULL DEFAULT 1;")
            conn.commit()
        finally:
            conn.close()
        return True

    _migrate_legacy_file()
    path = _users_file()
    if not path.exists():
        atomic_write_json(path, {})
    return False


def _load_file_users():
    init_user_store()
    payload = read_json(_users_file(), {})
    return payload if isinstance(payload, dict) else {}


def _save_file_users(users):
    atomic_write_json(_users_file(), users)


def list_users():
    init_user_store()
    if auth_using_postgres():
        conn = _conn()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT username, role, active, created_at, updated_at
                FROM app_users ORDER BY username
            """)
            rows = cur.fetchall()
        finally:
            conn.close()
        return [
            {"username": r[0], "role": r[1], "active": bool(r[2]), "created_at": r[3], "updated_at": r[4]}
            for r in rows
        ]
    users = _load_file_users()
    return [
        {
            "username": username,
            "role": data.get("role", "user"),
            "active": bool(data.get("active", True)),
            "created_at": data.get("created_at", ""),
            "updated_at": data.get("updated_at", ""),
        }
        for username, data in sorted(users.items())
    ]


def user_count():
    return len(list_users())


def get_user(username):
    init_user_store()
    username = str(username or "").strip().lower()
    if not username:
        return None
    if auth_using_postgres():
        conn = _conn()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT username, password_hash, salt, role, active, session_version, created_at, updated_at
                FROM app_users WHERE username=%s
            """, (username,))
            row = cur.fetchone()
        finally:
            conn.close()
        if not row:
            return None
        return {
            "username": row[0], "password_hash": row[1], "salt": row[2], "role": row[3],
            "active": bool(row[4]), "session_version": int(row[5] or 1),
            "created_at": row[6], "updated_at": row[7],
        }
    data = _load_file_users().get(username)
    if not data:
        return None
    return {"username": username, "session_version": int(data.get("session_version", 1) or 1), **data}


def create_user(username, password, role="user", active=True):
    init_user_store()
    username = str(username or "").strip().lower()
    role = "admin" if str(role).lower() == "admin" else "user"
    if not username:
        return False, "Brukernavn mangler"
    if len(password or "") < 8:
        return False, "Passord må være minst 8 tegn"
    if get_user(username):
        return False, "Bruker finnes allerede"
    hp = hash_password(password)
    now = datetime.now(timezone.utc).isoformat()
    if auth_using_postgres():
        conn = _conn()
        try:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO app_users
                (username, password_hash, salt, role, active, session_version, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, 1, %s, %s)
            """, (username, hp["hash"], hp["salt"], role, bool(active), now, now))
            conn.commit()
        finally:
            conn.close()
        return True, "Bruker opprettet"
    users = _load_file_users()
    users[username] = {
        "password_hash": hp["hash"], "salt": hp["salt"], "role": role, "active": bool(active),
        "session_version": 1, "created_at": now, "updated_at": now,
    }
    _save_file_users(users)
    return True, "Bruker opprettet"


def update_user(username, role=None, active=None, password=None):
    init_user_store()
    username = str(username or "").strip().lower()
    user = get_user(username)
    if not user:
        return False, "Bruker finnes ikke"
    new_role = user.get("role", "user") if role is None else ("admin" if str(role).lower() == "admin" else "user")
    new_active = user.get("active", True) if active is None else bool(active)
    now = datetime.now(timezone.utc).isoformat()
    password_changed = bool(password)
    active_invalidated = bool(user.get("active", True)) and not new_active
    session_version = int(user.get("session_version", 1) or 1) + (1 if password_changed or active_invalidated else 0)
    if password:
        if len(password) < 8:
            return False, "Passord må være minst 8 tegn"
        hp = hash_password(password)
        password_hash, salt = hp["hash"], hp["salt"]
    else:
        password_hash, salt = user["password_hash"], user["salt"]
    if auth_using_postgres():
        conn = _conn()
        try:
            cur = conn.cursor()
            cur.execute("""
                UPDATE app_users
                SET password_hash=%s, salt=%s, role=%s, active=%s, session_version=%s, updated_at=%s
                WHERE username=%s
            """, (password_hash, salt, new_role, new_active, session_version, now, username))
            conn.commit()
        finally:
            conn.close()
        return True, "Bruker oppdatert"
    users = _load_file_users()
    users[username].update({
        "password_hash": password_hash, "salt": salt, "role": new_role, "active": new_active,
        "session_version": session_version, "updated_at": now,
    })
    _save_file_users(users)
    return True, "Bruker oppdatert"


def delete_user(username):
    init_user_store()
    username = str(username or "").strip().lower()
    target = get_user(username)
    if not target:
        return False, "Bruker finnes ikke"
    active_admins = [
        item for item in list_users()
        if item["role"] == "admin" and item["active"] and item["username"] != username
    ]
    if target.get("role") == "admin" and not active_admins:
        return False, "Kan ikke slette siste aktive admin"
    if auth_using_postgres():
        conn = _conn()
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM app_users WHERE username=%s", (username,))
            conn.commit()
        finally:
            conn.close()
        return True, "Bruker slettet"
    users = _load_file_users()
    users.pop(username, None)
    _save_file_users(users)
    return True, "Bruker slettet"


def authenticate(username, password):
    user = get_user(username)
    if not user or not verify_password(password, user["salt"], user["password_hash"]):
        return False, None, "Feil brukernavn eller passord"
    if not user.get("active", True):
        return False, None, "Brukeren er deaktivert"
    safe_user = {
        "username": user["username"], "role": user.get("role", "user"),
        "active": bool(user.get("active", True)), "session_version": int(user.get("session_version", 1) or 1),
    }
    return True, safe_user, "Innlogget"


__all__ = [
    "DatabaseStarting", "authenticate", "create_user", "delete_user", "get_user",
    "hash_password", "init_user_store", "list_users", "update_user", "user_count", "verify_password",
]
