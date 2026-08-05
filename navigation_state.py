"""Global navigation/query-state helpers for AI Aksje Analyzer Pro.

v18.6.74e goal:
- Browser refresh/F5 should restore current main area, panel and inner tab across all main panels.
- Authentication tokens must never be preserved in navigation URLs.
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


# v19.22.0 RC7: one canonical URL route per visible control-center panel.
# The previous outer renderer wrote ``control_center`` while inner workspaces
# wrote routes such as ``autonomy``. That route ping-pong could trigger extra
# Streamlit reruns, preserve stale DOM during refresh and restore the wrong page.
CANONICAL_NAV_BY_PANEL_V19220_RC7 = {
    AUTONOMY_PANEL: AUTONOMY_NAV,
    "💱 Valutavarsler": "fx_alerts",
    "Top Picks": "top_picks",
    "⭐ Analyse – Top Picks": "top_picks",
    "Long Engine": "long_engine",
    "📈 Analyse – Long Engine": "long_engine",
    "AI Kandidattest": "analysis",
    "🤖 AI – Kandidattest": "analysis",
    "Paper Trading og kontroll": "paper_trading",
    "System/admin": "system",
    "⚙️ Innstillinger – System/admin": "system",
}

AUTONOMY_WORKSPACE_LABEL_BY_SLUG_V19220_RC7 = {
    "overview": "Oversikt",
    "reports": "Rapporter",
    "orchestrator": "Orkestrering og tidsplan",
    "autonomous_portfolio": "Autonom portefølje",
    "learning_portfolio": "Læringsportefølje",
    "architecture": "Ekspertkontroll",
    "operations": "Varsler og drift",
    "strategy_versions": "Strategiversjoner",
    "strategy_lab": "Strategy Lab",
    "engine_details": "Motorresultater",
}
AUTONOMY_WORKSPACE_SLUG_BY_LABEL_V19220_RC7 = {
    label: slug for slug, label in AUTONOMY_WORKSPACE_LABEL_BY_SLUG_V19220_RC7.items()
}


def canonical_nav_for_panel_v19220_rc7(group: Any = "", panel: Any = "", fallback: Any = "control_center") -> str:
    """Return the single canonical route for a visible control-center panel."""
    group_s = str(group or "").strip()
    panel_s = str(panel or "").strip()
    mapped = CANONICAL_NAV_BY_PANEL_V19220_RC7.get(panel_s)
    if mapped:
        return mapped
    if group_s == AUTONOMY_GROUP and panel_s == AUTONOMY_PANEL:
        return AUTONOMY_NAV
    return str(fallback or "control_center").strip().lower() or "control_center"


def apply_route_tab_to_session_state_v19220_rc7(
    session_state,
    *,
    nav: Any = "",
    panel: Any = "",
    tab: Any = "",
    subtab: Any = "",
) -> bool:
    """Restore a URL/file tab only into the workspace that owns that route.

    Older bootstrap code copied every ``aa_tab`` into Autonomi, Paper Trading
    and AI Discovery simultaneously. A refresh could therefore contaminate
    unrelated workspaces. RC7 keeps tab state route-scoped.
    """
    nav_s = str(nav or "").strip().lower()
    panel_s = str(panel or "").strip()
    tab_s = str(tab or "").strip()
    subtab_s = str(subtab or "").strip()
    if not tab_s and not subtab_s:
        return False

    changed = False
    if panel_s == AUTONOMY_PANEL or nav_s in AUTONOMY_NAV_ALIASES | {"reports", "jobs", "portfolio", "approvals", "operations"}:
        if tab_s:
            session_state["autonomy_core_workspace_slug_v1882"] = tab_s
            changed = True
    elif panel_s == "Paper Trading og kontroll" or nav_s in {"paper", "paper_trading", "papertrading"}:
        if tab_s:
            session_state["paper_trading_active_tab_slug_v18674c"] = tab_s
            changed = True
        if subtab_s:
            session_state["paper_trading_active_subtab_slug_v18674c"] = subtab_s
            changed = True
    elif "AI Discovery" in panel_s:
        if tab_s:
            session_state["ai_discovery_active_tab_slug_v18674c"] = tab_s
            changed = True
    return changed


def current_route_tab_from_session_v19220_rc7(session_state, *, nav: Any = "", panel: Any = "") -> tuple[str, str]:
    """Read only the tab state owned by the currently visible route."""
    nav_s = str(nav or "").strip().lower()
    panel_s = str(panel or "").strip()
    if panel_s == AUTONOMY_PANEL or nav_s in AUTONOMY_NAV_ALIASES | {"reports", "jobs", "portfolio", "approvals", "operations"}:
        slug = str(session_state.get("autonomy_core_workspace_active_slug_v19220_rc7") or "").strip()
        if not slug:
            label = str(session_state.get("autonomy_core_workspace_v1880") or "").strip()
            slug = AUTONOMY_WORKSPACE_SLUG_BY_LABEL_V19220_RC7.get(label, "")
        if not slug:
            slug = str(session_state.get("autonomy_core_workspace_slug_v1882") or "").strip()
        return slug, ""
    if panel_s == "Paper Trading og kontroll" or nav_s in {"paper", "paper_trading", "papertrading"}:
        return (
            str(session_state.get("paper_trading_active_tab_slug_v18674c") or "").strip(),
            str(session_state.get("paper_trading_active_subtab_slug_v18674c") or "").strip(),
        )
    if "AI Discovery" in panel_s:
        return str(session_state.get("ai_discovery_active_tab_slug_v18674c") or "").strip(), ""
    return "", ""


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
    """Set only navigation query keys and remove legacy authentication tokens.

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
        sensitive_removed = False
        for sensitive_key in ("remember_token", "remember_bootstrap"):
            if sensitive_key in current:
                try:
                    del st.query_params[sensitive_key]
                    sensitive_removed = True
                except Exception:
                    pass
                current.pop(sensitive_key, None)
        changed = sensitive_removed
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



def pin_autonomy_workspace_route_v19220_rc9(
    st,
    *,
    workspace_slug: str = "reports",
    public_nav: str = "reports",
) -> None:
    """Pin one Autonomy workspace before a Streamlit action reruns the app.

    Report-center buttons previously started work and then called ``st.rerun``
    while stale control-center radio values still pointed at AI Kandidattest.
    RC9 writes one complete route snapshot before the rerun so the action stays
    on the page where it was initiated.  This helper only changes UI routing.
    """
    slug = str(workspace_slug or "reports").strip() or "reports"
    nav = str(public_nav or "reports").strip().lower() or "reports"
    label = AUTONOMY_WORKSPACE_LABEL_BY_SLUG_V19220_RC7.get(slug, "Rapporter")
    state = st.session_state
    updates = {
        "active_nav_target_v18674c": nav,
        "ai_control_center_force_nav_v18663": nav,
        "ai_control_center_last_applied_nav_v19016": nav,
        "ai_control_center_group_v1863m": AUTONOMY_GROUP,
        "ai_control_center_active_panel_v1863m": AUTONOMY_PANEL,
        "ai_control_center_active_real_panel_v18598": AUTONOMY_PANEL,
        "ai_control_center_group_v1863aj": AUTONOMY_GROUP,
        "ai_control_center_active_panel_v1863aj": AUTONOMY_PANEL,
        "ai_control_center_group_radio_v1863aj": "Autonomi (1)",
        "ai_control_center_panel_radio_v1863aj_Autonomi": AUTONOMY_PANEL,
        "autonomy_core_workspace_slug_v1882": slug,
        "autonomy_core_workspace_v1880": label,
        "autonomy_core_workspace_active_slug_v19220_rc7": slug,
        "mobile_nav_last_choice_v19015": nav,
        "ai_control_center_menu_open_v1863ag": False,
        "navigation_last_source_v19143": "REPORT_ACTION_PIN_RC9",
    }
    for key, value in updates.items():
        state[key] = value
    set_global_navigation_state(
        st,
        nav=AUTONOMY_NAV,
        group=AUTONOMY_GROUP,
        panel=AUTONOMY_PANEL,
        tab=slug,
        subtab="",
    )

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

# v19.14.4: keys that background status refreshes are never allowed to change.
NAVIGATION_GUARD_KEYS_V19144 = (
    "active_nav_target_v18674c",
    "ai_control_center_group_v1863m",
    "ai_control_center_group_v1863aj",
    "ai_control_center_active_panel_v1863m",
    "ai_control_center_active_panel_v1863aj",
    "ai_control_center_active_real_panel_v18598",
    "ai_control_center_group_radio_v1863aj",
    "autonomy_core_workspace_slug_v1882",
    "paper_trading_active_tab_slug_v18674c",
    "paper_trading_active_subtab_slug_v18674c",
    "ai_discovery_active_tab_slug_v18674c",
    "mobile_nav_last_choice_v19015",
)


def capture_navigation_checkpoint_v19144(st) -> dict[str, Any]:
    """Capture user-owned navigation before a background-only fragment refresh."""
    values = {key: st.session_state.get(key) for key in NAVIGATION_GUARD_KEYS_V19144}
    for key in list(st.session_state.keys()):
        if str(key).startswith("ai_control_center_panel_radio_v1863aj_"):
            values[str(key)] = st.session_state.get(key)
    return {
        "revision": int(st.session_state.get("navigation_user_revision_v19143", 0) or 0),
        "values": values,
    }


def restore_navigation_checkpoint_v19144(st, checkpoint: dict[str, Any] | None) -> bool:
    """Restore navigation only when no user click occurred during the refresh."""
    if not isinstance(checkpoint, dict):
        return False
    before_revision = int(checkpoint.get("revision", 0) or 0)
    current_revision = int(st.session_state.get("navigation_user_revision_v19143", 0) or 0)
    if current_revision != before_revision:
        return False
    values = checkpoint.get("values") or {}
    if not isinstance(values, dict):
        return False
    for key, value in values.items():
        if value is None:
            st.session_state.pop(key, None)
        else:
            st.session_state[key] = value
    st.session_state["navigation_last_source_v19143"] = "BACKGROUND_PRESERVED"
    return True
