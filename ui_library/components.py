from __future__ import annotations

import html
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from .theme import UI_TOKENS
from .models import ActionView, DecisionView, JobStatusView, MetricView, PageStateView, TimelineStepView


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

def hero_status(st_module, *, title: str, body: str = "", module: str = "overview", tone: str = "neutral") -> None:
    st_module.markdown(f'<section class="aa-ui-hero aa-module-{_esc(module)} tone-{_esc(tone)}"><h1>{_esc(title)}</h1><p>{_esc(body)}</p></section>', unsafe_allow_html=True)

def metric_cards(st_module, metrics: Sequence[Mapping[str, Any] | MetricView]) -> None:
    cards=[]
    for item in metrics:
        view=item if isinstance(item,MetricView) else MetricView(str(item.get("label") or ""),str(item.get("value") or "-"),str(item.get("delta") or ""),str(item.get("tone") or "neutral"))
        cards.append(f'<article class="aa-ui-metric-card tone-{_esc(view.tone)}"><div class="aa-ui-kpi-label">{_esc(view.label)}</div><div class="aa-ui-kpi-value">{_esc(view.value)}</div><div class="aa-ui-kpi-delta">{_esc(view.delta)}</div></article>')
    st_module.markdown(f'<div class="aa-ui-metric-grid">{"".join(cards)}</div>',unsafe_allow_html=True)

def decision_cards(st_module, rows: Sequence[Mapping[str, Any] | DecisionView]) -> None:
    views=[row if isinstance(row,DecisionView) else DecisionView.from_mapping(row) for row in rows]
    cards=[f'<article class="aa-ui-decision-card tone-{_esc(v.tone)}" aria-label="{_esc(v.action)} {_esc(v.ticker)}"><div class="aa-ui-decision-action">{_esc(v.action)}</div><div class="aa-ui-decision-ticker">{_esc(v.ticker)}</div><p>{_esc(v.reason)}</p></article>' for v in views]
    st_module.markdown(f'<div class="aa-ui-decision-grid">{"".join(cards)}</div>',unsafe_allow_html=True)

def timeline(st_module, rows: Sequence[TimelineStepView]) -> None:
    items=[]
    for v in rows:
        details=" · ".join(f"{_esc(k)}: {_esc(val)}" for k,val in v.details.items())
        items.append(f'<article class="aa-ui-timeline-step tone-{_esc(v.tone)}"><b>{_esc(v.label)}</b> <span>{_esc(v.status)}</span><div>{_esc(v.scheduled_at)}</div><small>{details}</small></article>')
    st_module.markdown(f'<div class="aa-ui-timeline">{"".join(items)}</div>',unsafe_allow_html=True)

def page_state(st_module, view: PageStateView) -> None:
    tone={"ERROR":"danger","BLOCKED":"danger","STALE":"warning","PARTIAL":"warning","READY":"success"}.get(view.state,"neutral")
    st_module.markdown(f'<section class="aa-ui-page-state aa-ui-ambient tone-{tone}" role="status"><b>{_esc(view.state)}</b><p>{_esc(view.message)}</p><small>{_esc(view.code)}</small></section>',unsafe_allow_html=True)

def ambient_panel(st_module, title: str, body: str, *, module: str = "overview") -> None:
    st_module.markdown(f'<aside class="aa-ui-ambient aa-module-{_esc(module)}"><b>{_esc(title)}</b><p>{_esc(body)}</p></aside>',unsafe_allow_html=True)

def action_bar(st_module, actions: Sequence[Mapping[str, Any] | ActionView]) -> dict[str,bool]:
    normalized=[]
    for a in actions:
        if isinstance(a,ActionView): normalized.append({"id":a.action_id,"label":a.label,"disabled":a.disabled,"help":a.help_text,"type":"primary" if a.tone in {"success","portfolio","market"} else "secondary"})
        else: normalized.append(a)
    return action_row(st_module,normalized)

def render_job_status(st_module, view: JobStatusView, controls: Mapping[str, Callable[[], Any]] | None = None) -> str | None:
    percent=max(0,min(100,int(view.percent or 0)))
    st_module.progress(percent,text=view.message or view.label or view.state)
    metric_cards(st_module,[{"label":"Jobb-ID","value":view.job_id or "-"},{"label":"Tilstand","value":view.state},{"label":"Fase","value":view.phase or "-"},{"label":"Fremdrift","value":f"{percent}%"}])
    controls=controls or {}; selected=None
    specs=(("pause","Pause",view.can_pause),("resume","Fortsett",view.can_resume),("stop","Stopp",view.can_stop))
    if any(enabled and key in controls for key,_,enabled in specs):
        cols=st_module.columns(3)
        for col,(key,label,enabled) in zip(cols,specs):
            if enabled and key in controls and col.button(label,key=f"aa_job_{key}_{view.job_id}",width="stretch"):
                controls[key](); selected=key
    return selected
