
import streamlit as st
import pandas as pd
import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path

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
    tokens = _load_remember_tokens()
    expires = (datetime.now() + timedelta(days=REMEMBER_DAYS)).isoformat(timespec="seconds")
    tokens[token] = {"username": user.get("username"), "expires": expires}
    _save_remember_tokens(tokens)
    return token


def _restore_from_remember_token():
    try:
        token = st.query_params.get("remember_token", None)
        if isinstance(token, list):
            token = token[0] if token else None
        if not token:
            return None
        tokens = _load_remember_tokens()
        item = tokens.get(str(token))
        if not item:
            return None
        expires = datetime.fromisoformat(str(item.get("expires")))
        if expires < datetime.now():
            tokens.pop(str(token), None)
            _save_remember_tokens(tokens)
            return None
        username = item.get("username")
        for user in list_users():
            if user.get("username") == username and user.get("active", True):
                st.session_state["auth_user"] = user
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
    st.markdown(
        """
        <style>
        .login-shell { max-width: 520px; margin: 7vh auto 0 auto; }
        .login-card {
            background: linear-gradient(180deg, rgba(17,24,39,0.98), rgba(15,23,42,0.98));
            border: 1px solid rgba(148,163,184,0.38);
            border-radius: 20px;
            padding: 24px 24px 18px 24px;
            box-shadow: 0 18px 48px rgba(0,0,0,0.35);
        }
        .login-title { color:#f8fafc; font-size:1.65rem; font-weight:950; margin-bottom:2px; }
        .login-sub { color:#cbd5e1; font-weight:800; margin-bottom:18px; }
        .login-card input { min-height: 40px !important; }
        .login-card button { width: 100% !important; }
        @media (max-width: 700px) { .login-shell { max-width: 94vw; margin-top: 3vh; } .login-card { padding: 18px; } }
        </style>
        <div class="login-shell"><div class="login-card">
            <div class="login-title">🔐 Logg inn</div>
            <div class="login-sub">AI Aksje Analyzer Pro</div>
        """,
        unsafe_allow_html=True,
    )

    with st.form("login_form"):
        username = st.text_input("Brukernavn")
        password = st.text_input("Passord", type="password")
        remember_me = st.checkbox("Husk meg på denne enheten", value=True)
        submitted = st.form_submit_button("Logg inn")

    st.markdown("</div></div>", unsafe_allow_html=True)

    if submitted:
        ok, user, msg = authenticate(username, password)
        if ok:
            st.session_state["auth_user"] = user
            if remember_me:
                try:
                    st.query_params["remember_token"] = _create_remember_token(user)
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

    user = st.session_state.get("auth_user")
    if not user:
        user = _restore_from_remember_token()
    if not user:
        render_login()

    return user


def render_user_admin(current_user):
    st.sidebar.markdown("---")
    st.sidebar.subheader("👤 Bruker")
    st.sidebar.caption(f"Innlogget: {current_user.get('username')} ({current_user.get('role')})")

    if st.sidebar.button("Logg ut", key="auth_logout_btn"):
        _logout()

    if current_user.get("role") != "admin":
        return

    with st.sidebar.expander("🔐 Brukere", expanded=False):
        users = list_users()

        if users:
            df = pd.DataFrame(users)
            st.dataframe(
                df[["username", "role", "active"]],
                hide_index=True,
                use_container_width=True,
            )

        st.markdown("**Legg til bruker**")
        with st.form("add_user_form"):
            new_username = st.text_input("Nytt brukernavn")
            new_password = st.text_input("Passord", type="password")
            new_role = st.selectbox("Rolle", ["user", "admin"], index=0)
            add_submitted = st.form_submit_button("Legg til")

        if add_submitted:
            ok, msg = create_user(new_username, new_password, role=new_role, active=True)
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

        st.markdown("**Endre / fjern bruker**")
        usernames = [u["username"] for u in users]
        if usernames:
            selected = st.selectbox("Velg bruker", usernames, key="manage_user_select")
            selected_data = next((u for u in users if u["username"] == selected), None)

            col_a, col_b = st.columns(2)
            with col_a:
                new_active = st.checkbox(
                    "Aktiv",
                    value=bool(selected_data.get("active", True)),
                    key=f"user_active_{selected}",
                )
            with col_b:
                new_role = st.selectbox(
                    "Rolle",
                    ["user", "admin"],
                    index=1 if selected_data.get("role") == "admin" else 0,
                    key=f"user_role_{selected}",
                )

            new_pw = st.text_input("Nytt passord (valgfritt)", type="password", key=f"user_pw_{selected}")

            if st.button("Lagre bruker", key=f"save_user_{selected}"):
                ok, msg = update_user(selected, role=new_role, active=new_active, password=new_pw or None)
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

            if selected != current_user.get("username"):
                if st.button("Slett bruker", key=f"delete_user_{selected}"):
                    ok, msg = delete_user(selected)
                    if ok:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
            else:
                st.caption("Du kan ikke slette brukeren du er innlogget med.")
