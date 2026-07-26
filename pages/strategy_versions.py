"""Strategy registry and shared snapshot workspace for v19.6.0.

The page manages identity and lifecycle metadata only. It cannot promote a
challenger to production or change strategy parameters, trading rules or risk
limits.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from domain.strategy_versioning import StrategyStatus
from services.strategy_registry_service import StrategyRegistryError


def _actor_from_context(app_context: Any) -> str:
    user = getattr(app_context, "user", None)
    if isinstance(user, dict):
        return str(user.get("username") or user.get("email") or user.get("name") or "user")
    return str(getattr(user, "username", None) or getattr(user, "email", None) or user or "user")


def _display_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    status_labels = {
        "PRODUCTION": "Produksjon",
        "SHADOW": "Shadow",
        "CHALLENGER": "Challenger",
        "PAUSED": "Pauset",
        "RETIRED": "Avviklet",
    }
    mode_labels = {
        "PAPER": "Teoretiske handler",
        "SHADOW_READ_ONLY": "Skrivebeskyttet",
        "DISABLED": "Deaktivert",
    }
    return [
        {
            "Strategi": row.get("display_name") or row.get("strategy_id"),
            "Familie": row.get("strategy_family"),
            "Versjon": row.get("strategy_version"),
            "Parametre": row.get("parameter_version"),
            "Status": status_labels.get(str(row.get("status")), row.get("status")),
            "Kjøremodus": mode_labels.get(str(row.get("execution_mode")), row.get("execution_mode")),
            "Implementasjon": row.get("implementation_version"),
            "Forelder": row.get("parent_version_id") or "–",
            "Oppdatert": row.get("updated_at") or row.get("created_at"),
        }
        for row in rows
    ]


def render_strategy_versions(app_context: Any) -> None:
    st = app_context["st"]
    service = app_context.services.strategy_registry
    actor = _actor_from_context(app_context)
    service.ensure_defaults()
    rows = service.list_versions()

    st.markdown("### 🧬 Strategiversjoner")
    st.caption(
        "Registeret gjør teknisk benchmark og Autonomi sporbare som versjonerte strategier. "
        "v19.6.0 legger til felles markedssnapshot og teknisk signaltjeneste uten å endre terskler, handler eller risikoregler."
    )

    productions = [row for row in rows if row.get("status") == StrategyStatus.PRODUCTION.value]
    shadows = [row for row in rows if row.get("status") in {StrategyStatus.SHADOW.value, StrategyStatus.CHALLENGER.value}]
    paused = [row for row in rows if row.get("status") == StrategyStatus.PAUSED.value]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Registrerte versjoner", len(rows))
    c2.metric("Produksjonsbindinger", len(productions))
    c3.metric("Shadow/challenger", len(shadows))
    c4.metric("Pauset", len(paused))

    st.dataframe(pd.DataFrame(_display_rows(rows)), use_container_width=True, hide_index=True)
    st.info(
        "Produksjonsbindingen er låst. En ny versjon kan opprettes og kjøres i "
        "shadow, men kan ikke automatisk overta handler eller endre Autonomis beslutninger."
    )

    production_options = {
        f"{row.get('display_name')} · {row.get('strategy_version')}": row.get("version_id")
        for row in productions
    }
    with st.expander("Opprett skrivebeskyttet challenger", expanded=False):
        if not production_options:
            st.warning("Ingen produksjonsstrategi er registrert.")
        else:
            with st.form("strategy_challenger_create_v1950"):
                source_label = st.selectbox("Kildestrategi", list(production_options))
                new_version = st.text_input("Ny strategiversjon", placeholder="f.eks. 1.1.0")
                parameter_version = st.text_input("Parameterprofil", placeholder="f.eks. technical-params-1.1")
                description = st.text_area("Formål og hypotese", placeholder="Hva skal challengeren teste?")
                submitted = st.form_submit_button("Opprett shadow-versjon")
            if submitted:
                try:
                    created = service.create_challenger(
                        production_options[source_label], new_version,
                        parameter_version=parameter_version,
                        description=description,
                        actor=actor,
                    )
                    st.success(f"Opprettet {created['version_id']} som skrivebeskyttet shadow.")
                    st.rerun()
                except (StrategyRegistryError, ValueError) as exc:
                    st.error(str(exc))

    manageable = [row for row in rows if row.get("status") != StrategyStatus.PRODUCTION.value]
    with st.expander("Endre livssyklus for testversjon", expanded=False):
        if not manageable:
            st.caption("Ingen shadow- eller challenger-versjoner er opprettet ennå.")
        else:
            labels = {
                f"{row.get('display_name')} · {row.get('strategy_version')} · {row.get('status')}": row
                for row in manageable
            }
            selected_label = st.selectbox("Strategiversjon", list(labels), key="strategy_lifecycle_select_v1950")
            selected = labels[selected_label]
            allowed = {
                "SHADOW": ["CHALLENGER", "PAUSED", "RETIRED"],
                "CHALLENGER": ["SHADOW", "PAUSED", "RETIRED"],
                "PAUSED": ["SHADOW", "CHALLENGER", "RETIRED"],
                "RETIRED": [],
            }.get(str(selected.get("status")), [])
            if not allowed:
                st.caption("Avviklede versjoner er skrivebeskyttet historikk.")
            else:
                target = st.selectbox("Ny status", allowed, key="strategy_lifecycle_target_v1950")
                reason = st.text_input("Begrunnelse", key="strategy_lifecycle_reason_v1950")
                if st.button("Lagre status", key="strategy_lifecycle_save_v1950"):
                    try:
                        service.set_status(selected["version_id"], target, actor=actor, reason=reason)
                        st.success("Strategistatus oppdatert.")
                        st.rerun()
                    except StrategyRegistryError as exc:
                        st.error(str(exc))


    with st.expander("Felles markedssnapshot og teknisk motor", expanded=False):
        contract = dict(getattr(app_context, "version_contract", {}) or {})
        s1, s2, s3 = st.columns(3)
        s1.metric("Snapshot-kontrakt", contract.get("market_snapshot_version", "1.0"))
        s2.metric("TechnicalSignalService", contract.get("technical_signal_service_version", "1.0"))
        snapshot_rows = app_context.services.repositories.market_snapshots.list()[:50]
        s3.metric("Lagrede snapshots", len(snapshot_rows))
        st.caption(
            "Paper-scanner og Autonomi kan nå knytte beslutninger til et kontrollsummert snapshot. "
            "Snapshotet inneholder normaliserte beslutningsdata, ikke DataFrame- eller cacheobjekter."
        )
        if snapshot_rows:
            display = []
            for row in snapshot_rows[:20]:
                display.append({
                    "Snapshot-ID": row.get("snapshot_id"),
                    "Kilde": row.get("source"),
                    "Kjøring": row.get("run_id"),
                    "Kandidater": len(row.get("candidates") or []),
                    "Tidspunkt": row.get("captured_at"),
                    "Kontrollsum": str(row.get("checksum") or "")[:16],
                })
            st.dataframe(pd.DataFrame(display), use_container_width=True, hide_index=True)
        else:
            st.caption("Ingen snapshot er lagret ennå. De opprettes ved nye scanner- og autonomikjøringer.")

    with st.expander("Teknisk identitet og hendelser", expanded=False):
        st.caption("Disse feltene skal følge fremtidige beslutninger og handler.")
        for family in ("technical", "autonomy"):
            st.json(service.decision_binding(family), expanded=False)
        events = service.events.list(limit=100)
        if events:
            st.dataframe(pd.DataFrame(events), use_container_width=True, hide_index=True)
        else:
            st.caption("Ingen strategihendelser registrert.")
