"""
v18.6.1 — Desktop UX Patch
Drop-in Streamlit CSS helpers for compact desktop control bars and stable rerun layout.
"""

import streamlit as st

APP_VERSION = "v18.6.1"
APP_VERSION_NAME = "Daily Report & Desktop UX Patch"


def inject_desktop_ux_css() -> None:
    st.markdown(
        """
<style>
/* v18.6.1 — desktop layout stability */
@media (min-width: 769px) {
  .stButton > button {
    min-height: 34px !important;
    height: 34px !important;
    padding: 0.25rem 0.85rem !important;
    border-radius: 12px !important;
    font-size: 0.88rem !important;
    line-height: 1.1 !important;
    white-space: nowrap !important;
  }

  div[data-testid="stHorizontalBlock"] { gap: 0.45rem !important; }
  section.main .block-container { padding-top: 0.75rem !important; max-width: 98vw !important; }

  .global-update-panel,
  .global-update-box,
  .status-large-panel {
    display: none !important;
  }

  .compact-status-line {
    border: 1px solid rgba(72, 202, 255, 0.55);
    border-radius: 10px;
    padding: 0.35rem 0.65rem;
    background: rgba(12, 34, 62, 0.72);
    color: #eaf6ff;
    font-weight: 700;
    font-size: 0.82rem;
    white-space: nowrap !important;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .status-badge,
  .control-chip,
  .floating-status,
  .active-main-panel-badge,
  .active-panel-badge {
    min-width: max-content !important;
    max-width: none !important;
    white-space: nowrap !important;
    word-break: normal !important;
    overflow-wrap: normal !important;
    writing-mode: horizontal-tb !important;
  }

  * {
    word-break: normal;
  }
}

@media (max-width: 768px) {
  .compact-status-line { font-size: 0.78rem; padding: 0.45rem 0.65rem; }
}
</style>
        """,
        unsafe_allow_html=True,
    )


def render_compact_control_bar(global_update_callback=None) -> None:
    """Render one compact horizontal top control line.

    Wire callbacks from the host app if available. This function intentionally
    does not start/stop trading itself.
    """
    cols = st.columns([1, 1, 1, 1.15, 1.15, 1.35], gap="small")
    with cols[0]: st.button("▶ Start", key="v1861_start")
    with cols[1]: st.button("Ⅱ Pause", key="v1861_pause")
    with cols[2]: st.button("⛔ Stopp", key="v1861_stop")
    with cols[3]: st.button("🚨 Nødstopp", key="v1861_emergency")
    with cols[4]: st.button("🔓 Gjør klar", key="v1861_arm")
    with cols[5]:
        if st.button("🔄 Global oppdatering", key="v1861_global_update"):
            if callable(global_update_callback):
                global_update_callback()


def render_compact_status(status: str = "Klar", last_update: str = "Ikke oppdatert") -> None:
    st.markdown(
        f'<div class="compact-status-line">Status: {status} • Sist: {last_update}</div>',
        unsafe_allow_html=True,
    )
