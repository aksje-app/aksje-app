"""Global navigation/query-state helpers for AI Aksje Analyzer Pro.

v18.6.74e goal:
- Browser refresh/F5 should restore current main area, panel and inner tab across all main panels.
- Existing remember_token and other query parameters must be preserved.
- Query parameters are additive: aa_nav, aa_group, aa_panel, aa_tab, aa_subtab.
"""
from __future__ import annotations

from typing import Any

QUERY_KEYS_V18674C = ("aa_nav", "aa_group", "aa_panel", "aa_tab", "aa_subtab")
SESSION_KEYS_V18674E = ("active_nav_target_v18674c", "ai_control_center_group_v1863aj", "ai_control_center_active_panel_v1863aj", "paper_trading_active_tab_slug_v18674c", "ai_discovery_active_tab_slug_v18674c")
AUTONOMY_NAV = "autonomy"
AUTONOMY_GROUP = "Autonomi"
AUTONOMY_PANEL = "🧠 Autonomi – Kontrollsenter"
AUTONOMY_NAV_ALIASES = {"autonomy", "autonomous", "autonomi"}
AUTONOMY_PANEL_ALIASES = {
    AUTONOMY_PANEL: "overview",
    "🧠 Autonomi – Learning Portfolio": "learning_portfolio",
    "🚦 Autonomi – Orchestrator & Scheduler": "orchestrator",
    "Autonomi – Learning Portfolio": "learning_portfolio",
    "Autonomi – Orchestrator & Scheduler": "orchestrator",
}


def _plain_query_params(st) -> dict[str, str]:
    try:
        raw = dict(st.query_params)
    except Exception:
        try:
            raw = {k: v[0] if isinstance(v, list) and v else v for k, v in st.experimental_get_query_params().items()}
        except Exception:
            raw = {}
    out: dict[str, str] = {}
    for key, value in (raw or {}).items():
        if isinstance(value, (list, tuple)):
            out[str(key)] = str(value[0]) if value else ""
        else:
            out[str(key)] = str(value)
    return out


def normalize_navigation_values(
    nav: Any = "", group: Any = "", panel: Any = "", tab: Any = "", subtab: Any = "",
) -> dict[str, str]:
    """Map legacy Autonomy routes to the canonical v18.8.2 route."""
    nav_s, group_s, panel_s = str(nav or "").strip(), str(group or "").strip(), str(panel or "").strip()
    tab_s, subtab_s = str(tab or "").strip(), str(subtab or "").strip()
    if nav_s.casefold() in AUTONOMY_NAV_ALIASES or panel_s in AUTONOMY_PANEL_ALIASES:
        legacy_workspace = AUTONOMY_PANEL_ALIASES.get(panel_s, "")
        nav_s, group_s, panel_s = AUTONOMY_NAV, AUTONOMY_GROUP, AUTONOMY_PANEL
        if legacy_workspace and legacy_workspace != "overview" and not tab_s:
            tab_s = legacy_workspace
    return {"nav": nav_s, "group": group_s, "panel": panel_s, "tab": tab_s, "subtab": subtab_s}


def get_global_navigation_state(st) -> dict[str, str]:
    params = _plain_query_params(st)
    # v18.6.74d: allow old query names as read-only fallback, but only write aa_* keys.
    nav = str(params.get("aa_nav") or params.get("mobile_nav") or "").strip()
    group = str(params.get("aa_group") or "").strip()
    panel = str(params.get("aa_panel") or params.get("panel") or "").strip()
    tab = str(params.get("aa_tab") or params.get("tab") or "").strip()
    subtab = str(params.get("aa_subtab") or params.get("subtab") or "").strip()
    return normalize_navigation_values(nav, group, panel, tab, subtab)


def set_global_navigation_state(
    st,
    *,
    nav: Any | None = None,
    group: Any | None = None,
    panel: Any | None = None,
    tab: Any | None = None,
    subtab: Any | None = None,
) -> None:
    """Set only our navigation query keys and preserve remember_token/other keys.

    v18.6.74e: Do not write query params when they already have the same
    values. Streamlit reruns on query-param writes, so repeated no-op writes can
    make the app feel slow.
    """
    updates = {
        "aa_nav": nav,
        "aa_group": group,
        "aa_panel": panel,
        "aa_tab": tab,
        "aa_subtab": subtab,
    }
    try:
        current = _plain_query_params(st)
        changed = False
        for key, value in updates.items():
            if value is None:
                continue
            value_s = str(value or "").strip()
            current_s = str(current.get(key, "") or "").strip()
            if value_s and current_s != value_s:
                changed = True
                break
            if not value_s and key in current:
                changed = True
                break
        if not changed:
            return
        for key, value in updates.items():
            if value is None:
                continue
            value_s = str(value or "").strip()
            current_s = str(current.get(key, "") or "").strip()
            if value_s:
                if current_s != value_s:
                    st.query_params[key] = value_s
            else:
                if key in st.query_params:
                    del st.query_params[key]
    except Exception:
        # Do not let navigation state break the app on older Streamlit builds.
        pass


def clear_global_navigation_state(st, *, keep_nav: bool = False) -> None:
    keys = list(QUERY_KEYS_V18674C)
    if keep_nav and "aa_nav" in keys:
        keys.remove("aa_nav")
    try:
        for key in keys:
            if key in st.query_params:
                del st.query_params[key]
    except Exception:
        pass


def slugify_state_value(value: Any) -> str:
    raw = str(value or "").strip().lower()
    repl = {
        "æ": "ae",
        "ø": "o",
        "å": "a",
        "ä": "a",
        "ö": "o",
        "é": "e",
    }
    for src, dst in repl.items():
        raw = raw.replace(src, dst)
    out = []
    for ch in raw:
        out.append(ch if ch.isalnum() else "_")
    slug = "".join(out)
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug.strip("_")
