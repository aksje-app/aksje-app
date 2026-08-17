"""Renderer module extracted from app.py in v19.2.0.

Business calculations remain in the established services; this module owns only
the Streamlit presentation workflow and uses a compatibility context during the
transition away from the legacy monolith.
"""
from __future__ import annotations
from ui.legacy_context import bind_legacy_context

_PRESERVE = {'render_autonomy_core_control_center_v1880'}

def render_autonomy_core_control_center_v1880(_legacy_context) -> None:
    """Single, lazy workspace for all Autonomy operations."""
    bind_legacy_context(globals(), _legacy_context, preserve=_PRESERVE)
    from autonomi_core.runtime.orchestrator import runtime_manifest

    manifest = runtime_manifest()
    st.markdown("## 🧠 Autonomi")
    st.caption(
        "Autonomi er programmets styringslag. Markedsdata, analyse, rangering, "
        "porteføljebeslutninger, kontrollert læring og rapportering kobles sammen "
        "gjennom ett stabilt oppdragsgrensesnitt. Ingen ekte handler utføres."
    )
    a1, a2, a3, a4 = st.columns(4)
    a1.metric("Autonomy Core", manifest.get("version") or "-")
    a2.metric("Status", "Aktiv grunnmur")
    a3.metric("Kjøremodus", "Kun teoretisk")
    a4.metric("Domener", len(manifest.get("domains") or []))

    # RC13: all requested workspaces are applied before the radio is created;
    # never render a requested workspace through a separate early-return
    # path. The old path rendered the requested page once without establishing
    # the radio state; the next rerun then defaulted to Oversikt. All requests
    # now flow through one selector and one renderer below.
    from autonomy_modes import EXPERT, render_expert_console, render_mode_selector, render_simple_mode
    interface_mode = render_mode_selector()
    if interface_mode != EXPERT:
        render_simple_mode()
        return

    from navigation_state import (
        AUTONOMY_WORKSPACE_LABEL_BY_SLUG_V19220_RC7,
        AUTONOMY_WORKSPACE_ROUTE_LEASE_KEY_V19220_RC12,
        consume_autonomy_workspace_route_lease_v19220_rc12,
    )
    workspace_labels = dict(AUTONOMY_WORKSPACE_LABEL_BY_SLUG_V19220_RC7)
    if st.session_state.get(AUTONOMY_WORKSPACE_ROUTE_LEASE_KEY_V19220_RC12):
        try:
            from manual_job_background import get_active_status
            lease_status = get_active_status()
        except Exception:
            lease_status = {}
        consume_autonomy_workspace_route_lease_v19220_rc12(
            st.session_state, lease_status,
        )
    requested_workspace = str(st.session_state.get("autonomy_core_workspace_slug_v1882") or "").strip()
    if requested_workspace in workspace_labels:
        # Set the widget key before creation and keep it as the durable active
        # workspace. Clearing only the one-shot request must not clear selection.
        st.session_state["autonomy_core_workspace_v1880"] = workspace_labels[requested_workspace]
        st.session_state["autonomy_core_workspace_slug_v1882"] = ""

    def _open_quick_workspace(slug: str, report_surface: str = "") -> None:
        label = workspace_labels.get(slug)
        if not label:
            return
        st.session_state["autonomy_core_workspace_v1880"] = label
        st.session_state["autonomy_core_workspace_slug_v1882"] = ""
        if report_surface:
            st.session_state["mi_report_surface_v19220_rc1631t"] = report_surface

    st.markdown("#### Hurtigvalg")
    quick_reports, quick_progress, quick_portfolio = st.columns(3)
    quick_reports.button(
        "📚 Rapporter og historikk", type="primary", width="stretch",
        key="autonomy_quick_reports_history_v19220_rc1631t",
        on_click=_open_quick_workspace,
        args=("reports", "Rapporter, historikk og avansert"),
    )
    quick_progress.button(
        "▶️ Kjøring og status", width="stretch",
        key="autonomy_quick_report_progress_v19220_rc1631t",
        on_click=_open_quick_workspace,
        args=("reports", "Kjøring og fremdrift"),
    )
    quick_portfolio.button(
        "💼 Porteføljer", width="stretch",
        key="autonomy_quick_portfolio_v19220_rc1631t",
        on_click=_open_quick_workspace,
        args=("autonomous_portfolio", ""),
    )
    active_label = str(st.session_state.get("autonomy_core_workspace_v1880") or "Oversikt")
    st.caption(f"Aktiv arbeidsflate: {active_label}. Hurtigvalgene åpner de mest brukte områdene med ett trykk.")
    with st.expander("Alle arbeidsflater", expanded=False):
        workspace = st.radio(
            "Velg arbeidsflate",
            list(workspace_labels.values()),
            horizontal=True, key="autonomy_core_workspace_v1880",
        )
    workspace_slug = next(slug for slug, label in workspace_labels.items() if label == workspace)
    st.session_state["autonomy_core_workspace_active_slug_v19220_rc7"] = workspace_slug
    set_global_navigation_state(
        st, nav="autonomy", group="Autonomi", panel="🧠 Autonomi – Kontrollsenter", tab=workspace_slug,
    )
    if workspace == "Oversikt":
        from autonomy_overview import render_autonomy_overview
        render_autonomy_overview()
    elif workspace == "Orkestrering og tidsplan":
        render_autonomous_orchestrator_control_center()
    elif workspace == "Autonom portefølje":
        render_autonomous_portfolio(view="autonomous")
    elif workspace == "Læringsportefølje":
        render_autonomous_portfolio(view="learning")
    elif workspace == "Rapporter":
        from market_intelligence import render_market_intelligence
        render_market_intelligence()
    elif workspace == "Varsler og drift":
        render_alerts_watchlist_control_center_v1869()
        st.divider(); render_performance_dashboard()
    elif workspace == "Strategiversjoner":
        from pages.strategy_versions import render_strategy_versions
        render_strategy_versions(app_context)
    elif workspace == "Strategy Lab":
        from pages.strategy_lab import render_strategy_lab
        render_strategy_lab(app_context)
    elif workspace == "Motorresultater":
        from autonomy_overview import collect_autonomy_overview
        latest = collect_autonomy_overview().get("latest_run") or {}
        st.markdown("### News, Insider og Research")
        st.caption("Detaljvisning av motorbevis fra siste Autonomi-resultat; motorene kjøres av Autonomi.")
        rows = []
        for candidate in list(latest.get("candidates") or [])[:100]:
            raw = candidate.get("raw") if isinstance(candidate.get("raw"), dict) else {}
            rows.append({"Ticker": candidate.get("ticker"), "News": raw.get("news_score"), "Insider": raw.get("insider_score"), "Research": candidate.get("research_score"), "Datakvalitet": candidate.get("data_quality_score")})
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True) if rows else st.info("Ingen siste motorresultater.")
    else:
        render_expert_console()
