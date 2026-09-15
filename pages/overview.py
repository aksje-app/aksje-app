"""Renderer-independent overview page model (v19.2.0)."""
from __future__ import annotations
from datetime import datetime
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo
from daily_user_experience import build_attention_items

def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _portfolio_summary(state: Mapping[str, Any] | None) -> dict[str, Any]:
    state = dict(state or {})
    positions = [dict(row) for row in (state.get("positions") or {}).values() if isinstance(row, Mapping)]
    cash = _number(state.get("cash"))
    initial = _number(state.get("initial_cash"))
    target_weight = sum(_number(row.get("target_weight_pct") or row.get("weight_pct")) for row in positions)
    weighted_return = (
        sum(_number(row.get("pnl_pct") or row.get("return_pct")) * _number(row.get("target_weight_pct") or row.get("weight_pct")) for row in positions) / target_weight
        if target_weight > 0 else None
    )
    priced_positions = [row for row in positions if _number(row.get("quantity") or row.get("shares")) > 0 and _number(row.get("last_price") or row.get("current_price")) > 0]
    market_value = sum(_number(row.get("quantity") or row.get("shares")) * _number(row.get("last_price") or row.get("current_price")) for row in priced_positions)
    if positions and target_weight > 0 and initial > 0:
        since_start = round(float(weighted_return or 0), 4)
        total = initial * (1 + since_start / 100)
        cash_pct = max(0.0, min(100.0, 100.0 - target_weight))
    elif not positions and initial > 0:
        total, since_start, cash_pct = cash or initial, 0.0, 100.0
    elif len(priced_positions) == len(positions) and positions and cash + market_value > 0:
        total = cash + market_value
        since_start = round(((total / initial) - 1) * 100, 4) if initial > 0 else None
        cash_pct = cash / total * 100
    else:
        total, since_start, cash_pct = None, None, None
    confidence = state.get("decision_confidence") if isinstance(state.get("decision_confidence"), Mapping) else {}
    decisions = []
    for change in list(state.get("last_changes") or [])[:3]:
        if not isinstance(change, Mapping):
            continue
        decisions.append({
            "ticker": str(change.get("ticker") or change.get("symbol") or "-").upper(),
            "action": str(change.get("action") or change.get("decision") or change.get("type") or "VURDER").upper(),
            "reason": str(change.get("reason") or change.get("message") or "Se siste porteføljevurdering"),
            "score": change.get("score") or change.get("confidence"),
            "return_pct": change.get("pnl_pct") or change.get("return_pct"),
        })
    return {"value": total if total and total > 0 else None, "return_pct": since_start, "positions": len(positions), "cash_pct": cash_pct, "confidence": confidence.get("score"), "decisions": decisions}


def _next_report_time(now: datetime | None = None) -> str:
    local = now or datetime.now(ZoneInfo("Europe/Oslo"))
    for hour in (8, 22):
        if (local.hour, local.minute) < (hour, 0):
            return f"{hour:02d}:00"
    return "08:00 i morgen"


def build_overview_page(archive: Iterable[Mapping[str, Any]] | None, *, pending_approvals: int = 0, scheduler_ok: bool | None = None, portfolio_state: Mapping[str, Any] | None = None) -> dict[str, Any]:
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
        "next_event": {"label": "Neste planlagte rapport", "value": _next_report_time()},
        "portfolio": _portfolio_summary(portfolio_state),
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
    portfolio = dict(model.get("portfolio") or {})
    if portfolio.get("value") is None:
        try:
            from super_portfolio import load_state
            portfolio = _portfolio_summary(load_state())
        except Exception:
            pass
    def fmt_money(value):
        return f"{float(value):,.0f} kr".replace(",", " ") if value is not None else "Ikke tilgjengelig"
    def fmt_pct(value):
        return f"{float(value):+.2f} %".replace(".", ",") if value is not None else "Ikke tilgjengelig"
    confidence = portfolio.get("confidence")
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
    st_module.markdown(f'''<section class="aa-portfolio-command">
      <article class="aa-portfolio-value"><span>SUPER PORTEFØLJE</span><strong>{escape(fmt_money(portfolio.get('value')))}</strong><b>{escape(fmt_pct(portfolio.get('return_pct')))} <small>siden start</small></b><div class="aa-return-line" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i><i></i></div></article>
      <article class="aa-confidence"><span>BESLUTNINGSRO</span><strong>{escape(str(round(float(confidence)))) if confidence is not None else '–'}</strong><small>{'HØY TILLIT' if confidence is not None and float(confidence) >= 75 else 'SE BESLUTNINGSGRUNNLAG' if confidence is not None else 'IKKE BEREGNET'}</small></article>
      <div class="aa-aurora" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i></div>
    </section>
    <section class="aa-portfolio-facts"><div><strong>{portfolio.get('positions', 0)}</strong><span>POSISJONER</span></div><div><strong>{escape(fmt_pct(portfolio.get('cash_pct')).replace('+',''))}</strong><span>KONTANTER</span></div><div><strong>{escape(str((model.get('next_event') or {}).get('value') or '–'))}</strong><span>NESTE RAPPORT</span></div></section>''', unsafe_allow_html=True)
    left, right = st_module.columns([1.65, 1])
    with left:
        st_module.markdown('<h2 class="aa-section-title">Krever oppmerksomhet</h2>', unsafe_allow_html=True)
        if attention:
            for item in attention:
                tone = escape(str(item.get("tone") or "info"))
                st_module.markdown(f'''<article class="aa-attention-card tone-{tone}"><span class="aa-attention-dot"></span><div><strong>{escape(str(item.get('title') or 'Status'))}</strong><p>{escape(str(item.get('detail') or ''))}</p></div></article>''', unsafe_allow_html=True)
        else:
            st_module.markdown('<article class="aa-attention-card tone-success"><span class="aa-attention-dot"></span><div><strong>Ingen kritiske oppgaver</strong><p>Systemet har ingen registrerte handlinger som krever oppfølging nå.</p></div></article>', unsafe_allow_html=True)
        st_module.markdown('<h2 class="aa-section-title aa-decisions-title">Dagens beslutninger</h2>', unsafe_allow_html=True)
        decisions = list(portfolio.get("decisions") or [])
        if decisions:
            for row in decisions:
                action = str(row.get("action") or "VURDER").upper()
                tone = "success" if action in {"BUY", "KJØP", "ADD"} else "danger" if action in {"SELL", "SELG", "EXIT"} else "warning"
                score = f"AI {row.get('score')}" if row.get("score") is not None else ""
                ret = fmt_pct(row.get("return_pct")) if row.get("return_pct") is not None else ""
                st_module.markdown(f'''<article class="aa-decision-row tone-{tone}"><div><strong>{escape(str(row.get('ticker') or '-'))}</strong><small>{escape(str(row.get('reason') or ''))}</small></div><div><b>{escape(score)}</b><em>{escape(ret)}</em></div><span>{escape(action)}</span></article>''', unsafe_allow_html=True)
        else:
            st_module.markdown('<article class="aa-empty-decisions"><strong>Ingen nye porteføljebeslutninger</strong><p>Nye kjøp, salg og vurderinger vises her etter neste verifiserte Super Portfolio-kjøring.</p></article>', unsafe_allow_html=True)
    with right:
        st_module.markdown('<h2 class="aa-section-title">Hurtighandlinger</h2>', unsafe_allow_html=True)
        actions = [("Kjør eller åpne rapport", "reports", "aa_overview_reports"),("Åpne Super Portfolio", "portfolio", "aa_overview_portfolio"),("Se marked og kandidater", "long_engine", "aa_overview_market"),("Åpne drift", "operations", "aa_overview_operations")]
        for label, route, key in actions:
            if st_module.button(label, key=key, width="stretch", type="primary" if route == "reports" else "secondary"):
                navigate(route); st_module.rerun()
        st_module.caption("Handlingene åpner eksisterende arbeidsflater og starter ingen analyse automatisk.")
