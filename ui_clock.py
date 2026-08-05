"""Passive live clock UI; deliberately isolated from navigation state."""
from __future__ import annotations

from local_time import browser_clock_document, display_timezone_name
from settings_store import load_settings


def render_sidebar_clock_v19220_rc163(st) -> None:
    """Show browser/PC time and persisted app display time in the sidebar."""
    try:
        from streamlit.components.v1 import html as components_html
        app_timezone = display_timezone_name(load_settings() or {}, streamlit_module=st)
        with st.sidebar:
            st.markdown(
                "<div class='sidebar-section-title sidebar-clock-title-v19220-rc163'>Klokke</div>",
                unsafe_allow_html=True,
            )
            components_html(browser_clock_document(app_timezone), height=92, scrolling=False)
    except Exception:
        # Informational only: failure must never affect navigation or the app.
        pass
