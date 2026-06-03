import logging

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import hmac
import json
import os
import uuid
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
    list_users,
    update_user,
    user_count,
)


REMEMBER_FILE = Path("remember_tokens.json")
REMEMBER_DAYS = 30
SESSION_HOURS = 24
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
ADMIN_RESET_ENV_NAMES = ("ADMIN_RESET_KEY", "AKSE_ADMIN_RESET_KEY", "APP_ADMIN_RESET_KEY")


def _remember_storage_bridge(token=None, clear=False):
    """Best-effort browser storage for mobile refreshes that drop query params."""
    try:
        safe_token = json.dumps(str(token or ""))
        clear_flag = "true" if clear else "false"
        components.html(
            f"""
            <script>
            (function() {{
              try {{
                var key = "ai_aksje_remember_token";
                var clear = {clear_flag};
                var token = {safe_token};
                var parentUrl = new URL(window.parent.location.href);
                var parentStorage = null;
                try {{ parentStorage = window.parent.localStorage; }} catch (err) {{ parentStorage = null; }}
                function setStored(value) {{
                  try {{ window.localStorage.setItem(key, value); }} catch (err) {{}}
                  try {{ if (parentStorage) parentStorage.setItem(key, value); }} catch (err) {{}}
                }}
                function getStored() {{
                  try {{ if (parentStorage) {{
                    var parentValue = parentStorage.getItem(key);
                    if (parentValue) return parentValue;
                  }} }} catch (err) {{}}
                  try {{ return window.localStorage.getItem(key); }} catch (err) {{}}
                  return "";
                }}
                function clearStored() {{
                  try {{ window.localStorage.removeItem(key); }} catch (err) {{}}
                  try {{ if (parentStorage) parentStorage.removeItem(key); }} catch (err) {{}}
                }}
                if (clear) {{
                  clearStored();
                  parentUrl.searchParams.delete("remember_token");
                  window.parent.history.replaceState(null, "", parentUrl.toString());
                  return;
                }}
                if (token) {{
                  setStored(token);
                  parentUrl.searchParams.delete("remember_token");
                  window.parent.history.replaceState(null, "", parentUrl.toString());
                  return;
                }}
                if (!parentUrl.searchParams.get("remember_token")) {{
                  var stored = getStored();
                  if (stored) {{
                    parentUrl.searchParams.set("remember_token", stored);
                    window.parent.location.replace(parentUrl.toString());
                  }}
                }}
              }} catch (err) {{}}
            }})();
            </script>
            """,
            height=0,
        )
    except Exception as e:
        logging.warning("Remember storage bridge failed: %s", e)




def _remember_db_available():
    return bool(DATABASE_URL) and psycopg2 is not None


def _init_remember_db():
    if not _remember_db_available():
        return False
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS app_remember_tokens (
                token TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                expires TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def _db_get_remember_item(token):
    if not token or not _init_remember_db():
        return None
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("SELECT username, expires FROM app_remember_tokens WHERE token=%s", (str(token),))
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        return {"username": row[0], "expires": row[1]}
    except Exception:
        return None


def _db_upsert_remember_item(token, username, expires):
    if not token or not username or not _init_remember_db():
        return False
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO app_remember_tokens (token, username, expires, updated_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (token) DO UPDATE SET
                username=EXCLUDED.username,
                expires=EXCLUDED.expires,
                updated_at=EXCLUDED.updated_at
        """, (str(token), str(username), str(expires), datetime.now().isoformat(timespec="seconds")))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def _db_delete_remember_item(token):
    if not token or not _init_remember_db():
        return False
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("DELETE FROM app_remember_tokens WHERE token=%s", (str(token),))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def _load_remember_tokens():
    try:
        if REMEMBER_FILE.exists():
            with open(REMEMBER_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
    except Exception as e:
        logging.warning("Silenced exception restored in v18.6.3: %s", e)
    return {}


def _save_remember_tokens(tokens):
    try:
        with open(REMEMBER_FILE, "w", encoding="utf-8") as f:
            json.dump(tokens, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logging.warning("Silenced exception restored in v18.6.3: %s", e)


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
            conn = psycopg2.connect(DATABASE_URL)
            cur = conn.cursor()
            cur.execute("DELETE FROM app_remember_tokens WHERE username=%s", (username,))
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
    if not _db_upsert_remember_item(token, username, expires):
        tokens = _load_remember_tokens()
        tokens[token] = {"username": username, "expires": expires}
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


def _session_is_valid():
    user = st.session_state.get("auth_user")
    if not user:
        return False
    raw = st.session_state.get("auth_expires_at")
    if not raw:
        # Eldre session fra tidligere versjon: gi den standard levetid i stedet for å kaste bruker ut.
        st.session_state["auth_expires_at"] = (datetime.now() + timedelta(hours=SESSION_HOURS)).isoformat(timespec="seconds")
        return True
    try:
        expires = datetime.fromisoformat(str(raw))
        now = datetime.now()
        if expires >= now:
            st.session_state["auth_last_activity_at"] = now.isoformat(timespec="seconds")
            # Husk meg skal oppleves stabilt på mobil: forny session-vindu ved aktiv bruk.
            if bool(st.session_state.get("auth_remember_me", False)):
                st.session_state["auth_expires_at"] = (now + timedelta(days=REMEMBER_DAYS)).isoformat(timespec="seconds")
            return True
    except Exception as e:
        logging.warning("Silenced exception restored in v18.6.3: %s", e)
    st.session_state.pop("auth_user", None)
    st.session_state.pop("auth_expires_at", None)
    st.session_state.pop("auth_logged_in_at", None)
    st.session_state.pop("auth_last_activity_at", None)
    st.session_state.pop("auth_remember_me", None)
    st.session_state.pop("remember_token", None)
    return False


def _restore_from_remember_token():
    try:
        token = st.query_params.get("remember_token", None)
        if isinstance(token, list):
            token = token[0] if token else None
        if not token:
            return None
        item = _db_get_remember_item(str(token))
        tokens = None
        if not item:
            tokens = _load_remember_tokens()
            item = tokens.get(str(token))
        if not item:
            return None
        expires = datetime.fromisoformat(str(item.get("expires")))
        if expires < datetime.now():
            _db_delete_remember_item(str(token))
            if tokens is None:
                tokens = _load_remember_tokens()
            tokens.pop(str(token), None)
            _save_remember_tokens(tokens)
            return None
        username = item.get("username")
        for user in list_users():
            if user.get("username") == username and user.get("active", True):
                # Forny tokenet ved bruk, slik at Husk meg faktisk holder lenge på PC og mobil.
                new_expires = (datetime.now() + timedelta(days=REMEMBER_DAYS)).isoformat(timespec="seconds")
                if not _db_upsert_remember_item(str(token), username, new_expires):
                    if tokens is None:
                        tokens = _load_remember_tokens()
                    tokens[str(token)] = {"username": username, "expires": new_expires}
                    _save_remember_tokens(tokens)
                st.session_state["remember_token"] = str(token)
                _set_logged_in(user, remember=True)
                try:
                    del st.query_params["remember_token"]
                except Exception:
                    pass
                return user
    except Exception:
        return None
    return None


def _clear_remember_token():
    try:
        token = st.query_params.get("remember_token", None)
        if isinstance(token, list):
            token = token[0] if token else None
        if token:
            _db_delete_remember_item(str(token))
            tokens = _load_remember_tokens()
            tokens.pop(str(token), None)
            _save_remember_tokens(tokens)
            try:
                del st.query_params["remember_token"]
            except Exception as e:
                logging.warning("Silenced exception restored in v18.6.3: %s", e)
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
            st.success("Admin opprettet. Logg inn.")
            st.rerun()
        else:
            st.error(msg)

    st.stop()


def render_login():
    _remember_storage_bridge()
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
                    _remember_storage_bridge(token)
                except Exception as e:
                    logging.warning("Silenced exception restored in v18.6.3: %s", e)
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

def require_login():
    init_user_store()

    if user_count() == 0:
        render_first_admin_setup()

    if _session_is_valid():
        # Hold remember-token synlig i URL når mulig, så refresh/mobil-nettleser ikke mister login.
        try:
            tok = st.session_state.get("remember_token")
            if tok:
                _remember_storage_bridge(tok)
        except Exception as e:
            logging.warning("Silenced exception restored in v18.6.3: %s", e)
        return st.session_state.get("auth_user")

    user = _restore_from_remember_token()
    if not user:
        render_login()

    return user


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
    st.sidebar.markdown(
        f"""
        <div class="auth-sidebar-card">
            <div class="auth-sidebar-title">👤 Bruker</div>
            <div class="auth-sidebar-user"><b>{username}</b> <span>{role}</span></div>
            <div class="auth-remember-chip {remember_cls}">● Husk meg: <b>{remember_txt}</b></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.sidebar.button("Logg ut", key="auth_logout_btn", use_container_width=False):
        st.session_state["auth_last_redirect_reason_v1865c"] = "manual_logout"
        _logout()

    if current_user.get("role") != "admin":
        return

    with st.sidebar.expander("🔐 Admin", expanded=False):  # tidligere: Administrer brukere
        users = list_users()
        if users:
            rows = []
            for u in users:
                active_cls = "on" if bool(u.get("active", True)) else "off"
                rows.append(
                    f"<div class='auth-user-row'>"
                    f"<span><b>{u.get('username','-')}</b> · {u.get('role','user')}</span>"
                    f"<span class='auth-dot {active_cls}'></span>"
                    f"</div>"
                )
            st.markdown("<div class='auth-user-list'>" + "".join(rows) + "</div>", unsafe_allow_html=True)

        st.markdown("<div class='auth-mini-heading'>Legg til</div>", unsafe_allow_html=True)
        with st.form("add_user_form"):
            new_username = st.text_input("Brukernavn", label_visibility="visible")
            new_password = st.text_input("Passord", type="password", label_visibility="visible")
            new_role = st.selectbox("Rolle", ["user", "admin"], index=0)
            add_submitted = st.form_submit_button("Legg til", use_container_width=True)

        if add_submitted:
            ok, msg = create_user(new_username, new_password, role=new_role, active=True)
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

        st.markdown("<div class='auth-mini-heading'>Endre</div>", unsafe_allow_html=True)
        usernames = [u["username"] for u in users]
        if usernames:
            selected = st.selectbox("Velg", usernames, key="manage_user_select")
            selected_data = next((u for u in users if u["username"] == selected), {})

            new_active = st.checkbox(
                "Aktiv",
                value=bool(selected_data.get("active", True)),
                key=f"user_active_{selected}",
            )
            new_role = st.selectbox(
                "Rolle",
                ["user", "admin"],
                index=1 if selected_data.get("role") == "admin" else 0,
                key=f"user_role_{selected}",
            )
            new_pw = st.text_input("Nytt passord", type="password", key=f"user_pw_{selected}")

            if st.button("Lagre", key=f"save_user_{selected}", use_container_width=True):
                ok, msg = update_user(selected, role=new_role, active=new_active, password=new_pw or None)
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

            if selected != current_user.get("username"):
                if st.button("Slett", key=f"delete_user_{selected}", use_container_width=True):
                    ok, msg = delete_user(selected)
                    if ok:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
            else:
                st.caption("Kan ikke slette innlogget bruker.")
