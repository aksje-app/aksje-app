"""Strategy registry, shared snapshots and parallel evaluation for v19.7.0.

The page can define bounded technical challenger parameters, but every shadow
or challenger remains read-only. Production promotion and shared execution are
not available in this roadmap phase.
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
        "v19.7.0 kjører produksjon, shadow og challenger parallelt på samme snapshot gjennom ett felles, skrivebeskyttet strategigrensesnitt."
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
    production_rows = {row.get("version_id"): row for row in productions}
    with st.expander("Opprett skrivebeskyttet challenger", expanded=False):
        if not production_options:
            st.warning("Ingen produksjonsstrategi er registrert.")
        else:
            with st.form("strategy_challenger_create_v1970"):
                source_label = st.selectbox("Kildestrategi", list(production_options))
                selected_source = production_rows.get(production_options[source_label], {})
                new_version = st.text_input("Ny strategiversjon", placeholder="f.eks. 1.1.0")
                parameter_version = st.text_input("Parameterprofil", placeholder="f.eks. technical-params-1.1")
                description = st.text_area("Formål og hypotese", placeholder="Hva skal challengeren teste?")
                technical_parameters = {}
                if selected_source.get("strategy_family") == "technical":
                    st.caption("Avgrensede testparametre. De påvirker bare denne shadow/challengeren.")
                    p1, p2 = st.columns(2)
                    technical_parameters = {
                        "buy_score_threshold": p1.number_input("Kjøpsterskel", 0.0, 10.0, 7.2, 0.1),
                        "sell_score_threshold": p2.number_input("Salg/unngå-terskel", 0.0, 10.0, 4.2, 0.1),
                        "maximum_buy_rsi": p1.number_input("Maks RSI ved kjøp", 0.0, 100.0, 70.0, 1.0),
                        "extreme_sell_rsi": p2.number_input("Ekstrem RSI / salg", 0.0, 100.0, 80.0, 1.0),
                        "block_high_risk": p1.checkbox("Blokker høy risiko", value=True),
                        "require_positive_confirmation": p2.checkbox("Krev MACD/breakout-bekreftelse", value=True),
                    }
                submitted = st.form_submit_button("Opprett shadow-versjon")
            if submitted:
                try:
                    metadata = {"technical_parameters": technical_parameters} if technical_parameters else {}
                    created = service.create_challenger(
                        production_options[source_label], new_version,
                        parameter_version=parameter_version,
                        description=description,
                        actor=actor,
                        metadata=metadata,
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


    with st.expander("Parallelle strategikjøringer", expanded=False):
        parallel = app_context.services.parallel_strategies
        runs = parallel.recent_runs(limit=30)
        decisions = parallel.recent_decisions(limit=500)
        r1, r2, r3 = st.columns(3)
        r1.metric("Kjøringer", len(runs))
        r2.metric("Beslutninger", len(decisions))
        r3.metric("Feilbeslutninger", sum(1 for row in decisions if row.get("action") == "ERROR"))
        st.caption(
            "Alle rader er observasjoner. Selv produksjonsstrategien har execution_authorized=false i denne sammenligningsmotoren; "
            "faktiske teoretiske handler utføres fortsatt bare av eksisterende Paper- og Autonomi-motor."
        )
        if runs:
            run_display = [{
                "Kjøring": row.get("run_id"),
                "Snapshot": row.get("market_snapshot_id"),
                "Kilde": row.get("source"),
                "Strategier": row.get("strategy_count"),
                "Kandidater": row.get("candidate_count"),
                "Beslutninger": row.get("decision_count"),
                "Feil": row.get("error_count"),
                "Fullført": row.get("completed_at"),
            } for row in runs]
            st.dataframe(pd.DataFrame(run_display), use_container_width=True, hide_index=True)
        if decisions:
            decision_display = [{
                "Ticker": row.get("ticker"),
                "Strategi": f"{row.get('strategy_id')}@{row.get('strategy_version')}",
                "Status": row.get("strategy_status"),
                "Handling": row.get("action"),
                "Score": row.get("score"),
                "Sikkerhet": row.get("confidence"),
                "Snapshot": row.get("market_snapshot_id"),
                "Utførelse": "Nei" if row.get("execution_authorized") is False else "FEIL",
                "Tid": row.get("evaluated_at"),
            } for row in decisions[:200]]
            st.dataframe(pd.DataFrame(decision_display), use_container_width=True, hide_index=True)
        else:
            st.caption("Ingen parallelle strategibeslutninger er lagret ennå.")

    with st.expander("Teknisk identitet og hendelser", expanded=False):
        st.caption("Disse feltene skal følge fremtidige beslutninger og handler.")
        for family in ("technical", "autonomy"):
            st.json(service.decision_binding(family), expanded=False)
        events = service.events.list(limit=100)
        if events:
            st.dataframe(pd.DataFrame(events), use_container_width=True, hide_index=True)
        else:
            st.caption("Ingen strategihendelser registrert.")
