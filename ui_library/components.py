from __future__ import annotations

import html
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from .theme import UI_TOKENS


def _esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def page_header(st_module, title: str, subtitle: str = "") -> None:
    body = f'<div class="aa-ui-page-subtitle">{_esc(subtitle)}</div>' if subtitle else ""
    st_module.markdown(
        f'<div class="aa-ui-page-header"><div class="aa-ui-page-title">{_esc(title)}</div>{body}</div>',
        unsafe_allow_html=True,
    )


def section_header(st_module, title: str, caption: str = "") -> None:
    st_module.markdown(f'<div class="aa-ui-section-header">{_esc(title)}</div>', unsafe_allow_html=True)
    if caption:
        st_module.caption(caption)


def status_badge(label: str, tone: str = "info") -> str:
    colors = {
        "success": UI_TOKENS.success,
        "warning": UI_TOKENS.warning,
        "danger": UI_TOKENS.danger,
        "info": UI_TOKENS.info,
        "neutral": UI_TOKENS.text_muted,
    }
    color = colors.get(str(tone).lower(), UI_TOKENS.info)
    return f'<span class="aa-ui-badge" style="color:{color}">{_esc(label)}</span>'


def info_banner(st_module, title: str, body: str = "", tone: str = "info") -> None:
    colors = {
        "success": UI_TOKENS.success,
        "warning": UI_TOKENS.warning,
        "danger": UI_TOKENS.danger,
        "info": UI_TOKENS.info,
        "neutral": UI_TOKENS.text_muted,
    }
    color = colors.get(str(tone).lower(), UI_TOKENS.info)
    body_html = f'<div class="aa-ui-banner-body">{_esc(body)}</div>' if body else ""
    st_module.markdown(
        f'<div class="aa-ui-banner" style="--aa-accent:{color}"><div class="aa-ui-banner-title">{_esc(title)}</div>{body_html}</div>',
        unsafe_allow_html=True,
    )


def empty_state(st_module, title: str, body: str = "") -> None:
    suffix = f"<br><small>{_esc(body)}</small>" if body else ""
    st_module.markdown(f'<div class="aa-ui-empty"><b>{_esc(title)}</b>{suffix}</div>', unsafe_allow_html=True)


def compact_status_grid(st_module, rows: Iterable[Mapping[str, Any]]) -> None:
    items = []
    for row in rows:
        label = row.get("label", "")
        value = row.get("value", "-")
        tone = str(row.get("tone", "neutral"))
        badge = status_badge(str(value), tone)
        items.append(
            '<div class="aa-ui-status-item">'
            f'<div class="aa-ui-status-label">{_esc(label)}</div>'
            f'<div class="aa-ui-status-value">{badge}</div>'
            '</div>'
        )
    st_module.markdown(f'<div class="aa-ui-status-grid">{"".join(items)}</div>', unsafe_allow_html=True)


def kpi_row(st_module, metrics: Sequence[Mapping[str, Any]], columns: int | None = None) -> None:
    if not metrics:
        return
    count = max(1, min(int(columns or len(metrics)), len(metrics)))
    cols = st_module.columns(count)
    for idx, metric in enumerate(metrics):
        with cols[idx % count]:
            label = _esc(metric.get("label", ""))
            value = _esc(metric.get("value", "-"))
            delta = metric.get("delta")
            delta_html = f'<div class="aa-ui-kpi-delta">{_esc(delta)}</div>' if delta not in (None, "") else ""
            st_module.markdown(
                f'<div class="aa-ui-status-item"><div class="aa-ui-kpi-label">{label}</div><div class="aa-ui-kpi-value">{value}</div>{delta_html}</div>',
                unsafe_allow_html=True,
            )


def action_row(st_module, actions: Sequence[Mapping[str, Any]], columns: int | None = None) -> dict[str, bool]:
    """Render a consistent action row and return click state by action id."""
    if not actions:
        return {}
    count = max(1, min(int(columns or len(actions)), len(actions)))
    cols = st_module.columns(count)
    clicked: dict[str, bool] = {}
    for idx, action in enumerate(actions):
        action_id = str(action.get("id") or f"action_{idx}")
        with cols[idx % count]:
            clicked[action_id] = bool(
                st_module.button(
                    str(action.get("label") or action_id),
                    key=str(action.get("key") or action_id),
                    type=str(action.get("type") or "secondary"),
                    disabled=bool(action.get("disabled", False)),
                    width="stretch" if bool(action.get("use_container_width", True)) else "content",
                    help=action.get("help"),
                )
            )
    return clicked
