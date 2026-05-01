
import streamlit as st
import pandas as pd

from user_store import (
    authenticate,
    create_user,
    delete_user,
    init_user_store,
    list_users,
    update_user,
    user_count,
)


def _logout():
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
    st.title("🔐 Logg inn")
    st.caption("AI Aksje Analyzer Pro")

    with st.form("login_form"):
        username = st.text_input("Brukernavn")
        password = st.text_input("Passord", type="password")
        submitted = st.form_submit_button("Logg inn")

    if submitted:
        ok, user, msg = authenticate(username, password)
        if ok:
            st.session_state["auth_user"] = user
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
