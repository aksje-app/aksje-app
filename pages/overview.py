"""Renderer-independent overview page model (v19.2.0)."""
from __future__ import annotations
from typing import Any, Iterable, Mapping
from daily_user_experience import build_attention_items

def build_overview_page(archive: Iterable[Mapping[str, Any]] | None, *, pending_approvals: int = 0, scheduler_ok: bool | None = None) -> dict[str, Any]:
    attention = build_attention_items(archive, pending_approvals=pending_approvals, scheduler_ok=scheduler_ok, max_items=7)
    priority = {"danger": 0, "critical": 0, "warning": 1, "info": 2, "success": 3, "ok": 3}
    normalized = []
    for item in attention:
        row = dict(item)
        severity = str(row.get("severity") or "info").lower()
        row["tone"] = "danger" if severity == "critical" else "success" if severity == "ok" else severity
        normalized.append(row)
    normalized.sort(key=lambda row: priority.get(str(row.get("tone")), 2))
    # An empty archive during a healthy scheduler bootstrap is an EMPTY state,
    # not an operational alarm. The report workspace still offers creation.
    if not list(archive or []) and scheduler_ok is True and pending_approvals == 0:
        normalized = []
    healthy = scheduler_ok is not False and pending_approvals == 0 and not any(row.get("tone") in {"danger", "warning"} for row in normalized)
    return {
        "page": "overview",
        "title": "Hva trenger oppmerksomhet nå?",
        "hero": {"title": "Systemet er klart" if healthy else "Noe trenger oppmerksomhet", "body": "Beslutninger og neste hendelse samlet på ett sted.", "tone": "success" if healthy else "warning"},
        "metrics": [{"label": "Ventende godkjenninger", "value": str(pending_approvals), "tone": "warning" if pending_approvals else "neutral"}, {"label": "Scheduler", "value": "OK" if scheduler_ok is not False else "Stoppet", "tone": "success" if scheduler_ok is not False else "danger"}],
        "attention_items": normalized,
        "recent_changes": list(archive or [])[:5],
        "next_event": {"label": "Neste planlagte rapport", "value": "Se rapporttidslinjen"},
        "actions": [
            {"label": "Kjør rapport", "nav": "reports"},
            {"label": "Åpne siste rapport", "nav": "reports"},
            {"label": "Se endringer", "nav": "reports"},
            {"label": "Behandle godkjenninger", "nav": "approvals"},
            {"label": "Åpne drift", "nav": "operations"},
        ],
    }

def render_overview(st_module, model: Mapping[str, Any]) -> None:
    from ui_library.components import action_bar, decision_cards, hero_status, metric_cards, page_state
    from ui_library.models import PageStateView
    hero = model.get("hero") or {}
    hero_status(st_module, title=str(hero.get("title") or model.get("title") or "Oversikt"), body=str(hero.get("body") or ""), module="overview", tone=str(hero.get("tone") or "neutral"))
    metric_cards(st_module, model.get("metrics") or [])
    attention = model.get("attention_items") or []
    if attention:
        decision_cards(st_module, [{"ticker": row.get("title") or "Oppgave", "decision": "REPLACE_REVIEW" if row.get("tone") == "warning" else "REJECTED" if row.get("tone") == "danger" else "HOLD", "reason": row.get("detail") or row.get("message") or "Se detaljer"} for row in attention])
    else:
        page_state(st_module, PageStateView.empty("Ingen oppgaver krever oppmerksomhet nå."))
    action_bar(st_module, [{"id": str(i), **dict(action)} for i, action in enumerate(model.get("actions") or [])])

def render_ab_overview(st_module, model: Mapping[str, Any], *, navigate) -> None:
    """Render the real A+B home workspace using persisted data only."""
    from html import escape
    hero = model.get("hero") or {}
    attention = list(model.get("attention_items") or [])
    metrics = list(model.get("metrics") or [])
    st_module.markdown(
        f'''<main class="aa-overview-v2" aria-label="Oversikt">
        <section class="aa-overview-hero tone-{escape(str(hero.get('tone') or 'neutral'))}">
          <div><span class="aa-overline">BESLUTNINGSOVERSIKT</span><h1>{escape(str(hero.get('title') or 'Oversikt'))}</h1>
          <p>{escape(str(hero.get('body') or ''))}</p></div>
          <div class="aa-next-event"><span>NESTE HENDELSE</span><strong>{escape(str((model.get('next_event') or {}).get('label') or '-'))}</strong><small>{escape(str((model.get('next_event') or {}).get('value') or ''))}</small></div>
        </section></main>''', unsafe_allow_html=True,
    )
    cols = st_module.columns(max(1, min(4, len(metrics))))
    for index, metric in enumerate(metrics):
        with cols[index % len(cols)]:
            st_module.markdown(f'''<article class="aa-overview-metric tone-{escape(str(metric.get('tone') or 'neutral'))}"><span>{escape(str(metric.get('label') or ''))}</span><strong>{escape(str(metric.get('value') or '-'))}</strong><small>{escape(str(metric.get('delta') or ''))}</small></article>''', unsafe_allow_html=True)
    left, right = st_module.columns([1.65, 1])
    with left:
        st_module.markdown('<h2 class="aa-section-title">Krever oppmerksomhet</h2>', unsafe_allow_html=True)
        if attention:
            for item in attention:
                tone = escape(str(item.get("tone") or "info"))
                st_module.markdown(f'''<article class="aa-attention-card tone-{tone}"><span class="aa-attention-dot"></span><div><strong>{escape(str(item.get('title') or 'Status'))}</strong><p>{escape(str(item.get('detail') or ''))}</p></div></article>''', unsafe_allow_html=True)
        else:
            st_module.markdown('<article class="aa-attention-card tone-success"><span class="aa-attention-dot"></span><div><strong>Ingen kritiske oppgaver</strong><p>Systemet har ingen registrerte handlinger som krever oppfølging nå.</p></div></article>', unsafe_allow_html=True)
    with right:
        st_module.markdown('<h2 class="aa-section-title">Hurtighandlinger</h2>', unsafe_allow_html=True)
        actions = [("Kjør eller åpne rapport", "reports", "aa_overview_reports"),("Åpne Super Portfolio", "portfolio", "aa_overview_portfolio"),("Se marked og kandidater", "long_engine", "aa_overview_market"),("Åpne drift", "operations", "aa_overview_operations")]
        for label, route, key in actions:
            if st_module.button(label, key=key, width="stretch", type="primary" if route == "reports" else "secondary"):
                navigate(route); st_module.rerun()
        st_module.caption("Handlingene åpner eksisterende arbeidsflater og starter ingen analyse automatisk.")
