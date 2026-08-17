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
AUTONOMY_WORKSPACE_ROUTE_LEASE_KEY_V19220_RC12 = "autonomy_workspace_route_lease_v19220_rc12"
GLOBAL_NAVIGATION_ROUTE_LEASE_KEY_V19220_RC14 = "global_navigation_route_lease_v19220_rc14"
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
REPORT_SURFACE_LABEL_BY_SLUG_V19220_RC1631T = {
    "report_history": "Rapporter, historikk og avansert",
    "report_progress": "Kjøring og fremdrift",
    "report_archive": "Hurtigarkiv og komplett ZIP",
}
REPORT_SURFACE_SLUG_BY_LABEL_V19220_RC1631T = {
    label: slug for slug, label in REPORT_SURFACE_LABEL_BY_SLUG_V19220_RC1631T.items()
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
        if subtab_s in REPORT_SURFACE_LABEL_BY_SLUG_V19220_RC1631T:
            session_state["mi_report_surface_v19220_rc1631t"] = REPORT_SURFACE_LABEL_BY_SLUG_V19220_RC1631T[subtab_s]
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
        report_surface = ""
        if slug == "reports":
            report_surface = REPORT_SURFACE_SLUG_BY_LABEL_V19220_RC1631T.get(
                str(session_state.get("mi_report_surface_v19220_rc1631t") or ""), ""
            )
        return slug, report_surface
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


def current_navigation_snapshot_v19220_rc14(st) -> dict[str, str]:
    """Return the best available visible route without touching widget keys.

    The URL is authoritative on browser refresh, while session state is the
    most recent source during an action-triggered rerun.  The snapshot is
    application-owned and can therefore be queued safely after widgets have
    already been instantiated.
    """
    url_state = get_global_navigation_state(st)
    state = st.session_state
    nav = str(
        state.get("active_nav_target_v18674c")
        or state.get("ai_control_center_force_nav_v18663")
        or url_state.get("nav")
        or ""
    ).strip().lower()
    group = str(
        state.get("ai_control_center_group_v1863aj")
        or state.get("ai_control_center_group_v1863m")
        or url_state.get("group")
        or ""
    ).strip()
    panel = str(
        state.get("ai_control_center_active_panel_v1863aj")
        or state.get("ai_control_center_active_panel_v1863m")
        or state.get("ai_control_center_active_real_panel_v18598")
        or url_state.get("panel")
        or ""
    ).strip()
    tab, subtab = current_route_tab_from_session_v19220_rc7(
        state, nav=nav, panel=panel,
    )
    tab = str(tab or url_state.get("tab") or "").strip()
    subtab = str(subtab or url_state.get("subtab") or "").strip()
    return normalize_navigation_values(nav, group, panel, tab, subtab)


def queue_global_navigation_route_v19220_rc14(
    st,
    *,
    source: str = "ACTION_RERUN_RC14",
    route: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Queue the visible route for the next full application run.

    This function intentionally does not write Streamlit widget keys.  It is
    safe to call from any button handler, including handlers rendered after
    the navigation radios/selectboxes.
    """
    raw = route or current_navigation_snapshot_v19220_rc14(st)
    snapshot = normalize_navigation_values(
        raw.get("nav"), raw.get("group"), raw.get("panel"),
        raw.get("tab"), raw.get("subtab"),
    )
    if not any(snapshot.values()):
        return snapshot
    payload = {**snapshot, "source": str(source or "ACTION_RERUN_RC14")}
    st.session_state[GLOBAL_NAVIGATION_ROUTE_LEASE_KEY_V19220_RC14] = payload
    return snapshot


def consume_global_navigation_route_v19220_rc14(st) -> bool:
    """Apply a queued global route before navigation widgets are created."""
    route = st.session_state.pop(GLOBAL_NAVIGATION_ROUTE_LEASE_KEY_V19220_RC14, None)
    if not isinstance(route, dict):
        return False
    normalized = normalize_navigation_values(
        route.get("nav"), route.get("group"), route.get("panel"),
        route.get("tab"), route.get("subtab"),
    )
    nav = normalized["nav"]
    group = normalized["group"]
    panel = normalized["panel"]
    tab = normalized["tab"]
    subtab = normalized["subtab"]
    state = st.session_state
    if nav:
        state["active_nav_target_v18674c"] = nav
        state["ai_control_center_force_nav_v18663"] = nav
        state["ai_control_center_last_applied_nav_v19016"] = nav
        state["mobile_nav_last_choice_v19015"] = nav
    if group:
        state["ai_control_center_group_v1863m"] = group
        state["ai_control_center_group_v1863aj"] = group
    if panel:
        state["ai_control_center_active_panel_v1863m"] = panel
        state["ai_control_center_active_panel_v1863aj"] = panel
        state["ai_control_center_active_real_panel_v18598"] = panel
        state["ai_control_center_route_lock_v19220_rc6"] = {
            "nav": nav,
            "group": group,
            "panel": panel,
            "tab": tab,
            "subtab": subtab,
            "source": str(route.get("source") or "ACTION_RERUN_RC14"),
        }
    apply_route_tab_to_session_state_v19220_rc7(
        state, nav=nav, panel=panel, tab=tab, subtab=subtab,
    )
    set_global_navigation_state(
        st, nav=nav, group=group, panel=panel, tab=tab, subtab=subtab,
    )
    state["navigation_last_source_v19143"] = str(route.get("source") or "ACTION_RERUN_RC14")
    return True


def install_navigation_rerun_guard_v19220_rc14(st) -> bool:
    """Wrap full-app ``st.rerun`` calls with one route-preservation lease.

    The guard covers existing menus without requiring 190+ individual button
    handlers to implement their own route code. Fragment-only reruns remain
    untouched. Explicit route helpers still win because they update the route
    before invoking ``st.rerun``.
    """
    marker = "_ai_aksje_navigation_rerun_guard_v19220_rc14"
    original_marker = "_ai_aksje_original_rerun_v19220_rc14"
    if bool(getattr(st, marker, False)):
        return False
    original = getattr(st, "rerun", None)
    if not callable(original):
        return False

    def guarded_rerun(*args, **kwargs):
        if str(kwargs.get("scope") or "app").strip().lower() != "fragment":
            try:
                queue_global_navigation_route_v19220_rc14(
                    st, source="GLOBAL_ST_RERUN_GUARD_RC14",
                )
            except Exception:
                pass
        return original(*args, **kwargs)

    setattr(st, original_marker, original)
    setattr(st, "rerun", guarded_rerun)
    setattr(st, marker, True)
    return True



def queue_autonomy_workspace_route_lease_v19220_rc12(
    session_state,
    *,
    workspace_slug: str = "reports",
    execution_id: str = "",
    source: str = "REPORT_ACTION_RC12",
) -> dict[str, str]:
    """Keep one Autonomy workspace stable across the job-start rerun lifecycle.

    The lease is application-owned state.  It is consumed before the Autonomy
    workspace radio is instantiated, so it never mutates a Streamlit widget key
    after creation.  A lease tied to an execution remains active while that
    execution is non-terminal and is released after its terminal state has been
    rendered once.
    """
    slug = str(workspace_slug or "reports").strip() or "reports"
    lease = {
        "workspace_slug": slug,
        "execution_id": str(execution_id or "").strip(),
        "source": str(source or "REPORT_ACTION_RC12"),
    }
    session_state[AUTONOMY_WORKSPACE_ROUTE_LEASE_KEY_V19220_RC12] = lease
    return lease


def consume_autonomy_workspace_route_lease_v19220_rc12(
    session_state,
    active_status: Any | None = None,
) -> bool:
    """Apply the RC12 workspace lease before the workspace radio is created."""
    lease = session_state.get(AUTONOMY_WORKSPACE_ROUTE_LEASE_KEY_V19220_RC12)
    if not isinstance(lease, dict):
        return False
    slug = str(lease.get("workspace_slug") or "reports").strip() or "reports"
    label = AUTONOMY_WORKSPACE_LABEL_BY_SLUG_V19220_RC7.get(slug)
    if not label:
        session_state.pop(AUTONOMY_WORKSPACE_ROUTE_LEASE_KEY_V19220_RC12, None)
        return False

    status = dict(active_status or {}) if isinstance(active_status, dict) else {}
    leased_execution = str(lease.get("execution_id") or "").strip()
    status_execution = str(status.get("execution_id") or "").strip()
    status_state = str(status.get("state") or "").upper()

    # Always apply at least once.  This closes the gap between accepting the
    # job and the first durable status read on the following Streamlit run.
    session_state["autonomy_core_workspace_slug_v1882"] = slug
    session_state["autonomy_core_workspace_v1880"] = label
    session_state["autonomy_core_workspace_active_slug_v19220_rc7"] = slug

    terminal = {"COMPLETED", "FAILED", "CANCELLED"}
    if not leased_execution:
        session_state.pop(AUTONOMY_WORKSPACE_ROUTE_LEASE_KEY_V19220_RC12, None)
    elif status_execution == leased_execution and status_state in terminal:
        # The widget key has now been set safely for the terminal render.  Its
        # own value remains Rapporter after the one-shot lease is released.
        session_state.pop(AUTONOMY_WORKSPACE_ROUTE_LEASE_KEY_V19220_RC12, None)
    elif status_execution and status_execution != leased_execution:
        # A newer accepted job owns the durable active pointer.  Do not let an
        # old lease force the page indefinitely.
        session_state.pop(AUTONOMY_WORKSPACE_ROUTE_LEASE_KEY_V19220_RC12, None)
    return True


def pin_autonomy_workspace_route_v19220_rc12(
    st,
    *,
    workspace_slug: str = "reports",
    public_nav: str = "reports",
    execution_id: str = "",
) -> None:
    """Queue an Autonomy route and optional execution-bound workspace lease."""
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
        # RC13: this helper runs from buttons inside an already rendered
        # Autonomi workspace. Never mutate the Streamlit radio widget key here.
        # The application-owned slug and route lease are consumed before the
        # radio is created on the following rerun.
        "autonomy_core_workspace_slug_v1882": slug,
        "autonomy_core_workspace_active_slug_v19220_rc7": slug,
        "mobile_nav_last_choice_v19015": nav,
        "ai_control_center_menu_open_v1863ag": False,
        "navigation_last_source_v19143": "REPORT_ACTION_ROUTE_LEASE_RC12",
        "ai_control_center_route_lock_v19220_rc6": {
            "nav": AUTONOMY_NAV,
            "group": AUTONOMY_GROUP,
            "panel": AUTONOMY_PANEL,
            "tab": slug,
            "public_nav": nav,
            "source": "REPORT_ACTION_ROUTE_LEASE_RC12",
        },
    }
    for key, value in updates.items():
        state[key] = value
    queue_autonomy_workspace_route_lease_v19220_rc12(
        state, workspace_slug=slug, execution_id=execution_id,
    )
    set_global_navigation_state(
        st, nav=AUTONOMY_NAV, group=AUTONOMY_GROUP, panel=AUTONOMY_PANEL,
        tab=slug, subtab="",
    )


def pin_autonomy_workspace_route_v19220_rc13(
    st,
    *,
    workspace_slug: str = "reports",
    public_nav: str = "reports",
    execution_id: str = "",
) -> None:
    """RC13 route helper: queue state only; widget keys change before render."""
    pin_autonomy_workspace_route_v19220_rc12(
        st, workspace_slug=workspace_slug, public_nav=public_nav,
        execution_id=execution_id,
    )


def pin_autonomy_workspace_route_v19220_rc11(
    st,
    *,
    workspace_slug: str = "reports",
    public_nav: str = "reports",
    execution_id: str = "",
) -> None:
    """Backward-compatible alias for the RC12 route lease."""
    pin_autonomy_workspace_route_v19220_rc12(
        st, workspace_slug=workspace_slug, public_nav=public_nav,
        execution_id=execution_id,
    )


def pin_autonomy_workspace_route_v19220_rc9(
    st,
    *,
    workspace_slug: str = "reports",
    public_nav: str = "reports",
    execution_id: str = "",
) -> None:
    """Backward-compatible alias for the RC12 route lease."""
    pin_autonomy_workspace_route_v19220_rc12(
        st, workspace_slug=workspace_slug, public_nav=public_nav,
        execution_id=execution_id,
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
