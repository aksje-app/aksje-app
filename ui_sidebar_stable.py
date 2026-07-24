"""Stable sidebar renderer for AI Aksje Analyzer Pro.

v18.6.42 goal:
- One source of truth for sidebar structure.
- Avoid fragmented inline sidebar HTML in app.py.
- Keep desktop readable and prevent mobile drawer from blocking the app.
"""
from __future__ import annotations

from urllib.parse import urlencode




def _sidebar_set_query_state_v18674c(st, nav: str, group: str = "", panel: str = "") -> None:
    """Set refresh-safe URL state while preserving remember_token."""
    try:
        st.query_params["aa_nav"] = str(nav or "")
        if group:
            st.query_params["aa_group"] = str(group)
        elif "aa_group" in st.query_params:
            del st.query_params["aa_group"]
        if panel:
            st.query_params["aa_panel"] = str(panel)
        elif "aa_panel" in st.query_params:
            del st.query_params["aa_panel"]
        for k in ("aa_tab", "aa_subtab"):
            if k in st.query_params:
                del st.query_params[k]
    except Exception:
        pass

def _sidebar_persist_nav_v18658(st, nav: str) -> None:
    """Persist desktop sidebar navigation without forcing URL redirects.

    v18.6.61: Do NOT write panel/mobile_nav query params from desktop buttons.
    Query params kept re-applying the old page on every rerun and could make
    Dashboard/Analyse/Top Picks/AI/System appear dead. File persistence is
    enough for refresh/new login; button clicks update session_state directly.
    """
    try:
        import json
        from pathlib import Path
        path = Path("data/ui_state_v18658.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"nav": str(nav or ""), "version": "v18.6.61"}, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass



def _sidebar_nav_href_v18659(st, nav: str) -> str:
    """Real href fallback for desktop nav.

    v18.6.59: Streamlit buttons can be blocked by persistent query state on
    some sessions. These links make every sidebar item navigate by URL first,
    using the same panel parameter that the app already applies on startup.
    """
    params = {}
    try:
        for k, v in dict(st.query_params).items():
            if isinstance(v, (list, tuple)):
                params[k] = str(v[0]) if v else ""
            else:
                params[k] = str(v)
    except Exception:
        params = {}
    params.pop("mobile_nav", None)
    params["panel"] = str(nav or "")
    return "?" + urlencode(params)


def _sidebar_nav_links_v18659(st) -> None:
    legacy_items = [
        ("🏠", "Dashboard", "dashboard"),
        ("📈", "Analyse", "analysis"),
        ("🎯", "Top Picks", "top_picks"),
        ("🚀", "Long Engine", "long_engine"),
        ("🤖", "AI", "ai"),
        ("🧾", "Paper Trading", "paper_trading"),
        ("🧠", "Autonomi", "autonomy"),
        ("💱", "Valutavarsler", "fx_alerts"),
        ("⚙️", "System", "system"),
    ]
    try:
        from autonomi_core.configuration.application_centered import application_centered_enabled, application_navigation
        items = list(application_navigation()) if application_centered_enabled() else legacy_items
    except Exception:
        items = legacy_items
    current = ""
    try:
        current = str(st.query_params.get("panel", "") or "").lower()
    except Exception:
        current = ""
    html = ["<div class='sidebar2026-nav-links-v18659'>"]
    for icon, label, nav in items:
        active = " active" if current == nav else ""
        href = _sidebar_nav_href_v18659(st, nav)
        html.append(
            f"<a class='sidebar2026-nav-link-v18659{active}' href='{href}' target='_self' "
            f"title='{label}'><span class='nav-ico'>{icon}</span><span class='nav-label'>{label}</span></a>"
        )
    html.append("</div>")
    st.sidebar.markdown("".join(html), unsafe_allow_html=True)

def _clear_control_center_nav_state_v18663(st) -> None:
    """Clear stale control-center selection keys before a fresh sidebar click.

    v18.6.63: previous versions left Long Engine radio/session keys alive.
    Then every menu click reacted, but the control center snapped back to Long.
    """
    clear_exact = [
        "ai_control_center_group_v1863m",
        "ai_control_center_active_panel_v1863m",
        "ai_control_center_active_real_panel_v18598",
        "ai_control_center_group_v1863aj",
        "ai_control_center_active_panel_v1863aj",
        "ai_control_center_group_radio_v1863aj",
        "analysis_pipeline_active_stage_v1863bz",
    ]
    for key in clear_exact:
        try:
            st.session_state.pop(key, None)
        except Exception:
            pass
    try:
        for key in list(st.session_state.keys()):
            if str(key).startswith("ai_control_center_panel_radio_v1863aj_"):
                st.session_state.pop(key, None)
    except Exception:
        pass
    try:
        if "panel" in st.query_params:
            del st.query_params["panel"]
        if "mobile_nav" in st.query_params:
            del st.query_params["mobile_nav"]
        for k in ("aa_nav", "aa_group", "aa_panel", "aa_tab", "aa_subtab"):
            if k in st.query_params:
                del st.query_params[k]
    except Exception:
        pass


def _sidebar_nav_set_v18650(st, nav: str) -> None:
    """Single real navigation path for desktop sidebar buttons.

    v18.6.63: menu click is the source of truth. Stale Long Engine state is
    cleared first so saved UI-state cannot override Dashboard/Analyse/Top Picks.
    """
    nav = str(nav or "").strip().lower()
    _clear_control_center_nav_state_v18663(st)
    st.session_state["ai_control_center_force_nav_v18663"] = nav
    if nav == "dashboard":
        st.session_state["ai_control_center_menu_open_v1863ag"] = True
    elif nav == "analysis":
        st.session_state["ai_control_center_group_v1863m"] = "AI Kandidattest"
        st.session_state["ai_control_center_group_v1863aj"] = "AI Kandidattest"
        st.session_state["ai_control_center_active_panel_v1863m"] = "AI Kandidattest"
        st.session_state["ai_control_center_active_panel_v1863aj"] = "AI Kandidattest"
        st.session_state["ai_control_center_active_real_panel_v18598"] = "AI Kandidattest"
        st.session_state["ai_control_center_menu_open_v1863ag"] = False
    elif nav == "top_picks":
        st.session_state["ai_control_center_group_v1863m"] = "Marked og signaler"
        st.session_state["ai_control_center_group_v1863aj"] = "Marked og signaler"
        st.session_state["ai_control_center_active_panel_v1863m"] = "Top Picks"
        st.session_state["ai_control_center_active_panel_v1863aj"] = "Top Picks"
        st.session_state["ai_control_center_active_real_panel_v18598"] = "Top Picks"
        st.session_state["ai_control_center_menu_open_v1863ag"] = False
    elif nav in {"portfolio", "reports"}:
        nav = nav
        workspace = "Læringsportefølje" if nav == "portfolio" else "Rapporter"
        slug = "learning_portfolio" if nav == "portfolio" else "reports"
        st.session_state["ai_control_center_group_v1863m"] = "Autonomi"
        st.session_state["ai_control_center_group_v1863aj"] = "Autonomi"
        st.session_state["ai_control_center_active_panel_v1863m"] = "🧠 Autonomi – Kontrollsenter"
        st.session_state["ai_control_center_active_panel_v1863aj"] = "🧠 Autonomi – Kontrollsenter"
        st.session_state["ai_control_center_active_real_panel_v18598"] = "🧠 Autonomi – Kontrollsenter"
        st.session_state["autonomy_core_workspace_slug_v1882"] = slug
        st.session_state["ai_control_center_menu_open_v1863ag"] = False
    elif nav == "long_engine":
        st.session_state["ai_control_center_group_v1863m"] = "Long Engine"
        st.session_state["ai_control_center_group_v1863aj"] = "Long Engine"
        st.session_state["ai_control_center_active_panel_v1863m"] = "Long Engine"
        st.session_state["ai_control_center_active_panel_v1863aj"] = "Long Engine"
        st.session_state["ai_control_center_active_real_panel_v18598"] = "Long Engine"
        st.session_state["ai_control_center_group_radio_v1863aj"] = "Long Engine (1)"
        st.session_state["ai_control_center_panel_radio_v1863aj_Long Engine"] = "Long Engine"
        st.session_state["ai_control_center_menu_open_v1863ag"] = False
    elif nav == "ai":
        st.session_state["ai_control_center_group_v1863m"] = "Analyse og prognose"
        st.session_state["ai_control_center_group_v1863aj"] = "Analyse og prognose"
        st.session_state["ai_control_center_menu_open_v1863ag"] = True
    elif nav in {"paper", "paper_trading", "papertrading"}:
        nav = "paper_trading"
        st.session_state["ai_control_center_group_v1863m"] = "Testing og portefolje"
        st.session_state["ai_control_center_group_v1863aj"] = "Testing og portefolje"
        st.session_state["ai_control_center_active_panel_v1863m"] = "Paper Trading og kontroll"
        st.session_state["ai_control_center_active_panel_v1863aj"] = "Paper Trading og kontroll"
        st.session_state["ai_control_center_active_real_panel_v18598"] = "Paper Trading og kontroll"
        st.session_state["ai_control_center_menu_open_v1863ag"] = False
    elif nav in {"autonomy", "autonomous", "autonomi"}:
        nav = "autonomy"
        st.session_state["ai_control_center_group_v1863m"] = "Autonomi"
        st.session_state["ai_control_center_group_v1863aj"] = "Autonomi"
        st.session_state["ai_control_center_active_panel_v1863m"] = "🧠 Autonomi – Kontrollsenter"
        st.session_state["ai_control_center_active_panel_v1863aj"] = "🧠 Autonomi – Kontrollsenter"
        st.session_state["ai_control_center_active_real_panel_v18598"] = "🧠 Autonomi – Kontrollsenter"
        st.session_state["ai_control_center_group_radio_v1863aj"] = "Autonomi (1)"
        st.session_state["ai_control_center_panel_radio_v1863aj_Autonomi"] = "🧠 Autonomi – Kontrollsenter"
        st.session_state["ai_control_center_menu_open_v1863ag"] = False
    elif nav in {"fx_alerts", "currency_alerts", "valutavarsler"}:
        nav = "fx_alerts"
        st.session_state["ai_control_center_group_v1863m"] = "Andre paneler"
        st.session_state["ai_control_center_group_v1863aj"] = "Andre paneler"
        st.session_state["ai_control_center_active_panel_v1863m"] = "💱 Valutavarsler"
        st.session_state["ai_control_center_active_panel_v1863aj"] = "💱 Valutavarsler"
        st.session_state["ai_control_center_active_real_panel_v18598"] = "💱 Valutavarsler"
        st.session_state["ai_control_center_menu_open_v1863ag"] = False
    elif nav == "system":
        st.session_state["ai_control_center_group_v1863m"] = "System"
        st.session_state["ai_control_center_group_v1863aj"] = "System"
        st.session_state["ai_control_center_active_panel_v1863m"] = "System/admin"
        st.session_state["ai_control_center_active_panel_v1863aj"] = "System/admin"
        st.session_state["ai_control_center_active_real_panel_v18598"] = "System/admin"
        st.session_state["ai_control_center_menu_open_v1863ag"] = False
    sidebar_group_panel_v18674c = {
        "dashboard": ("", ""),
        "analysis": ("AI Kandidattest", "AI Kandidattest"),
        "top_picks": ("Marked og signaler", "Top Picks"),
        "long_engine": ("Long Engine", "Long Engine"),
        "ai": ("Analyse og prognose", ""),
        "paper_trading": ("Testing og portefolje", "Paper Trading og kontroll"),
        "autonomy": ("Autonomi", "🧠 Autonomi – Kontrollsenter"),
        "fx_alerts": ("Andre paneler", "💱 Valutavarsler"),
        "portfolio": ("Autonomi", "🧠 Autonomi – Kontrollsenter"),
        "reports": ("Autonomi", "🧠 Autonomi – Kontrollsenter"),
        "system": ("System", "System/admin"),
    }
    q_group, q_panel = sidebar_group_panel_v18674c.get(nav, ("", ""))
    _sidebar_set_query_state_v18674c(st, nav, q_group, q_panel)
    _sidebar_persist_nav_v18658(st, nav)
    try:
        st.rerun()
    except Exception:
        pass

def _sidebar_nav_button_v18650(st, label: str, nav: str, key: str) -> None:
    if st.sidebar.button(label, key=key, use_container_width=True):
        _sidebar_nav_set_v18650(st, nav)


def render_stable_sidebar_v18641(st, current_user, render_user_admin):
    """Render real clickable sidebar navigation and return drift visibility.

    v18.6.50 rebuild: the old HTML nav cards looked clickable, but were dead.
    This version uses real Streamlit buttons for desktop navigation.
    """
    st.sidebar.markdown(_SIDEBAR_CSS_V18641, unsafe_allow_html=True)

    st.sidebar.markdown("<div class='sidebar-section-title'>Navigasjon</div>", unsafe_allow_html=True)
    # v18.6.60: back to real Streamlit buttons.
    # v18.6.59 URL links fixed dead clicks, but could force a fresh auth/login
    # and also made long labels overflow. Buttons keep the user inside the same
    # authenticated Streamlit session while still persisting panel state.
    try:
        from autonomi_core.configuration.application_centered import application_centered_enabled, application_navigation
        centered = application_centered_enabled()
    except Exception:
        centered = False
    if centered:
        for _icon, _label, _nav in application_navigation():
            _sidebar_nav_button_v18650(st, f"{_icon} {_label}", _nav, f"sidebar_nav_v1900_{_nav}")
    else:
        _sidebar_nav_button_v18650(st, "🏠 Dashboard", "dashboard", "sidebar_nav_dashboard_v18660")
        _sidebar_nav_button_v18650(st, "📈 Analyse", "analysis", "sidebar_nav_analysis_v18660")
        _sidebar_nav_button_v18650(st, "🎯 Top Picks", "top_picks", "sidebar_nav_top_picks_v18660")
        _sidebar_nav_button_v18650(st, "🚀 Long", "long_engine", "sidebar_nav_long_engine_v18660")
        _sidebar_nav_button_v18650(st, "🤖 AI", "ai", "sidebar_nav_ai_v18660")
        _sidebar_nav_button_v18650(st, "🧾 Paper Trading", "paper_trading", "sidebar_nav_paper_v1907")
        _sidebar_nav_button_v18650(st, "🧠 Autonomi", "autonomy", "sidebar_nav_autonomy_v1882")
        _sidebar_nav_button_v18650(st, "💱 Valutavarsler", "fx_alerts", "sidebar_nav_fx_alerts_v1891")
        _sidebar_nav_button_v18650(st, "⚙️ System", "system", "sidebar_nav_system_v18660")

    st.sidebar.markdown("<div class='sidebar-section-title sidebar-section-title-account'>Konto</div>", unsafe_allow_html=True)
    render_user_admin(current_user)

    # Admin/Drift skal ikke renderes i venstremeny. De styres fra toppmenyen.
    return bool(st.session_state.get("show_drift_controls_v18647", False))

_SIDEBAR_CSS_V18641 = """
<style>
/* v18.6.46 stable sidebar: desktop full menu, mobile bottom rail. */
html body section[data-testid="stSidebar"] {
  width: 224px !important;
  min-width: 224px !important;
  max-width: 224px !important;
  overflow-x: hidden !important;
  overflow-y: auto !important;
  border-right: 1px solid rgba(56,189,248,.20) !important;
}
html body section[data-testid="stSidebar"] > div:first-child {
  padding: .70rem .70rem !important;
}
html body section[data-testid="stSidebar"] .sidebar-section-title {
  display: block !important;
  font-size: .69rem !important;
  line-height: 1.05 !important;
  letter-spacing: .12em !important;
  text-align: left !important;
  margin: .62rem .18rem .38rem .18rem !important;
  color: #bfdbfe !important;
  text-transform: uppercase !important;
  font-weight: 950 !important;
  white-space: nowrap !important;
}
html body section[data-testid="stSidebar"] .sidebar-section-title:first-of-type { margin-top: .15rem !important; }
html body section[data-testid="stSidebar"] .sidebar2026-nav {
  display: flex !important;
  flex-direction: column !important;
  gap: .38rem !important;
  margin-bottom: .72rem !important;
}
html body section[data-testid="stSidebar"] .sidebar2026-nav-item {
  display: grid !important;
  grid-template-columns: 32px minmax(0, 1fr) !important;
  align-items: center !important;
  gap: .46rem !important;
  min-height: 40px !important;
  padding: .34rem .48rem !important;
  border-radius: 15px !important;
  background: linear-gradient(180deg, rgba(14,56,90,.92), rgba(8,30,55,.92)) !important;
  border: 1px solid rgba(96,165,250,.32) !important;
  box-shadow: inset 0 0 0 1px rgba(255,255,255,.04), 0 8px 18px rgba(0,0,0,.18) !important;
}
html body section[data-testid="stSidebar"] .sidebar2026-nav-item b {
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  width: 30px !important;
  height: 30px !important;
  border-radius: 10px !important;
  background: rgba(14,116,144,.45) !important;
  font-size: 1.05rem !important;
}
html body section[data-testid="stSidebar"] .sidebar2026-nav-item span {
  display: block !important;
  min-width: 0 !important;
  color: #f8fafc !important;
  font-size: .88rem !important;
  font-weight: 900 !important;
  line-height: 1.05 !important;
  white-space: nowrap !important;
  overflow: visible !important;
  text-overflow: clip !important;
}
html body section[data-testid="stSidebar"] .auth-sidebar-card {
  padding: .56rem .56rem !important;
  margin: 0 0 .48rem 0 !important;
  border-radius: 16px !important;
  background: rgba(15,23,42,.64) !important;
  border: 1px solid rgba(148,163,184,.24) !important;
}
html body section[data-testid="stSidebar"] .auth-sidebar-title { font-size: .76rem !important; margin-bottom: .20rem !important; }
html body section[data-testid="stSidebar"] .auth-sidebar-user { font-size: .88rem !important; line-height: 1.18 !important; text-align: left !important; }
html body section[data-testid="stSidebar"] .auth-sidebar-user span { font-size: .70rem !important; color: #93c5fd !important; }
html body section[data-testid="stSidebar"] .auth-remember-chip {
  display: inline-flex !important;
  width: auto !important;
  max-width: 100% !important;
  margin-top: .36rem !important;
  padding: .20rem .40rem !important;
  border-radius: 999px !important;
  font-size: .66rem !important;
  white-space: nowrap !important;
}
html body section[data-testid="stSidebar"] div[data-testid="stButton"] > button {
  min-height: 40px !important;
  width: 100% !important;
  justify-content: flex-start !important;
  padding: .34rem .46rem !important;
  border-radius: 15px !important;
  font-size: .80rem !important;
  font-weight: 900 !important;
  line-height: 1.05 !important;
  color: #f8fafc !important;
  white-space: nowrap !important;
  overflow: hidden !important;
  text-overflow: ellipsis !important;
  background: linear-gradient(180deg, rgba(14,56,90,.92), rgba(8,30,55,.92)) !important;
  border: 1px solid rgba(96,165,250,.32) !important;
  box-shadow: inset 0 0 0 1px rgba(255,255,255,.04), 0 8px 18px rgba(0,0,0,.18) !important;
}
html body section[data-testid="stSidebar"] div[data-testid="stExpander"] details {
  margin-top: .20rem !important;
  border-radius: 16px !important;
  overflow: hidden !important;
}
html body section[data-testid="stSidebar"] div[data-testid="stExpander"] summary {
  min-height: 34px !important;
  padding: .12rem .22rem !important;
  white-space: nowrap !important;
  overflow: hidden !important;
  text-overflow: clip !important;
}
html body section[data-testid="stSidebar"] div[data-testid="stExpander"] summary * {
  font-size: .76rem !important;
  line-height: 1.0 !important;
  white-space: nowrap !important;
  overflow: visible !important;
  text-overflow: clip !important;
}
/* v18.6.46: Admin/Drift labels must not be cut to Adr/Dri. */
html body section[data-testid="stSidebar"] div[data-testid="stExpander"] summary p {
  font-size: .78rem !important;
  max-width: 100% !important;
  white-space: nowrap !important;
  overflow: visible !important;
}
html body section[data-testid="stSidebar"] div[data-testid="stExpander"] summary svg {
  width: 13px !important;
  min-width: 13px !important;
}
/* Do not let Streamlit collapse buttons trap the layout. */
html body [data-testid="stSidebarCollapsedControl"],
html body [data-testid="collapsedControl"],
html body button[title*="sidebar" i],
html body button[aria-label*="sidebar" i] {
  display: none !important;
  pointer-events: none !important;
}
@media (max-width: 760px) {
  /* v18.6.42: mobile must never be trapped behind a wide drawer.
     Sidebar becomes a bottom navigation rail and leaves the main window visible. */
  html body section[data-testid="stSidebar"] {
    position: fixed !important;
    left: 0 !important;
    right: 0 !important;
    bottom: 0 !important;
    top: auto !important;
    width: 100vw !important;
    min-width: 100vw !important;
    max-width: 100vw !important;
    height: 68px !important;
    min-height: 68px !important;
    max-height: 68px !important;
    transform: none !important;
    visibility: visible !important;
    opacity: 1 !important;
    z-index: 9999 !important;
    overflow: hidden !important;
    border-right: 0 !important;
    border-top: 1px solid rgba(56,189,248,.35) !important;
    background: rgba(2,6,23,.96) !important;
    box-shadow: 0 -10px 30px rgba(0,0,0,.38) !important;
  }
  html body section[data-testid="stSidebar"] > div:first-child {
    padding: .30rem .42rem !important;
    width: 100vw !important;
    min-width: 100vw !important;
    max-width: 100vw !important;
    height: 68px !important;
    overflow: hidden !important;
  }
  html body section[data-testid="stSidebar"] .sidebar-section-title,
  html body section[data-testid="stSidebar"] .sidebar-section-title-account,
  html body section[data-testid="stSidebar"] .sidebar-section-title-advanced,
  html body section[data-testid="stSidebar"] .auth-sidebar-card,
  html body section[data-testid="stSidebar"] div[data-testid="stExpander"],
  html body section[data-testid="stSidebar"] div[data-testid="stCheckbox"],
  html body section[data-testid="stSidebar"] div[data-testid="stButton"] {
    display: none !important;
  }
  html body section[data-testid="stSidebar"] .sidebar2026-nav {
    display: grid !important;
    grid-template-columns: repeat(6, minmax(0, 1fr)) !important;
    gap: .26rem !important;
    width: calc(100vw - .84rem) !important;
    margin: 0 !important;
    align-items: center !important;
  }
  html body section[data-testid="stSidebar"] .sidebar2026-nav-item {
    width: auto !important;
    min-width: 0 !important;
    height: 56px !important;
    min-height: 56px !important;
    max-height: 56px !important;
    padding: .20rem .12rem !important;
    display: flex !important;
    flex-direction: column !important;
    align-items: center !important;
    justify-content: center !important;
    gap: .12rem !important;
    border-radius: 14px !important;
    margin: 0 !important;
    grid-template-columns: none !important;
  }
  html body section[data-testid="stSidebar"] .sidebar2026-nav-item b {
    width: 24px !important;
    height: 24px !important;
    font-size: .98rem !important;
  }
  html body section[data-testid="stSidebar"] .sidebar2026-nav-item span {
    display: block !important;
    font-size: .58rem !important;
    line-height: 1 !important;
    max-width: 100% !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    white-space: nowrap !important;
  }
  html body .stApp .block-container {
    padding-left: .42rem !important;
    padding-right: .42rem !important;
    padding-bottom: 5.2rem !important;
    max-width: 100% !important;
  }
  html body .stApp { overflow-x: hidden !important; }
}

/* v18.6.46 final desktop sidebar override: keep advanced labels readable. */
@media (min-width: 761px) {
  html body section[data-testid="stSidebar"] {
    width: 224px !important; min-width: 224px !important; max-width: 224px !important;
  }
  html body section[data-testid="stSidebar"] div[data-testid="stExpander"] summary {
    display: flex !important; align-items: center !important; gap: .20rem !important;
  }
}

html body section[data-testid="stSidebar"] .sidebar2026-nav-links-v18659 {
  display: flex !important;
  flex-direction: column !important;
  gap: .38rem !important;
  margin-bottom: .72rem !important;
}
html body section[data-testid="stSidebar"] .sidebar2026-nav-link-v18659 {
  display: grid !important;
  grid-template-columns: 30px minmax(0, 1fr) !important;
  align-items: center !important;
  gap: .42rem !important;
  min-height: 40px !important;
  padding: .34rem .48rem !important;
  border-radius: 15px !important;
  text-decoration: none !important;
  color: #f8fafc !important;
  background: linear-gradient(180deg, rgba(14,56,90,.92), rgba(8,30,55,.92)) !important;
  border: 1px solid rgba(96,165,250,.32) !important;
  box-shadow: inset 0 0 0 1px rgba(255,255,255,.04), 0 8px 18px rgba(0,0,0,.18) !important;
  cursor: pointer !important;
  pointer-events: auto !important;
}
html body section[data-testid="stSidebar"] .sidebar2026-nav-link-v18659:hover,
html body section[data-testid="stSidebar"] .sidebar2026-nav-link-v18659.active {
  border-color: rgba(56,189,248,.68) !important;
  background: linear-gradient(180deg, rgba(14,116,144,.82), rgba(8,47,73,.94)) !important;
}
html body section[data-testid="stSidebar"] .sidebar2026-nav-link-v18659 .nav-ico {
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  width: 28px !important;
  height: 28px !important;
  border-radius: 10px !important;
  background: rgba(14,116,144,.45) !important;
  font-size: 1.0rem !important;
}
html body section[data-testid="stSidebar"] .sidebar2026-nav-link-v18659 .nav-label {
  display: block !important;
  min-width: 0 !important;
  font-size: .86rem !important;
  font-weight: 950 !important;
  line-height: 1.05 !important;
  white-space: nowrap !important;
  overflow: visible !important;
}

</style>
"""
