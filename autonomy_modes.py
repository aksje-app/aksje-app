"""Simple and expert user experiences for Autonomy v18.8.4."""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

import pandas as pd
import streamlit as st

from adaptive_ranking import COMPONENT_FIELDS
from autonomi_core.configuration.policy import load_policy
from autonomi_core.missions.user_mission import load_user_mission, save_user_mission
from autonomi_core.runtime.orchestrator import runtime_manifest
from autonomous_orchestrator import load_audit as load_orchestrator_audit
from autonomous_portfolio import load_parameters, load_portfolio
from controlled_parameter_learning import load_audit as load_learning_audit, load_state
from manual_job_background import get_active_status, is_running, start_manual_job
from market_intelligence import BASE_MARKET_SCOPES, _load_report_archive, load_draft_job, load_jobs, load_run
from persistent_config_store import read_persistent_json, write_persistent_json
from scheduler_background import scheduler_audit, scheduler_status
from services.storage_service import get_storage_service


MODE_KEY = "autonomi_core/interface_mode.json"
SIMPLE = "Enkel modus"
EXPERT = "Ekspertmodus"
GOALS = ["Kapitalvekst", "Stabilitet", "Utbytte", "Finne nye kandidater"]
HORIZONS = ["1–3 måneder", "3–12 måneder", "1–3 år", "3 år eller mer"]
RISKS = ["Forsiktig", "Balansert", "Offensiv"]
SECTORS = [
    "Teknologi", "Finans", "Energi", "Industri", "Helse", "Forbruksvarer",
    "Kommunikasjon", "Eiendom", "Materialer", "Forsyning",
]


def load_interface_mode() -> str:
    value = read_persistent_json(MODE_KEY, default={})
    mode = str(value.get("mode") or SIMPLE) if isinstance(value, Mapping) else SIMPLE
    return mode if mode in {SIMPLE, EXPERT} else SIMPLE


def save_interface_mode(mode: str) -> str:
    clean = mode if mode in {SIMPLE, EXPERT} else SIMPLE
    write_persistent_json(MODE_KEY, {"mode": clean})
    return clean


def render_mode_selector() -> str:
    stored = load_interface_mode()
    mode = st.radio(
        "Brukernivå", [SIMPLE, EXPERT], index=0 if stored == SIMPLE else 1,
        horizontal=True, key="autonomy_interface_mode_v1884",
        help="Enkel modus skjuler tekniske parametere. Ekspertmodus gir innsyn i motorer og diagnose.",
    )
    if mode != stored:
        save_interface_mode(mode)
    return mode


def _index(options: list[str], value: Any, default: int = 0) -> int:
    try:
        return options.index(str(value))
    except ValueError:
        return default


def render_simple_mode() -> None:
    mission = load_user_mission()
    status = get_active_status()
    st.markdown("### Start Autonomi")
    st.caption(
        "Beskriv hva Autonomi skal lete etter. Markeder, bransjer og risikogrense "
        "håndheves før beslutningsdelen; mål og tidshorisont følger hele oppdraget som kontekst."
    )
    with st.form("autonomy_simple_mission_v1884"):
        c1, c2, c3 = st.columns(3)
        goal = c1.selectbox("Mål", GOALS, index=_index(GOALS, mission.get("goal"), 0))
        horizon = c2.selectbox("Tidshorisont", HORIZONS, index=_index(HORIZONS, mission.get("horizon"), 1))
        risk = c3.selectbox("Risiko", RISKS, index=_index(RISKS, mission.get("risk"), 1))
        markets = st.multiselect(
            "Markeder", list(BASE_MARKET_SCOPES),
            default=[item for item in mission.get("markets", []) if item in BASE_MARKET_SCOPES] or list(BASE_MARKET_SCOPES),
        )
        sectors = st.multiselect(
            "Eventuelle bransjer", SECTORS,
            default=[item for item in mission.get("sectors", []) if item in SECTORS],
            help="Tomt felt betyr alle bransjer. Bransjefilter brukes etter at kandidatene er analysert.",
        )
        submitted = st.form_submit_button(
            "▶ Start Autonomi", type="primary", use_container_width=True,
            disabled=is_running(status),
        )
    if submitted:
        try:
            saved = save_user_mission(goal=goal, horizon=horizon, risk=risk, markets=markets, sectors=sectors)
            draft = load_draft_job()
            job = replace(
                draft, name=f"Autonomi · {goal}", markets=list(markets),
                user_mission_id=str(saved["mission_id"]), enabled=False,
            )
            accepted = start_manual_job(job, trigger="MANUAL_SIMPLE_AUTONOMY", force_refresh=False)
            st.success(f"Oppdraget er startet: {accepted.get('execution_id')}")
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
    if is_running(status):
        st.info("Autonomi kjører allerede. Følg fremdrift og avbryt sikkert i oversikten under.")
    elif mission:
        sector_text = ", ".join(mission.get("sectors") or []) or "Alle bransjer"
        st.success(
            f"Sist lagrede oppdrag: {mission.get('goal')} · {mission.get('horizon')} · "
            f"{mission.get('risk')} risiko · {', '.join(mission.get('markets') or [])} · {sector_text}"
        )
    from autonomy_overview import render_autonomy_overview
    render_autonomy_overview(allow_quick_start=False)


def _latest_run() -> dict[str, Any]:
    archive = _load_report_archive()
    return load_run(str(archive[0].get("run_id") or "")) if archive else {}


def render_expert_console() -> None:
    """Read-only expert inventory; edits remain in established owner panels."""
    st.markdown("### 🧰 Ekspertkontroll")
    st.caption("Teknisk innsyn er samlet her. Endringer gjøres fortsatt i modulens eierpanel og følger eksisterende guardrails.")
    manifest = runtime_manifest()
    latest = _latest_run()
    policy = load_policy()
    params = load_parameters()
    learning = load_state()

    engines, thresholds, sources, strategies = st.tabs(["Motorer", "Terskler", "Datakilder", "Strategier"])
    with engines:
        st.dataframe(pd.DataFrame([
            {"Motor/domene": name, "Type": "Autonomy Core"} for name in manifest.get("domains", [])
        ] + [
            {"Motor/domene": name, "Type": "Kompatibilitetsmotor"} for name in manifest.get("compatibility", [])
        ]), use_container_width=True, hide_index=True)
    with thresholds:
        st.markdown("**Datapolicy**")
        st.json(policy.to_dict(), expanded=False)
        st.markdown("**Learning Portfolio**")
        st.json(vars(params), expanded=False)
    with sources:
        rows = []
        for candidate in list(latest.get("candidates") or [])[:100]:
            contract = candidate.get("data_contract") or {}
            rows.append({
                "Ticker": candidate.get("ticker"), "Kilde": contract.get("source"),
                "Hentet": contract.get("fetched_at"), "Live/cache": contract.get("delivery"),
                "Kvalitet": contract.get("quality_score"), "Gyldighet": contract.get("validity"),
            })
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.info("Ingen siste kjøring med datakildekontrakter.")
    with strategies:
        portfolio = load_portfolio()
        active = sorted({str(row.get("strategy")) for row in (portfolio.get("positions") or {}).values() if row.get("strategy")})
        st.write("Aktive porteføljestrategier:", ", ".join(active) or "Ingen")
        st.write("Pipeline-moduler:", ", ".join(latest.get("modules") or []) or "Ingen siste kjøring")

    factors, scheduler, shadow, logs = st.tabs(["Faktorvekter", "Scheduler", "Shadow Mode", "Logger og diagnose"])
    with factors:
        state = read_persistent_json("adaptive_ranking/model_state.json", default={})
        active_model = state.get("active_model") if isinstance(state, Mapping) else None
        active_model = dict(active_model) if isinstance(active_model, Mapping) else {}
        st.write("Aktiv modell:", active_model.get("model_version") or "Standard")
        st.dataframe(pd.DataFrame([
            {"Faktor": name, "Kandidatfelt": ", ".join(fields), "Aktiv vekt": (active_model or {}).get("weights", {}).get(name)}
            for name, fields in COMPONENT_FIELDS.items()
        ]), use_container_width=True, hide_index=True)
    with scheduler:
        jobs = load_jobs()
        st.json(scheduler_status(), expanded=False)
        st.dataframe(pd.DataFrame([{
            "Jobb": job.name, "Aktiv": job.enabled, "Tid": ", ".join(job.schedules),
            "Markeder": ", ".join(job.markets), "Tidssone": job.timezone_name,
        } for job in jobs]), use_container_width=True, hide_index=True)
    with shadow:
        proposals = read_persistent_json("adaptive_ranking/model_proposals.json", default=[])
        st.write("Produksjonsgodkjenning:", "Alltid eksplisitt")
        st.write("Automatisk modellgodkjenning:", "Av")
        st.write("Kontrollert læringsmodus:", learning.get("mode") or "OBSERVER")
        if proposals:
            st.dataframe(pd.DataFrame(list(proposals)[:100]), use_container_width=True, hide_index=True)
        else:
            st.info("Ingen Shadow Mode-forslag er lagret.")
    with logs:
        health = get_storage_service().health()
        l1, l2, l3 = st.columns(3)
        l1.metric("Lagring", health.backend)
        l2.metric("Orchestratorlogg", len(load_orchestrator_audit(500)))
        l3.metric("Læringslogg", len(load_learning_audit(500)))
        st.json({"scheduler": scheduler_status(), "storage": vars(health)}, expanded=False)
        audits = scheduler_audit(100)
        if audits:
            st.dataframe(pd.DataFrame(audits[::-1]), use_container_width=True, hide_index=True)
