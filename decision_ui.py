from __future__ import annotations

import html
from typing import Any, Mapping

import streamlit as st

from decision_engine import (
    DECISION_CASES_KEY,
    DECISION_QUEUE_KEY,
    add_decision_rows,
    build_decision_cases,
    decision_source_rows_from_radar_result,
    remove_decision_rows,
)


def _latest_radar_result_from_state() -> Mapping[str, Any] | None:
    latest: Mapping[str, Any] | None = None
    latest_key = ""
    for key, value in st.session_state.items():
        if not str(key).startswith("alpha_radar_last_result_"):
            continue
        if not isinstance(value, Mapping) or not value.get("candidates"):
            continue
        created = str(value.get("created_at") or "")
        marker = f"{created}|{key}"
        if marker >= latest_key:
            latest_key = marker
            latest = value
    return latest


def _decision_rows_from_pipeline() -> list[dict[str, Any]]:
    try:
        from datetime import datetime
        from services.analysis_pipeline_service import get_analysis_pipeline_service
        from services.state_service import get_state_service
        from services.storage_service import get_storage_service

        pipeline = get_analysis_pipeline_service(
            state_service=get_state_service(st.session_state),
            storage_service=get_storage_service(),
        )
        package = pipeline.load_stage_input("decision_support") or pipeline.load_stage_output("auto_test_lab")
        rows: list[dict[str, Any]] = []
        for item in package.get("candidates") or []:
            if not isinstance(item, Mapping):
                continue
            raw = item.get("raw") if isinstance(item.get("raw"), Mapping) else {}
            row = dict(raw or item)
            row["ticker"] = str(row.get("ticker") or item.get("ticker") or "").strip().upper()
            if not row["ticker"]:
                continue
            row["name"] = row.get("name") or item.get("name") or row["ticker"]
            row["decision_source"] = item.get("source") or package.get("source_label") or "Analyseflyt"
            row["source_stage"] = package.get("origin_stage_id") or package.get("stage_id") or "analysis_pipeline"
            row["source_result_created_at"] = package.get("generated_at")
            row["queued_at"] = datetime.now().isoformat(timespec="seconds")
            rows.append(row)
        return rows
    except Exception:
        return []


def _save_decision_cases_to_pipeline(cases: list[dict[str, Any]], *, mode: str, queue_size: int) -> None:
    try:
        from services.analysis_pipeline_service import get_analysis_pipeline_service
        from services.state_service import get_state_service
        from services.storage_service import get_storage_service

        get_analysis_pipeline_service(
            state_service=get_state_service(st.session_state),
            storage_service=get_storage_service(),
        ).save_stage_output(
            "decision_support",
            cases,
            source_label="Beslutningsgrunnlag",
            context={"queue": queue_size, "mode": mode},
            max_items=len(cases) or queue_size,
            auto_handoff=True,
        )
    except Exception:
        pass


def _render_decision_pipeline_bar_v1863bw() -> None:
    try:
        from services.analysis_pipeline_service import (
            PIPELINE_PENDING_NAV_KEY,
            get_analysis_pipeline_service,
            stage_wizard_info,
        )
        from services.state_service import get_state_service
        from services.storage_service import get_storage_service

        pipeline = get_analysis_pipeline_service(
            state_service=get_state_service(st.session_state),
            storage_service=get_storage_service(),
        )
        info = stage_wizard_info("decision_support")
        inp = pipeline.load_stage_input("decision_support")
        out = pipeline.load_stage_output("decision_support")
    except Exception as exc:
        st.caption(f"Analyseflyt-status kunne ikke vises: {exc}")
        return

    st.markdown(
        f"""
        <div style="border:1px solid rgba(56,189,248,.52);border-radius:8px;padding:.62rem .72rem;margin:.4rem 0;background:rgba(15,23,42,.72);">
          <div style="display:flex;justify-content:space-between;gap:.65rem;flex-wrap:wrap;align-items:center;">
            <b>{html.escape(str(info.get('wizard_label') or 'Test 8 av 10: Beslutningsgrunnlag'))}</b>
            <span>{int(inp.get('candidate_count') or 0)} inn | {int(out.get('candidate_count') or 0)} ut</span>
            <span>Auto-kjoring: av</span>
          </div>
          <div style="font-size:.82rem;color:rgba(226,232,240,.86);margin-top:.22rem;">Hent kandidatpakken, vurder koen, og send ferdig beslutningsgrunnlag videre til portefoljeanalysen.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    disabled = not bool(out)
    if st.button("Send output til Test 9 og åpne Porteføljeanalyse", key="decision_pipeline_next_v1863bw", use_container_width=True, disabled=disabled):
        result = pipeline.handoff_latest_output_to_next("decision_support")
        if not result.ok:
            st.warning(result.message)
            return
        target = stage_wizard_info("portfolio_analysis")
        st.session_state[PIPELINE_PENDING_NAV_KEY] = {
            "stage_id": "portfolio_analysis",
            "group": target.get("group") or "",
            "panel": target.get("panel_label") or "",
            "defaults": dict(target.get("defaults") or {}),
            "auto_run": False,
        }
        st.rerun()


def _case_card(case: Mapping[str, Any]) -> str:
    decision = str(case.get("decision") or "-")
    tone = {
        "Kjop naa": "#16a34a",
        "Vent": "#eab308",
        "Unnga": "#ef4444",
    }.get(decision, "#38bdf8")
    positives = "; ".join(str(x) for x in case.get("positive_reasons") or []) or "-"
    cautions = "; ".join(str(x) for x in case.get("cautions") or []) or "-"
    triggers = "; ".join(str(x) for x in case.get("buy_triggers") or []) or "-"
    return f"""
    <div style="border:1px solid rgba(148,163,184,.28);border-radius:8px;padding:.72rem .82rem;margin:.45rem 0;background:rgba(15,23,42,.72);">
      <div style="display:flex;justify-content:space-between;gap:.7rem;align-items:flex-start;">
        <div>
          <div style="font-weight:800;color:#f8fafc;">{html.escape(str(case.get('ticker') or '-'))} - {html.escape(str(case.get('name') or ''))}</div>
          <div style="font-size:.82rem;color:#94a3b8;">{html.escape(str(case.get('market') or '-'))} | {html.escape(str(case.get('source') or '-'))} | confidence {html.escape(str(case.get('confidence') or '-'))}</div>
        </div>
        <div style="color:{tone};font-weight:900;">{html.escape(decision)} {html.escape(str(case.get('decision_score') or '-'))}</div>
      </div>
      <div style="margin-top:.45rem;color:#dbeafe;font-size:.86rem;">{html.escape(str(case.get('why') or ''))}</div>
      <div style="margin-top:.45rem;color:#dcfce7;font-size:.84rem;"><b>Pluss:</b> {html.escape(positives)}</div>
      <div style="margin-top:.25rem;color:#fde68a;font-size:.84rem;"><b>Sjekk:</b> {html.escape(cautions)}</div>
      <div style="margin-top:.25rem;color:#bae6fd;font-size:.84rem;"><b>Trigger:</b> {html.escape(triggers)}</div>
      <div style="margin-top:.25rem;color:#cbd5e1;font-size:.84rem;"><b>Posisjon:</b> {html.escape(str(case.get('position_hint') or ''))}</div>
    </div>
    """


def render_decision_support_panel() -> None:
    st.subheader("Beslutningsgrunnlag")
    st.caption("Tar funn fra Alpha Radar/Early Warning videre til manuell kjop/vent/unnga-vurdering. Ingen automatisk handel.")
    _render_decision_pipeline_bar_v1863bw()

    queue = [dict(row) for row in st.session_state.get(DECISION_QUEUE_KEY, []) if isinstance(row, Mapping)]

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        latest = _latest_radar_result_from_state()
        if st.button("Hent siste radarfunn", key="decision_support_import_latest_v1863ba", use_container_width=True, disabled=latest is None):
            rows = decision_source_rows_from_radar_result(latest or {})
            queue = add_decision_rows(queue, rows)
            st.session_state[DECISION_QUEUE_KEY] = queue
            st.success(f"Hentet {len(rows)} radarfunn til beslutningsgrunnlag.")
    with c2:
        pipeline_rows = _decision_rows_from_pipeline()
        if st.button("Hent fra analyseflyt", key="decision_support_import_pipeline_v1863bv", use_container_width=True, disabled=not pipeline_rows):
            queue = add_decision_rows(queue, pipeline_rows)
            st.session_state[DECISION_QUEUE_KEY] = queue
            st.success(f"Hentet {len(pipeline_rows)} kandidater fra analyseflyt.")
    with c3:
        if st.button("Vurder hele køen", key="decision_support_run_v1863ba", use_container_width=True, disabled=not queue):
            cases = build_decision_cases(queue)
            st.session_state[DECISION_CASES_KEY] = cases
            _save_decision_cases_to_pipeline(cases, mode="hele_koen", queue_size=len(queue))
            st.success(f"Vurdert {len(queue)} kandidater.")
    with c4:
        if st.button("Tøm kø", key="decision_support_clear_v1863ba", use_container_width=True, disabled=not queue):
            queue = []
            st.session_state[DECISION_QUEUE_KEY] = []
            st.session_state[DECISION_CASES_KEY] = []
            st.success("Beslutningskøen er tom.")

    if not queue:
        st.info("Ingen radarfunn i beslutningskøen ennaa. Kjor radar og send funn hit, eller hent siste radarfunn.")
        return

    labels = [f"{row.get('ticker')} | {row.get('decision_source') or row.get('source') or row.get('mode')}" for row in queue]
    selected_labels = st.multiselect(
        "Kandidater",
        labels,
        default=labels[: min(8, len(labels))],
        key="decision_support_selected_v1863ba",
    )
    selected_tickers = [label.split("|", 1)[0].strip().upper() for label in selected_labels]
    selected_rows = [row for row in queue if str(row.get("ticker") or "").strip().upper() in selected_tickers]

    a1, a2 = st.columns(2)
    with a1:
        if st.button("Vurder valgte", key="decision_support_run_selected_v1863ba", use_container_width=True, disabled=not selected_rows):
            cases = build_decision_cases(selected_rows)
            st.session_state[DECISION_CASES_KEY] = cases
            _save_decision_cases_to_pipeline(cases, mode="valgte", queue_size=len(queue))
            st.success(f"Vurdert {len(selected_rows)} valgte kandidater.")
    with a2:
        if st.button("Fjern valgte", key="decision_support_remove_selected_v1863ba", use_container_width=True, disabled=not selected_rows):
            queue = remove_decision_rows(queue, selected_tickers)
            st.session_state[DECISION_QUEUE_KEY] = queue
            st.session_state[DECISION_CASES_KEY] = build_decision_cases(queue) if queue else []
            st.success(f"Fjernet {len(selected_tickers)} kandidater.")

    cases = st.session_state.get(DECISION_CASES_KEY)
    if not cases:
        cases = build_decision_cases(selected_rows or queue)
        st.session_state[DECISION_CASES_KEY] = cases

    summary = {
        "Kjop naa": sum(1 for case in cases if case.get("decision") == "Kjop naa"),
        "Vent": sum(1 for case in cases if case.get("decision") == "Vent"),
        "Unnga": sum(1 for case in cases if case.get("decision") == "Unnga"),
    }
    st.caption(f"Kø: {len(queue)} | Kjop naa: {summary['Kjop naa']} | Vent: {summary['Vent']} | Unnga: {summary['Unnga']}")

    for case in cases:
        st.markdown(_case_card(case), unsafe_allow_html=True)


__all__ = ["render_decision_support_panel"]
