
import streamlit as st
import pandas as pd
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
    except Exception:
        pass
    return {}


def _save_remember_tokens(tokens):
    try:
        with open(REMEMBER_FILE, "w", encoding="utf-8") as f:
            json.dump(tokens, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


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
    except Exception:
        pass
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
            except Exception:
                pass
    except Exception:
        pass


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
                    st.query_params["remember_token"] = token
                except Exception:
                    pass
            st.success("Innlogget")
            st.rerun()
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
            if tok and not st.query_params.get("remember_token"):
                st.query_params["remember_token"] = tok
        except Exception:
            pass
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
    st.sidebar.markdown("---")
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

    if st.sidebar.button("Logg ut", key="auth_logout_btn", use_container_width=True):
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
