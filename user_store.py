
import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime
from pathlib import Path

try:
    import psycopg2
except Exception:
    psycopg2 = None


DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
USERS_FILE = Path("app_users.json")
PBKDF2_ITERATIONS = 220_000


def using_postgres():
    return bool(DATABASE_URL) and psycopg2 is not None


def _conn():
    return psycopg2.connect(DATABASE_URL)


def hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_bytes(16)
    if isinstance(salt, str):
        salt = base64.b64decode(salt.encode("utf-8"))

    key = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    return {
        "salt": base64.b64encode(salt).decode("utf-8"),
        "hash": base64.b64encode(key).decode("utf-8"),
    }


def verify_password(password, salt, password_hash):
    candidate = hash_password(password, salt)["hash"]
    return hmac.compare_digest(candidate, password_hash)


def init_user_store():
    if using_postgres():
        conn = _conn()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS app_users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)
        conn.commit()
        conn.close()
        return True

    if not USERS_FILE.exists():
        USERS_FILE.write_text(json.dumps({}), encoding="utf-8")
    return False


def _load_file_users():
    init_user_store()
    try:
        return json.loads(USERS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_file_users(users):
    USERS_FILE.write_text(json.dumps(users, indent=2, ensure_ascii=False), encoding="utf-8")


def list_users():
    init_user_store()

    if using_postgres():
        conn = _conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT username, role, active, created_at, updated_at
            FROM app_users
            ORDER BY username
        """)
        rows = cur.fetchall()
        conn.close()
        return [
            {
                "username": r[0],
                "role": r[1],
                "active": bool(r[2]),
                "created_at": r[3],
                "updated_at": r[4],
            }
            for r in rows
        ]

    users = _load_file_users()
    return [
        {
            "username": u,
            "role": data.get("role", "user"),
            "active": bool(data.get("active", True)),
            "created_at": data.get("created_at", ""),
            "updated_at": data.get("updated_at", ""),
        }
        for u, data in sorted(users.items())
    ]


def user_count():
    return len(list_users())


def get_user(username):
    init_user_store()
    username = str(username or "").strip().lower()
    if not username:
        return None

    if using_postgres():
        conn = _conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT username, password_hash, salt, role, active, created_at, updated_at
            FROM app_users
            WHERE username=%s
        """, (username,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        return {
            "username": row[0],
            "password_hash": row[1],
            "salt": row[2],
            "role": row[3],
            "active": bool(row[4]),
            "created_at": row[5],
            "updated_at": row[6],
        }

    users = _load_file_users()
    data = users.get(username)
    if not data:
        return None
    return {"username": username, **data}


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
    now = datetime.utcnow().isoformat()

    if using_postgres():
        conn = _conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO app_users
            (username, password_hash, salt, role, active, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (username, hp["hash"], hp["salt"], role, bool(active), now, now))
        conn.commit()
        conn.close()
        return True, "Bruker opprettet"

    users = _load_file_users()
    users[username] = {
        "password_hash": hp["hash"],
        "salt": hp["salt"],
        "role": role,
        "active": bool(active),
        "created_at": now,
        "updated_at": now,
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
    now = datetime.utcnow().isoformat()

    if password:
        if len(password) < 8:
            return False, "Passord må være minst 8 tegn"
        hp = hash_password(password)
        password_hash = hp["hash"]
        salt = hp["salt"]
    else:
        password_hash = user["password_hash"]
        salt = user["salt"]

    if using_postgres():
        conn = _conn()
        cur = conn.cursor()
        cur.execute("""
            UPDATE app_users
            SET password_hash=%s, salt=%s, role=%s, active=%s, updated_at=%s
            WHERE username=%s
        """, (password_hash, salt, new_role, new_active, now, username))
        conn.commit()
        conn.close()
        return True, "Bruker oppdatert"

    users = _load_file_users()
    users[username].update({
        "password_hash": password_hash,
        "salt": salt,
        "role": new_role,
        "active": new_active,
        "updated_at": now,
    })
    _save_file_users(users)
    return True, "Bruker oppdatert"


def delete_user(username):
    init_user_store()
    username = str(username or "").strip().lower()
    if not get_user(username):
        return False, "Bruker finnes ikke"

    # Prevent deleting last admin
    users = list_users()
    active_admins = [u for u in users if u["role"] == "admin" and u["active"] and u["username"] != username]
    target = get_user(username)
    if target and target.get("role") == "admin" and not active_admins:
        return False, "Kan ikke slette siste aktive admin"

    if using_postgres():
        conn = _conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM app_users WHERE username=%s", (username,))
        conn.commit()
        conn.close()
        return True, "Bruker slettet"

    users = _load_file_users()
    users.pop(username, None)
    _save_file_users(users)
    return True, "Bruker slettet"


def authenticate(username, password):
    user = get_user(username)
    if not user:
        return False, None, "Feil brukernavn eller passord"
    if not user.get("active", True):
        return False, None, "Brukeren er deaktivert"

    ok = verify_password(password, user["salt"], user["password_hash"])
    if not ok:
        return False, None, "Feil brukernavn eller passord"

    safe_user = {
        "username": user["username"],
        "role": user.get("role", "user"),
        "active": user.get("active", True),
    }
    return True, safe_user, "Innlogget"
