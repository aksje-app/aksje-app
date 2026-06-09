"""Stable sidebar renderer for AI Aksje Analyzer Pro.

v18.6.42 goal:
- One source of truth for sidebar structure.
- Avoid fragmented inline sidebar HTML in app.py.
- Keep desktop readable and prevent mobile drawer from blocking the app.
"""
from __future__ import annotations


def render_stable_sidebar_v18641(st, current_user, render_user_admin):
    """Render the left sidebar and return the advanced drift toggle state.

    The function intentionally receives `st` and auth renderer from app.py to avoid
    changing login/session logic in this stabilization step.
    """
    st.sidebar.markdown(_SIDEBAR_CSS_V18641, unsafe_allow_html=True)

    st.sidebar.markdown("<div class='sidebar-section-title'>Navigasjon</div>", unsafe_allow_html=True)
    st.sidebar.markdown(
        """
        <div class='sidebar2026-nav'>
          <div class='sidebar2026-nav-item' title='Dashboard'><b>🏠</b><span>Dashboard</span></div>
          <div class='sidebar2026-nav-item' title='Analyse'><b>📈</b><span>Analyse</span></div>
          <div class='sidebar2026-nav-item' title='Top Picks'><b>🎯</b><span>Top Picks</span></div>
          <div class='sidebar2026-nav-item' title='AI'><b>🤖</b><span>AI</span></div>
          <div class='sidebar2026-nav-item' title='System'><b>⚙️</b><span>System</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.sidebar.markdown("<div class='sidebar-section-title sidebar-section-title-account'>Konto</div>", unsafe_allow_html=True)
    render_user_admin(current_user)

    st.sidebar.markdown("<div class='sidebar-section-title sidebar-section-title-advanced'>Avansert</div>", unsafe_allow_html=True)
    with st.sidebar.expander("🔧 Drift", expanded=False):
        show_drift = st.checkbox(
            "Vis global oppdatering",
            value=False,
            key="show_drift_controls_v1863cc",
            help="Avansert drift/admin. Paper-kontrollene ligger i Paper Trading.",
        )
    return bool(show_drift)


_SIDEBAR_CSS_V18641 = """
<style>
/* v18.6.42 stable sidebar: desktop full menu, mobile bottom rail. */
html body section[data-testid="stSidebar"] {
  width: 188px !important;
  min-width: 188px !important;
  max-width: 188px !important;
  overflow-x: hidden !important;
  overflow-y: auto !important;
  border-right: 1px solid rgba(56,189,248,.20) !important;
}
html body section[data-testid="stSidebar"] > div:first-child {
  padding: .72rem .62rem !important;
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
  min-height: 36px !important;
  padding: .32rem .48rem !important;
  border-radius: 14px !important;
  font-size: .82rem !important;
  white-space: nowrap !important;
}
html body section[data-testid="stSidebar"] div[data-testid="stExpander"] details { margin-top: .20rem !important; border-radius: 16px !important; }
html body section[data-testid="stSidebar"] div[data-testid="stExpander"] summary,
html body section[data-testid="stSidebar"] div[data-testid="stExpander"] summary * {
  min-height: 36px !important;
  padding: .16rem .28rem !important;
  font-size: .82rem !important;
  line-height: 1.1 !important;
  white-space: nowrap !important;
  overflow: visible !important;
  text-overflow: clip !important;
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
    grid-template-columns: repeat(5, minmax(0, 1fr)) !important;
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

</style>
"""
