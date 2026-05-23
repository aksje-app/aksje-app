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

    queue = [dict(row) for row in st.session_state.get(DECISION_QUEUE_KEY, []) if isinstance(row, Mapping)]

    c1, c2, c3 = st.columns(3)
    with c1:
        latest = _latest_radar_result_from_state()
        if st.button("Hent siste radarfunn", key="decision_support_import_latest_v1863ba", use_container_width=True, disabled=latest is None):
            rows = decision_source_rows_from_radar_result(latest or {})
            queue = add_decision_rows(queue, rows)
            st.session_state[DECISION_QUEUE_KEY] = queue
            st.success(f"Hentet {len(rows)} radarfunn til beslutningsgrunnlag.")
    with c2:
        if st.button("Vurder hele køen", key="decision_support_run_v1863ba", use_container_width=True, disabled=not queue):
            st.session_state[DECISION_CASES_KEY] = build_decision_cases(queue)
            st.success(f"Vurdert {len(queue)} kandidater.")
    with c3:
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
            st.session_state[DECISION_CASES_KEY] = build_decision_cases(selected_rows)
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
