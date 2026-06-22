"""Global navigation/query-state helpers for AI Aksje Analyzer Pro.

v18.6.74c goal:
- Browser refresh/F5 should restore current main area, panel and inner tab.
- Existing remember_token and other query parameters must be preserved.
- Query parameters are additive: aa_nav, aa_group, aa_panel, aa_tab, aa_subtab.
"""
from __future__ import annotations

from typing import Any

QUERY_KEYS_V18674C = ("aa_nav", "aa_group", "aa_panel", "aa_tab", "aa_subtab")


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


def get_global_navigation_state(st) -> dict[str, str]:
    params = _plain_query_params(st)
    return {
        "nav": str(params.get("aa_nav") or "").strip(),
        "group": str(params.get("aa_group") or "").strip(),
        "panel": str(params.get("aa_panel") or "").strip(),
        "tab": str(params.get("aa_tab") or "").strip(),
        "subtab": str(params.get("aa_subtab") or "").strip(),
    }


def set_global_navigation_state(
    st,
    *,
    nav: Any | None = None,
    group: Any | None = None,
    panel: Any | None = None,
    tab: Any | None = None,
    subtab: Any | None = None,
) -> None:
    """Set only our navigation query keys and preserve remember_token/other keys."""
    updates = {
        "aa_nav": nav,
        "aa_group": group,
        "aa_panel": panel,
        "aa_tab": tab,
        "aa_subtab": subtab,
    }
    try:
        for key, value in updates.items():
            if value is None:
                continue
            value_s = str(value or "").strip()
            if value_s:
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
