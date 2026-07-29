from __future__ import annotations

import argparse
import getpass
import json
import logging
from pathlib import Path

from runtime_env import load_app_env
from user_store import get_user, init_user_store, update_user
from utils import using_postgres

try:
    import psycopg2
except Exception:
    psycopg2 = None


REMEMBER_FILE = Path("remember_tokens.json")


def _clear_local_remember_tokens(username: str) -> None:
    username = str(username or "").strip().lower()
    if not username or not REMEMBER_FILE.exists():
        return
    try:
        data = json.loads(REMEMBER_FILE.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    kept = {
        token: item
        for token, item in data.items()
        if str((item or {}).get("username") or "").strip().lower() != username
    }
    REMEMBER_FILE.write_text(json.dumps(kept, indent=2, ensure_ascii=False), encoding="utf-8")


def _clear_db_remember_tokens(username: str) -> bool:
    username = str(username or "").strip().lower()
    if not username or not using_postgres() or psycopg2 is None:
        return False
    try:
        from runtime_env import env_value

        database_url = env_value("DATABASE_URL", "")
        if not database_url:
            return False
        conn = psycopg2.connect(database_url)
        cur = conn.cursor()
        cur.execute("DELETE FROM app_remember_tokens WHERE username=%s", (username,))
        conn.commit()
        conn.close()
        return True
    except Exception as exc:
        logging.warning("Kunne ikke rydde DB remember-tokens: %s", exc)
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Lokalt nødskript for å sette nytt app-passord.")
    parser.add_argument("--user", default="admin", help="Brukernavn som skal resettes. Standard: admin")
    parser.add_argument("--password", default="", help="Nytt passord. Utelat for skjult prompt.")
    args = parser.parse_args()

    load_app_env()
    init_user_store()

    username = str(args.user or "admin").strip().lower()
    if not get_user(username):
        print(f"Fant ikke bruker: {username}")
        return 2

    password = str(args.password or "")
    if not password:
        password = getpass.getpass("Nytt passord: ")
        password2 = getpass.getpass("Gjenta nytt passord: ")
        if password != password2:
            print("Passordene er ikke like")
            return 3

    ok, msg = update_user(username, password=password)
    if ok:
        _clear_local_remember_tokens(username)
        db_cleared = _clear_db_remember_tokens(username)
        suffix = "lokalt og i database" if db_cleared else "lokalt"
        print(f"{msg}. Husk-meg tokens for {username} er ryddet {suffix}.")
        return 0
    print(msg)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
