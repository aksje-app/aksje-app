"""Global busy/run indicator helpers.

v18.5.34 keeps one fixed top-right app status chip.  Streamlit reruns the app
on many widget changes; these helpers keep a small, consistent status that can
be shown in the sticky topbar and updated by modules that start real work.
"""

from __future__ import annotations
from utils import _now_iso  # v18.6.3 centralized helpers

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import streamlit as st

BUSY_STATE_KEY = "global_busy_state_v18570"
DEFAULT_IDLE_LABEL = "Klar"




def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        return datetime.fromisoformat(text).replace(tzinfo=None)
    except Exception:
        return None


def set_global_busy(label: str = "Jobber", detail: str = "", *, step: int | None = None, total: int | None = None) -> None:
    """Mark the app as busy.

    Used both by button callbacks and by long-running modules.  The state is
    intentionally lightweight and safe to call before a rerun.
    """
    st.session_state[BUSY_STATE_KEY] = {
        "running": True,
        "label": str(label or "Jobber"),
        "detail": str(detail or ""),
        "step": step,
        "total": total,
        "updated_at": _now_iso(),
    }


def update_global_busy(label: str | None = None, detail: str | None = None, *, step: int | None = None, total: int | None = None) -> None:
    state = dict(st.session_state.get(BUSY_STATE_KEY) or {})
    state["running"] = True
    if label is not None:
        state["label"] = str(label)
    if detail is not None:
        state["detail"] = str(detail)
    if step is not None:
        state["step"] = step
    if total is not None:
        state["total"] = total
    state["updated_at"] = _now_iso()
    st.session_state[BUSY_STATE_KEY] = state


def finish_global_busy(label: str = "Klar", detail: str = "") -> None:
    st.session_state[BUSY_STATE_KEY] = {
        "running": False,
        "label": str(label or DEFAULT_IDLE_LABEL),
        "detail": str(detail or ""),
        "step": None,
        "total": None,
        "updated_at": _now_iso(),
    }


def mark_choice_update(label: str = "Oppdaterer valg") -> None:
    """Callback-friendly helper for lightweight widget changes.

    v18.5.48: A normal widget change must not put the whole app into a
    running/busy state. Earlier versions used ``set_global_busy`` here, which
    made every selectbox/radio change look like a long job and could leave the
    header in a dimmed/spinner state until the next cleanup. Keep this as an
    idle status update only; real work calls set_global_busy/update_global_busy.
    """
    st.session_state[BUSY_STATE_KEY] = {
        "running": False,
        "label": str(label or "Valg oppdatert"),
        "detail": "Valg endret – tung analyse venter på Global oppdatering der det er relevant.",
        "step": None,
        "total": None,
        "updated_at": _now_iso(),
    }


def get_global_busy_snapshot(*, stale_seconds: int = 90) -> Dict[str, Any]:
    state = dict(st.session_state.get(BUSY_STATE_KEY) or {})
    if not state:
        return {"running": False, "label": DEFAULT_IDLE_LABEL, "detail": "", "step": None, "total": None}

    updated = _parse_iso(state.get("updated_at"))
    if bool(state.get("running")) and updated and datetime.now(timezone.utc) - updated > timedelta(seconds=stale_seconds):
        # Do not leave a permanent busy indicator if a run crashed or completed without cleanup.
        state["running"] = False
        state["label"] = DEFAULT_IDLE_LABEL
        state["detail"] = "Sist jobb ble avsluttet/utløpt."
        st.session_state[BUSY_STATE_KEY] = state
    return state


def global_busy_chip_html() -> str:
    state = get_global_busy_snapshot()
    running = bool(state.get("running"))
    label = str(state.get("label") or ("Jobber" if running else DEFAULT_IDLE_LABEL))
    detail = str(state.get("detail") or "")
    step = state.get("step")
    total = state.get("total")
    step_txt = ""
    if step is not None and total is not None:
        step_txt = f" · {step}/{total}"
    title = f"{label}{step_txt}"
    if detail:
        title += f" — {detail}"
    safe_title = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    if running:
        return (
            f'<span class="ptw-pill ptw-pill-busy ptw-busy-running" title="{safe_title}">'
            f'<span class="ptw-busy-spinner" aria-hidden="true"></span>'
            f'<span class="ptw-busy-copy"><b>Jobber...</b>{step_txt}<span class="ptw-busy-sep"> · </span>{label}</span>'
            f'</span>'
        )
    return f'<span class="ptw-pill ptw-pill-ready" title="{safe_title}">✅ <b>{label}</b></span>'
