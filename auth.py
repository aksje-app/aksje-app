import logging

import streamlit as st
import pandas as pd
import hmac
import hashlib
import json
import os
import re
import uuid
from urllib.parse import quote
from datetime import datetime, timedelta
from pathlib import Path

try:
    import psycopg2
except Exception:
    psycopg2 = None

from user_store import (
    authenticate,
    create_user,
    delete_user,
    init_user_store,
    get_user,
    list_users,
    update_user,
    user_count,
    DatabaseStarting,
)


from auth_persistence import (
    atomic_write_json,
    auth_database_url,
    auth_environment_id,
    auth_json_path,
    auth_storage_status,
    auth_using_postgres,
    read_json,
)

REMEMBER_FILE = auth_json_path("remember_sessions.json")
REMEMBER_DAYS = 30
SESSION_HOURS = 24
AUTH_SESSION_RECHECK_SECONDS = max(15, min(300, int(os.getenv("AUTH_SESSION_RECHECK_SECONDS", "60") or 60)))
ADMIN_RESET_ENV_NAMES = ("ADMIN_RESET_KEY", "AKSE_ADMIN_RESET_KEY", "APP_ADMIN_RESET_KEY")


def _remember_cookie_name_v19144() -> str:
    namespace = auth_environment_id()
    digest = hashlib.sha256(namespace.encode("utf-8")).hexdigest()[:12]
    return f"ai_aksje_remember_{digest}"


def _remember_token_hash_v19144(token: str) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def _remember_storage_bridge(token=None, clear=False, *, bootstrap=False, reload_after_store=False):
    """Persist the remember token in a secure same-site browser cookie.

    Streamlit 1.57 exposes request cookies through ``st.context.cookies``. The
    small browser bridge sets/clears the cookie and migrates any legacy
    localStorage token without ever placing the token in the visible URL.
    """
    try:
        safe_token = json.dumps(str(token or ""))
        safe_cookie_name = json.dumps(_remember_cookie_name_v19144())
        clear_flag = "true" if clear else "false"
        bootstrap_flag = "true" if bootstrap else "false"
        reload_flag = "true" if reload_after_store else "false"
        bridge_html = f"""
            <script>
            (function() {{
              try {{
                var cookieName = {safe_cookie_name};
                var storageKey = cookieName + "_storage";
                var migrationKey = cookieName + "_migration_v19144";
                var clear = {clear_flag};
                var bootstrap = {bootstrap_flag};
                var reloadAfterStore = {reload_flag};
                var token = {safe_token};
                var parentUrl = new URL(window.parent.location.href);
                var parentStorage = null;
                try {{ parentStorage = window.parent.localStorage; }} catch (err) {{ parentStorage = null; }}
                function cookieSuffix(maxAge) {{
                  var secure = parentUrl.protocol === "https:" ? "; Secure" : "";
                  return "; Path=/; Max-Age=" + maxAge + "; SameSite=Lax" + secure;
                }}
                function setCookie(value) {{
                  window.parent.document.cookie = cookieName + "=" + encodeURIComponent(value) + cookieSuffix(2592000);
                }}
                function clearCookie() {{
                  window.parent.document.cookie = cookieName + "=; Path=/; Max-Age=0; SameSite=Lax" + (parentUrl.protocol === "https:" ? "; Secure" : "");
                }}
                function setStored(value) {{
                  try {{ window.localStorage.setItem(storageKey, value); }} catch (err) {{}}
                  try {{ if (parentStorage) parentStorage.setItem(storageKey, value); }} catch (err) {{}}
                }}
                function getStored() {{
                  try {{ if (parentStorage) {{
                    var parentValue = parentStorage.getItem(storageKey);
                    if (parentValue) return parentValue;
                  }} }} catch (err) {{}}
                  try {{ return window.localStorage.getItem(storageKey) || ""; }} catch (err) {{}}
                  return "";
                }}
                function clearStored() {{
                  try {{ window.localStorage.removeItem(storageKey); }} catch (err) {{}}
                  try {{ if (parentStorage) parentStorage.removeItem(storageKey); }} catch (err) {{}}
                  try {{ window.sessionStorage.removeItem(migrationKey); }} catch (err) {{}}
                }}
                function clearLegacyQuery() {{
                  var changed = parentUrl.searchParams.has("remember_token") || parentUrl.searchParams.has("remember_bootstrap");
                  parentUrl.searchParams.delete("remember_token");
                  parentUrl.searchParams.delete("remember_bootstrap");
                  if (changed) window.parent.history.replaceState(null, "", parentUrl.toString());
                }}
                if (clear) {{
                  clearStored();
                  clearCookie();
                  clearLegacyQuery();
                  return;
                }}
                if (token) {{
                  setStored(token);
                  setCookie(token);
                  clearLegacyQuery();
                  if (reloadAfterStore) {{
                    window.setTimeout(function() {{ window.parent.location.reload(); }}, 80);
                  }}
                  return;
                }}
                clearLegacyQuery();
                if (bootstrap) {{
                  var migrated = "";
                  try {{ migrated = window.sessionStorage.getItem(migrationKey) || ""; }} catch (err) {{}}
                  if (!migrated) {{
                    var stored = getStored();
                    try {{ window.sessionStorage.setItem(migrationKey, "1"); }} catch (err) {{}}
                    if (stored) {{
                      setCookie(stored);
                      window.setTimeout(function() {{ window.parent.location.reload(); }}, 80);
                    }}
                  }}
                }}
              }} catch (err) {{}}
            }})();
            </script>
            """
        st.iframe(
            "data:text/html;charset=utf-8," + quote(bridge_html),
            height=1,
            width=1,
        )
    except Exception as e:
        logging.warning("Remember cookie bridge failed: %s", e)


def _remember_cookie_token_v19143():
    try:
        context = getattr(st, "context", None)
        cookies = getattr(context, "cookies", None) if context is not None else None
        if cookies is not None:
            token = cookies.get(_remember_cookie_name_v19144())
            if token:
                return str(token)
    except Exception as exc:
        logging.debug("Remember cookie unavailable: %s", exc)
    return None



def _remember_db_available():
    return auth_using_postgres() and psycopg2 is not None


def _init_remember_db():
    if not _remember_db_available():
        return False
    try:
        conn = psycopg2.connect(auth_database_url(), connect_timeout=5)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS app_auth_sessions (
                token_hash TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                session_version INTEGER NOT NULL DEFAULT 1,
                expires TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                revoked BOOLEAN NOT NULL DEFAULT FALSE
            );
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_app_auth_sessions_username ON app_auth_sessions(username);")
        conn.commit()
        conn.close()
        return True
    except Exception as exc:
        logging.warning("Kunne ikke initialisere auth sessions: %s", exc)
        return False


def _db_get_remember_item(token):
    if not token or not _init_remember_db():
        return None
    try:
        conn = psycopg2.connect(auth_database_url(), connect_timeout=5)
        cur = conn.cursor()
        cur.execute(
            "SELECT username, session_version, expires, revoked FROM app_auth_sessions WHERE token_hash=%s",
            (_remember_token_hash_v19144(str(token)),),
        )
        row = cur.fetchone()
        conn.close()
        if not row or bool(row[3]):
            return None
        return {"username": row[0], "session_version": int(row[1] or 1), "expires": row[2]}
    except Exception:
        return None


def _db_upsert_remember_item(token, username, expires, session_version=1):
    if not token or not username or not _init_remember_db():
        return False
    try:
        now = datetime.now().isoformat(timespec="seconds")
        conn = psycopg2.connect(auth_database_url(), connect_timeout=5)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO app_auth_sessions
                (token_hash, username, session_version, expires, created_at, updated_at, revoked)
            VALUES (%s, %s, %s, %s, %s, %s, FALSE)
            ON CONFLICT (token_hash) DO UPDATE SET
                username=EXCLUDED.username,
                session_version=EXCLUDED.session_version,
                expires=EXCLUDED.expires,
                updated_at=EXCLUDED.updated_at,
                revoked=FALSE
        """, (
            _remember_token_hash_v19144(str(token)), str(username), int(session_version or 1),
            str(expires), now, now,
        ))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def _db_delete_remember_item(token):
    if not token or not _init_remember_db():
        return False
    try:
        conn = psycopg2.connect(auth_database_url(), connect_timeout=5)
        cur = conn.cursor()
        cur.execute("DELETE FROM app_auth_sessions WHERE token_hash=%s", (_remember_token_hash_v19144(str(token)),))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def _load_remember_tokens():
    data = read_json(REMEMBER_FILE, {})
    return data if isinstance(data, dict) else {}


def _save_remember_tokens(tokens):
    try:
        atomic_write_json(REMEMBER_FILE, tokens if isinstance(tokens, dict) else {})
    except Exception as exc:
        logging.warning("Kunne ikke lagre remember sessions: %s", exc)


def _env_value_v1868(name: str, default: str = "") -> str:
    try:
        from runtime_env import env_value

        return env_value(name, default)
    except Exception:
        return os.getenv(name, default).strip()


def _admin_reset_key_v1868() -> str:
    for name in ADMIN_RESET_ENV_NAMES:
        value = _env_value_v1868(name, "")
        if value:
            return value
    return ""


def _clear_remember_tokens_for_username_v1868(username: str) -> None:
    username = str(username or "").strip().lower()
    if not username:
        return
    try:
        tokens = _load_remember_tokens()
        kept = {
            token: item
            for token, item in tokens.items()
            if str((item or {}).get("username") or "").strip().lower() != username
        }
        if kept != tokens:
            _save_remember_tokens(kept)
    except Exception as e:
        logging.warning("Silenced exception restored in v18.6.8: %s", e)
    if _init_remember_db():
        try:
            conn = psycopg2.connect(auth_database_url(), connect_timeout=5)
            cur = conn.cursor()
            cur.execute("DELETE FROM app_auth_sessions WHERE username=%s", (username,))
            conn.commit()
            conn.close()
        except Exception as e:
            logging.warning("Silenced exception restored in v18.6.8: %s", e)


def reset_user_password_without_login(username: str, new_password: str, reset_key: str):
    """Reset a user password from login using a local env reset key."""
    expected = _admin_reset_key_v1868()
    if not expected:
        return False, "Mangler ADMIN_RESET_KEY i .env/secrets. Bruk lokalt nødskript eller legg inn reset-nøkkel."
    provided = str(reset_key or "").strip()
    if not provided or not hmac.compare_digest(provided, expected):
        return False, "Feil reset-nøkkel"
    ok, msg = update_user(username, password=new_password)
    if ok:
        _clear_remember_tokens_for_username_v1868(username)
        return True, "Passordet er oppdatert. Logg inn med nytt passord."
    return False, msg


def _create_remember_token(user):
    token = uuid.uuid4().hex + uuid.uuid4().hex
    expires = (datetime.now() + timedelta(days=REMEMBER_DAYS)).isoformat(timespec="seconds")
    username = user.get("username")
    session_version = int(user.get("session_version", 1) or 1)
    if not _db_upsert_remember_item(token, username, expires, session_version):
        tokens = _load_remember_tokens()
        tokens[_remember_token_hash_v19144(token)] = {
            "username": username, "session_version": session_version, "expires": expires
        }
        _save_remember_tokens(tokens)
    return token


def _set_logged_in(user, remember=False):
    """V14.7: tydelig session-varighet. Vanlig login varer 24 t, Husk meg varer 30 dager."""
    now = datetime.now()
    st.session_state["auth_user"] = user
    st.session_state["auth_logged_in_at"] = st.session_state.get("auth_logged_in_at") or now.isoformat(timespec="seconds")
    st.session_state["auth_last_activity_at"] = now.isoformat(timespec="seconds")
    st.session_state["auth_remember_me"] = bool(remember)
    expires_at = now + (timedelta(days=REMEMBER_DAYS) if remember else timedelta(hours=SESSION_HOURS))
    st.session_state["auth_expires_at"] = expires_at.isoformat(timespec="seconds")


def _clear_auth_session_v19144():
    for key in (
        "auth_user", "auth_expires_at", "auth_logged_in_at",
        "auth_last_activity_at", "auth_remember_me", "remember_token",
        "auth_user_version_checked_at_v19144", "auth_backend_warning_v19144",
    ):
        st.session_state.pop(key, None)


def _session_is_valid():
    """Validate the local session without logging users out on transient storage errors.

    Expiry is always enforced locally. The server-side user/session version is
    rechecked periodically, so password changes and deactivation invalidate the
    session, while a short database restart does not create a false logout loop.
    """
    user = st.session_state.get("auth_user")
    if not user:
        return False

    now = datetime.now()
    raw = st.session_state.get("auth_expires_at")
    if not raw:
        # Eldre session fra tidligere versjon: gi den standard levetid i stedet for å kaste bruker ut.
        st.session_state["auth_expires_at"] = (now + timedelta(hours=SESSION_HOURS)).isoformat(timespec="seconds")
    else:
        try:
            expires = datetime.fromisoformat(str(raw))
        except Exception as exc:
            logging.warning("Ugyldig lokal session-utløpstid: %s", exc)
            _clear_auth_session_v19144()
            return False
        if expires < now:
            _clear_auth_session_v19144()
            return False

    st.session_state["auth_last_activity_at"] = now.isoformat(timespec="seconds")
    if bool(st.session_state.get("auth_remember_me", False)):
        st.session_state["auth_expires_at"] = (now + timedelta(days=REMEMBER_DAYS)).isoformat(timespec="seconds")

    checked_raw = st.session_state.get("auth_user_version_checked_at_v19144")
    if checked_raw:
        try:
            checked_at = datetime.fromisoformat(str(checked_raw))
            if (now - checked_at).total_seconds() < AUTH_SESSION_RECHECK_SECONDS:
                return True
        except Exception:
            st.session_state.pop("auth_user_version_checked_at_v19144", None)

    try:
        stored = get_user(user.get("username"))
    except Exception as exc:
        # Fail stable for an already-authenticated, locally unexpired session.
        # A temporary database restart must not force a new login on every rerun.
        st.session_state["auth_user_version_checked_at_v19144"] = now.isoformat(timespec="seconds")
        st.session_state["auth_backend_warning_v19144"] = (
            "Brukerlageret svarte ikke midlertidig. Eksisterende innlogging beholdes og kontrolleres på nytt."
        )
        logging.warning("Midlertidig autentiseringslagerfeil; beholder gyldig lokal session: %s", exc)
        return True

    if (
        not stored
        or not stored.get("active", True)
        or int(stored.get("session_version", 1) or 1) != int(user.get("session_version", 1) or 1)
    ):
        _clear_auth_session_v19144()
        return False

    st.session_state["auth_user_version_checked_at_v19144"] = now.isoformat(timespec="seconds")
    st.session_state.pop("auth_backend_warning_v19144", None)
    return True


def _restore_from_remember_token():
    try:
        token = _remember_cookie_token_v19143()
        if not token:
            token = st.query_params.get("remember_token", None)
            if isinstance(token, list):
                token = token[0] if token else None
        if not token:
            return None
        item = _db_get_remember_item(str(token))
        tokens = None
        if not item:
            tokens = _load_remember_tokens()
            item = tokens.get(_remember_token_hash_v19144(str(token))) or tokens.get(str(token))
        if not item:
            return None
        expires = datetime.fromisoformat(str(item.get("expires")))
        if expires < datetime.now():
            _db_delete_remember_item(str(token))
            if tokens is None:
                tokens = _load_remember_tokens()
            tokens.pop(_remember_token_hash_v19144(str(token)), None)
            tokens.pop(str(token), None)
            _save_remember_tokens(tokens)
            return None
        username = str(item.get("username") or "").strip().lower()
        user = get_user(username)
        token_version = int(item.get("session_version", 1) or 1)
        current_version = int((user or {}).get("session_version", 1) or 1)
        if user and user.get("active", True) and token_version == current_version:
                # Forny tokenet ved bruk, slik at Husk meg faktisk holder lenge på PC og mobil.
                new_expires = (datetime.now() + timedelta(days=REMEMBER_DAYS)).isoformat(timespec="seconds")
                if not _db_upsert_remember_item(str(token), username, new_expires, current_version):
                    if tokens is None:
                        tokens = _load_remember_tokens()
                    tokens[_remember_token_hash_v19144(str(token))] = {
                        "username": username, "session_version": current_version, "expires": new_expires
                    }
                    _save_remember_tokens(tokens)
                safe_user = {
                    "username": user.get("username"), "role": user.get("role", "user"),
                    "active": bool(user.get("active", True)), "session_version": current_version,
                }
                st.session_state["remember_token"] = str(token)
                _set_logged_in(safe_user, remember=True)
                for query_key in ("remember_token", "remember_bootstrap"):
                    try:
                        if query_key in st.query_params:
                            del st.query_params[query_key]
                    except Exception:
                        pass
                _remember_storage_bridge(str(token))
                return safe_user
        # Tokenet peker til en deaktivert bruker eller en gammel passordversjon.
        _db_delete_remember_item(str(token))
        if tokens is None:
            tokens = _load_remember_tokens()
        tokens.pop(_remember_token_hash_v19144(str(token)), None)
        tokens.pop(str(token), None)
        _save_remember_tokens(tokens)
    except Exception:
        return None
    return None


def _clear_remember_token():
    try:
        token = st.session_state.get("remember_token") or _remember_cookie_token_v19143() or st.query_params.get("remember_token", None)
        if isinstance(token, list):
            token = token[0] if token else None
        if token:
            _db_delete_remember_item(str(token))
            tokens = _load_remember_tokens()
            tokens.pop(_remember_token_hash_v19144(str(token)), None)
            tokens.pop(str(token), None)
            _save_remember_tokens(tokens)
            for query_key in ("remember_token", "remember_bootstrap"):
                try:
                    if query_key in st.query_params:
                        del st.query_params[query_key]
                except Exception as e:
                    logging.warning("Kunne ikke rydde sensitiv query-parameter: %s", e)
        _remember_storage_bridge(clear=True)
    except Exception as e:
        logging.warning("Silenced exception restored in v18.6.3: %s", e)


def _logout():
    _clear_remember_token()
    st.session_state.pop("auth_user", None)
    st.session_state.pop("auth_expires_at", None)
    st.session_state.pop("auth_logged_in_at", None)
    st.session_state.pop("auth_last_activity_at", None)
    st.session_state.pop("auth_remember_me", None)
    st.session_state.pop("remember_token", None)
    st.rerun()


def render_first_admin_setup():
    st.title("🔐 Første gangs oppsett")
    st.info("Ingen brukere finnes ennå. Opprett første admin-bruker.")

    with st.form("first_admin_setup_form"):
        username = st.text_input("Admin brukernavn", value="admin")
        password = st.text_input("Admin passord", type="password")
        password2 = st.text_input("Gjenta passord", type="password")
        submitted = st.form_submit_button("Opprett admin")

    if submitted:
        if password != password2:
            st.error("Passordene er ikke like")
            st.stop()

        ok, msg = create_user(username, password, role="admin", active=True)
        if ok:
            authenticated, user, _ = authenticate(username, password)
            if authenticated and user:
                _set_logged_in(user, remember=True)
                token = _create_remember_token(user)
                st.session_state["remember_token"] = token
                st.session_state["auth_restore_attempted_v18621"] = True
                _remember_storage_bridge(token, reload_after_store=True)
                st.success("Admin opprettet og innlogget. Innloggingen lagres på denne enheten …")
                st.stop()
            st.success("Admin opprettet. Logg inn.")
            st.rerun()
        else:
            st.error(msg)

    st.stop()


def render_login():
    # Bootstrap is completed by require_login before the form is shown.
    _remember_storage_bridge(bootstrap=True)
    # V13 / Oppgave 33: hele login-formen skal være kort og sentrert, ikke bare headeren.
    st.markdown(
        """
        <style>
        .login-header {
            max-width: 520px;
            margin: 7vh auto 0.75rem auto;
            background: linear-gradient(180deg, rgba(17,24,39,0.98), rgba(15,23,42,0.98));
            border: 1px solid rgba(148,163,184,0.38);
            border-radius: 18px;
            padding: 22px 24px 18px 24px;
            box-shadow: 0 18px 48px rgba(0,0,0,0.35);
        }
        .login-title { color:#f8fafc; font-size:1.65rem; font-weight:950; margin-bottom:2px; }
        .login-sub { color:#cbd5e1; font-weight:800; margin-bottom:0; }
        div[data-testid="stForm"] {
            max-width: 520px !important;
            margin: 0 auto !important;
            border: 1px solid rgba(148,163,184,0.34) !important;
            border-radius: 16px !important;
            padding: 18px 18px 16px 18px !important;
            background: rgba(255,255,255,0.96) !important;
            box-shadow: 0 10px 32px rgba(15,23,42,0.08) !important;
        }
        div[data-testid="stForm"] input { min-height: 38px !important; }
        div[data-testid="stForm"] button { width: auto !important; min-width: 104px !important; }
        @media (max-width: 700px) {
            .login-header { max-width: 94vw; margin-top: 3vh; padding: 18px; }
            div[data-testid="stForm"] { max-width: 94vw !important; }
        }
        </style>
        <div class="login-header">
            <div class="login-title">🔐 Logg inn</div>
            <div class="login-sub">AI Aksje Analyzer Pro</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.form("login_form"):
        username = st.text_input("Brukernavn")
        password = st.text_input("Passord", type="password")
        remember_me = st.checkbox("Husk meg på denne enheten", value=True)
        submitted = st.form_submit_button("Logg inn")

    if submitted:
        ok, user, msg = authenticate(username, password)
        if ok:
            _set_logged_in(user, remember=bool(remember_me))
            if remember_me:
                try:
                    token = _create_remember_token(user)
                    st.session_state["remember_token"] = token
                    st.session_state["auth_restore_attempted_v18621"] = True
                    _remember_storage_bridge(token, reload_after_store=True)
                    st.success("Innlogget. Husk meg lagres på denne enheten …")
                    st.stop()
                except Exception as e:
                    logging.warning("Kunne ikke lagre Husk meg: %s", e)
            st.success("Innlogget")
            st.rerun()
        else:
            st.error(msg)

    with st.expander("Glemt passord?", expanded=False):
        st.caption("Brukes når du ikke kommer inn. Krever lokal ADMIN_RESET_KEY i .env/secrets.")
        if not _admin_reset_key_v1868():
            st.info("Ingen reset-nøkkel er satt. Legg ADMIN_RESET_KEY i .env, eller kjør reset_admin_password.py lokalt.")
        with st.form("forgot_password_form_v1868"):
            reset_username = st.text_input("Brukernavn", key="forgot_username_v1868")
            reset_key = st.text_input("Reset-nøkkel", type="password", key="forgot_key_v1868")
            new_password = st.text_input("Nytt passord", type="password", key="forgot_new_password_v1868")
            new_password2 = st.text_input("Gjenta nytt passord", type="password", key="forgot_new_password2_v1868")
            reset_submitted = st.form_submit_button("Sett nytt passord")
        if reset_submitted:
            if new_password != new_password2:
                st.error("Passordene er ikke like")
            else:
                ok, msg = reset_user_password_without_login(reset_username, new_password, reset_key)
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)

    st.stop()

def _render_auth_storage_blocker_v19144(status):
    st.error("Autentiseringslageret er ikke varig konfigurert. Programmet stopper før brukerdata kan gå tapt.")
    st.markdown(
        "**Raskeste løsning i Render:** bruk en separat testdatabase i `AUTH_DATABASE_URL`, "
        "eller monter en persistent disk og sett `AUTH_STORAGE_ROOT` til diskbanen."
    )
    st.code(
        "AUTH_STORAGE_MODE=postgres\nAUTH_DATABASE_URL=<separat testdatabase>\nAUTH_REQUIRE_PERSISTENT=true",
        language="text",
    )
    st.caption(str((status or {}).get("message") or ""))
    st.stop()


def require_login():
    storage_status = auth_storage_status()
    st.session_state["auth_storage_status_v19144"] = storage_status
    if not storage_status.get("ready"):
        _render_auth_storage_blocker_v19144(storage_status)
    try:
        init_user_store()
    except DatabaseStarting:
        st.warning("Databasen starter eller gjenopprettes. Programmet prøver automatisk igjen.")
        if st.button("Prøv databaseforbindelsen på nytt", width="stretch", key="database_starting_retry_v1910"):
            st.rerun()
        st.stop()

    if user_count() == 0:
        render_first_admin_setup()

    if _session_is_valid():
        # Oppbevar remember-token lokalt, men fjern det fra delbar URL.
        try:
            tok = st.session_state.get("remember_token")
            if tok:
                _remember_storage_bridge(tok)
        except Exception as e:
            logging.warning("Silenced exception restored in v18.6.3: %s", e)
        return st.session_state.get("auth_user")

    user = _restore_from_remember_token()
    if user:
        return user

    # The login renderer migrates any legacy localStorage token directly into a
    # cookie. It does not stop the first render, so users never need to submit
    # credentials twice when no remembered session exists.
    st.session_state["auth_restore_attempted_v18621"] = True
    render_login()
    return None


def render_user_admin(current_user):
    """Compact sidebar user/session administration.

    v18.5.34 keeps the sidebar short: only the logged-in user, logout and a
    closed admin expander are visible by default.  It intentionally avoids
    st.dataframe in the sidebar, because Streamlit's dataframe container can
    create large empty/white boxes in narrow sidebars.
    """
    username = str(current_user.get("username", "-"))
    role = str(current_user.get("role", "user"))
    remember_on = bool(st.session_state.get("auth_remember_me"))
    remember_cls = "on" if remember_on else "off"
    remember_txt = "På" if remember_on else "Av"
    auth_status = st.session_state.get("auth_storage_status_v19144") or auth_storage_status()
    auth_backend = "Varig" if auth_status.get("persistent") else "Flyktig"
    st.sidebar.markdown(
        f"""
        <div class="auth-sidebar-card auth-sidebar-card-v18639">
            <div class="auth-sidebar-title">👤 Bruker</div>
            <div class="auth-sidebar-user"><b>{username}</b><br/><span>Rolle: {role}</span></div>
            <div class="auth-remember-chip {remember_cls}">● Husk: <b>{remember_txt}</b></div>
            <div class="auth-remember-chip {'on' if auth_status.get('persistent') else 'off'}">● Brukerlager: <b>{auth_backend}</b></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.sidebar.button("Logg ut", key="auth_logout_btn", width="stretch"):
        st.session_state["auth_last_redirect_reason_v1865c"] = "manual_logout"
        _logout()

    # v18.6.49: Admin-panelet rendres ikke lenger i venstremenyen.
    # Bruk toppmenyen "⚙️ Admin" for å åpne System/admin i hovedvinduet.
    return
