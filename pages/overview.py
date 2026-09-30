"""Renderer-independent overview page model (v19.2.0)."""
from __future__ import annotations
from datetime import datetime
from html import escape
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo
from daily_user_experience import build_attention_items

def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _portfolio_summary(state: Mapping[str, Any] | None) -> dict[str, Any]:
    """Build Start-page portfolio facts from the authoritative Super Portfolio NAV."""
    state = dict(state or {})
    positions = [dict(row) for row in (state.get("positions") or {}).values() if isinstance(row, Mapping)]
    initial = _number(state.get("initial_cash"))
    target_weight = sum(_number(row.get("target_weight_pct") or row.get("weight_pct")) for row in positions)

    nav_value = _number(state.get("portfolio_value"))
    nav_return_raw = state.get("portfolio_return_pct")
    if nav_value > 0 and initial > 0:
        total = nav_value
        since_start = (
            round(_number(nav_return_raw), 4)
            if nav_return_raw is not None
            else round(((nav_value / initial) - 1.0) * 100.0, 4)
        )
    elif initial > 0:
        # Legacy state before NAV tracking: show a conservative start value,
        # never reconstruct realised performance from only current holdings.
        total = initial
        since_start = 0.0
    else:
        total = None
        since_start = None

    vacancy = state.get("vacancy_diagnostics") if isinstance(state.get("vacancy_diagnostics"), Mapping) else {}
    if vacancy.get("cash_pct") is not None:
        cash_pct = max(0.0, min(100.0, _number(vacancy.get("cash_pct"))))
    else:
        cash_pct = max(0.0, min(100.0, 100.0 - target_weight)) if positions else 100.0

    confidence = state.get("decision_confidence") if isinstance(state.get("decision_confidence"), Mapping) else {}
    health = state.get("portfolio_health") if isinstance(state.get("portfolio_health"), Mapping) else {}
    health_components = health.get("components") if isinstance(health.get("components"), Mapping) else {}
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

    history_returns: list[float] = []
    history_labels: list[str] = []
    latest_measurement_at = str(state.get("updated_at") or state.get("last_evaluated_at") or "")
    for snapshot in list(state.get("history") or [])[-12:]:
        if not isinstance(snapshot, Mapping) or snapshot.get("portfolio_return_pct") is None:
            continue
        history_returns.append(round(_number(snapshot.get("portfolio_return_pct")), 4))
        raw_at = str(snapshot.get("at") or snapshot.get("created_at") or "")
        if raw_at:
            latest_measurement_at = raw_at
        try:
            parsed_at = datetime.fromisoformat(raw_at.replace("Z", "+00:00"))
            history_labels.append(parsed_at.strftime("%d.%m"))
        except (TypeError, ValueError):
            history_labels.append("")

    if since_start is not None and (not history_returns or history_returns[-1] != since_start):
        history_returns.append(since_start)
        try:
            latest = datetime.fromisoformat(latest_measurement_at.replace("Z", "+00:00"))
            history_labels.append(latest.astimezone(ZoneInfo("Europe/Oslo")).strftime("%d.%m"))
        except (TypeError, ValueError):
            history_labels.append("Siste")

    updated_label = "Ikke tilgjengelig"
    try:
        latest = datetime.fromisoformat(latest_measurement_at.replace("Z", "+00:00"))
        updated_label = latest.astimezone(ZoneInfo("Europe/Oslo")).strftime("%d.%m kl. %H:%M")
    except (TypeError, ValueError):
        pass

    position_rows: list[dict[str, Any]] = []
    for row in positions:
        ticker = str(row.get("ticker") or row.get("symbol") or "-").upper()
        weight = _number(row.get("target_weight_pct") or row.get("weight_pct"))
        pnl_pct = _number(row.get("pnl_pct") or row.get("return_pct"))
        market_value = _number(row.get("market_value") or row.get("value_nok") or row.get("position_value"))
        if market_value <= 0 and total and weight > 0:
            market_value = _number(total) * weight / 100.0
        pnl_nok_raw = row.get("pnl_nok") or row.get("profit_nok")
        pnl_nok = _number(pnl_nok_raw) if pnl_nok_raw is not None else market_value * pnl_pct / 100.0
        distance_to_stop = row.get("distance_to_hard_stop_pct")
        stop_pressure = str(row.get("stop_pressure") or row.get("stop_status") or "").strip().upper()
        action = str(row.get("action") or row.get("recommended_action") or "HOLD").strip().upper()
        position_rows.append({
            "ticker": ticker,
            "weight_pct": round(weight, 2),
            "value_nok": round(market_value, 0) if market_value > 0 else None,
            "pnl_nok": round(pnl_nok, 0),
            "pnl_pct": round(pnl_pct, 2),
            "distance_to_stop_pct": round(_number(distance_to_stop), 2) if distance_to_stop is not None else None,
            "status": stop_pressure or "OK",
            "action": action,
        })
    position_rows.sort(key=lambda row: (_number(row.get("weight_pct")), _number(row.get("value_nok"))), reverse=True)

    return {
        "value": total if total and total > 0 else None,
        "return_pct": since_start,
        "positions": len(positions),
        "position_rows": position_rows,
        "cash_pct": cash_pct,
        "confidence": confidence.get("score"),
        "health_components": dict(health_components),
        "decisions": decisions,
        "history_returns": history_returns[-12:],
        "history_labels": history_labels[-12:],
        "last_updated": updated_label,
    }

def _sparkline_svg(values: Iterable[Any], labels: Iterable[str] | None = None) -> str:
    points = [_number(value) for value in values]
    if len(points) < 2:
        return '<div class="aa-chart-empty">Avkastningshistorikk kommer etter flere kjøringer</div>'
    # Keep zero at the visual centre and enforce a minimum ±1% range so tiny
    # moves cannot look like severe swings.
    scale = max(1.0, max(abs(value) for value in points) * 1.15)
    low, high = -scale, scale
    spread = high - low
    chart_top, chart_bottom = 18.0, 76.0
    zero_y = chart_bottom - ((0.0 - low) / spread) * (chart_bottom - chart_top)
    coords: list[tuple[float, float]] = []
    for index, value in enumerate(points):
        x = 8 + index * (484 / max(1, len(points) - 1))
        y = chart_bottom - ((value - low) / spread) * (chart_bottom - chart_top)
        coords.append((x, y))
    curve = f"M {coords[0][0]:.1f} {coords[0][1]:.1f}"
    for previous, current in zip(coords, coords[1:]):
        middle = (previous[0] + current[0]) / 2
        curve += f" C {middle:.1f} {previous[1]:.1f}, {middle:.1f} {current[1]:.1f}, {current[0]:.1f} {current[1]:.1f}"
    area = f"{curve} L {coords[-1][0]:.1f} {zero_y:.1f} L {coords[0][0]:.1f} {zero_y:.1f} Z"
    last_x, last_y = coords[-1]
    axis_labels = list(labels or [])
    first_label = axis_labels[0] if axis_labels and axis_labels[0] else "Eldst"
    last_label = axis_labels[-1] if axis_labels and axis_labels[-1] else "Siste"
    return f'''<div class="aa-chart-wrap"><span>AVKASTNINGSHISTORIKK</span><div class="aa-axis-y"><b>+{scale:.1f}%</b><b>0%</b><b>−{scale:.1f}%</b></div><svg class="aa-return-chart" width="100%" height="78" viewBox="0 0 500 92" preserveAspectRatio="none" role="img" aria-label="Avkastningsutvikling"><defs><linearGradient id="aaReturnFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#55d5ba" stop-opacity=".18"/><stop offset="1" stop-color="#55d5ba" stop-opacity="0"/></linearGradient></defs><line class="aa-chart-baseline" x1="8" y1="{zero_y:.1f}" x2="492" y2="{zero_y:.1f}"/><path class="aa-chart-area" d="{area}"/><path class="aa-chart-line" d="{curve}"/><circle class="aa-chart-end" cx="{last_x:.1f}" cy="{last_y:.1f}" r="4"/></svg><div class="aa-axis-x"><b>Fra {escape(first_label)}</b><b>Til {escape(last_label)}</b></div></div>'''


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
    hero = model.get("hero") or {}
    attention = list(model.get("attention_items") or [])
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
    components = dict(portfolio.get("health_components") or {})
    component_rows = []
    for label, key in (("Kvalitet", "quality"), ("Risiko", "risk"), ("Diversifisering", "diversification"), ("Stoppsikkerhet", "stop_safety")):
        if components.get(key) is not None:
            component_rows.append(f'<div><span>{label}</span><strong>{_number(components.get(key)):.0f}</strong></div>')
    component_html = "".join(component_rows) or '<p class="aa-confidence-empty">Detaljmål beregnes ved neste porteføljevurdering.</p>'
    local_hour = datetime.now(ZoneInfo("Europe/Oslo")).hour
    greeting = "God morgen" if local_hour < 12 else "God ettermiddag" if local_hour < 18 else "God kveld"
    chart = _sparkline_svg(portfolio.get("history_returns") or [], portfolio.get("history_labels") or [])
    try:
        from quality_v2_shadow_store import load_shadow_state
        v2_shadow = load_shadow_state()
        # Migration-safe current snapshot: older persisted shadow state used
        # cumulative counters. Prefer the latest actual Quality run immediately,
        # so 3 repeats of the same 8 disagreements still display 8, not 24.
        try:
            from quality_valuation_store import load_latest
            latest_quality = load_latest()
            latest_shadow = latest_quality.get("quality_v2_shadow") if isinstance(latest_quality, Mapping) else {}
            if isinstance(latest_shadow, Mapping) and latest_shadow.get("shadow_only"):
                classification_available = bool(
                    latest_shadow.get("classification_available",
                                      "v2_weaker_count" in latest_shadow and "v2_stronger_count" in latest_shadow)
                )
                v2_shadow = {
                    **v2_shadow,
                    "evaluated_companies": int(latest_shadow.get("evaluated") or 0),
                    "disagreement_count": int(latest_shadow.get("disagreement_count") or 0),
                    "weakening_count": int(latest_shadow.get("weakening_count") or 0),
                    "classification_available": classification_available,
                }
                if classification_available:
                    v2_shadow.update({
                        "v2_weaker_count": int(latest_shadow.get("v2_weaker_count") or 0),
                        "v2_stronger_count": int(latest_shadow.get("v2_stronger_count") or 0),
                        "v2_weaker_tickers": list(latest_shadow.get("v2_weaker_tickers") or []),
                        "v2_stronger_tickers": list(latest_shadow.get("v2_stronger_tickers") or []),
                        "v2_weaker_details": list(latest_shadow.get("v2_weaker_details") or []),
                        "v2_stronger_details": list(latest_shadow.get("v2_stronger_details") or []),
                        "classification_schema": str(latest_shadow.get("classification_schema") or ""),
                        "model_version": str(latest_shadow.get("model_version") or ""),
                        "comparison_complete": bool(latest_shadow.get("comparison_complete", False)),
                    })
        except Exception:
            pass
    except Exception:
        v2_shadow = {}
    st_module.markdown(
        f'''<main class="aa-overview-v2" aria-label="Oversikt">
        <section class="aa-overview-hero tone-{escape(str(hero.get('tone') or 'neutral'))}">
          <div><span class="aa-overline">BESLUTNINGSOVERSIKT · INVESTOR INTELLIGENCE</span><h1>{greeting}</h1>
          <p>{'Systemet har oppgaver som bør vurderes.' if attention else 'Systemet er oppdatert. Ingen kritiske oppgaver er registrert.'}</p><b class="aa-market-pill">OSLO · NESTE RAPPORT {escape(str((model.get('next_event') or {}).get('value') or '–'))}</b></div>
          <div class="aa-system-chip"><i></i>{'SYSTEMET ER KLART' if str(hero.get('tone')) == 'success' else 'KREVER OPPMERKSOMHET'}</div>
        </section></main>''', unsafe_allow_html=True,
    )
    if v2_shadow:
        runs = int(v2_shadow.get("complete_runs") or 0)
        evaluated = int(v2_shadow.get("evaluated_companies") or 0)
        disagreements = int(v2_shadow.get("disagreement_count") or 0)
        weakening = int(v2_shadow.get("weakening_count") or 0)
        classification_available = bool(v2_shadow.get("classification_available", False))
        v2_weaker = int(v2_shadow.get("v2_weaker_count") or 0) if classification_available else 0
        v2_stronger = int(v2_shadow.get("v2_stronger_count") or 0) if classification_available else 0
        weaker_tickers = [str(value).strip().upper() for value in (v2_shadow.get("v2_weaker_tickers") or []) if str(value).strip()] if classification_available else []
        stronger_tickers = [str(value).strip().upper() for value in (v2_shadow.get("v2_stronger_tickers") or []) if str(value).strip()] if classification_available else []
        weaker_unique = list(dict.fromkeys(weaker_tickers))
        stronger_unique = list(dict.fromkeys(stronger_tickers))
        ticker_overlap = sorted(set(weaker_unique) & set(stronger_unique))
        comparison_complete = bool(
            classification_available
            and v2_shadow.get("comparison_complete", False)
            and disagreements == v2_weaker + v2_stronger
            and disagreements == len(weaker_unique) + len(stronger_unique)
            and not ticker_overlap
        )
        unclassified = max(0, disagreements - len(weaker_unique) - len(stronger_unique)) if classification_available else disagreements
        history_comparable = bool(v2_shadow.get("comparison_available", False))
        new_tickers = [str(value) for value in (v2_shadow.get("new_disagreement_tickers") or []) if str(value)] if history_comparable else []
        resolved_tickers = [str(value) for value in (v2_shadow.get("resolved_disagreement_tickers") or []) if str(value)] if history_comparable else []
        unchanged_tickers = [str(value) for value in (v2_shadow.get("unchanged_disagreement_tickers") or []) if str(value)] if history_comparable else []
        weaker_details = [dict(value) for value in (v2_shadow.get("v2_weaker_details") or []) if isinstance(value, Mapping)]
        stronger_details = [dict(value) for value in (v2_shadow.get("v2_stronger_details") or []) if isinstance(value, Mapping)]
        next_point = v2_shadow.get("next_milestone")
        decision_required = bool(v2_shadow.get("decision_required"))
        status_label = "BESLUTNING KREVES" if decision_required else "SHADOW - INGEN PRODUKSJONSEFFEKT"
        next_label = "Beslutning kreves nå" if decision_required else f"Neste milepæl: {next_point or '-'} komplette kjøringer"

        if not classification_available or not comparison_complete:
            consistency_note = (
                f"{unclassified} aktive uenigheter er ikke komplett klassifisert. "
                "Tallene holdes tilbake til en komplett kvalitetskjøring foreligger."
            )
        elif not history_comparable:
            consistency_note = "Ingen sammenlignbar tidligere klassifisering"
        else:
            consistency_note = (
                f"{len(new_tickers)} nye · {len(resolved_tickers)} løst · "
                f"{len(unchanged_tickers)} uendret siden forrige sammenlignbare kjøring"
            )

        weaker_class = "tone-danger" if v2_weaker > 0 else "tone-neutral"
        stronger_class = "tone-success" if v2_stronger > 0 else "tone-neutral"

        if comparison_complete:
            classification_cells = (
                f'<span class="{weaker_class}"><b>{v2_weaker}</b><small>V2 SVAKERE</small></span>'
                f'<span class="{stronger_class}"><b>{v2_stronger}</b><small>V2 STERKERE</small></span>'
            )
        else:
            classification_cells = (
                f'<span class="tone-neutral aa-v2-unclassified"><b>{unclassified}</b>'
                '<small>IKKE KOMPLETT KLASSIFISERT</small></span>'
            )

        st_module.markdown(f'''<section class="aa-v2-shadow-card">
          <div><span class="aa-overline">QUALITY V2 · SHADOW</span><h3>{escape(status_label)}</h3><p>{escape(next_label)}</p><p class="aa-v2-comparison-note">{escape(consistency_note)}</p></div>
          <div class="aa-v2-shadow-facts"><span><b>{runs}</b><small>KOMPLETTE KJØRINGER</small></span><span><b>{evaluated}</b><small>VURDERT I SISTE KJØRING</small></span><span class="tone-watch"><b>{disagreements}</b><small>UENIGHETER NÅ</small></span>{classification_cells}</div>
        </section>''', unsafe_allow_html=True)

        def _detail_rows(details, tickers, direction_label):
            by_ticker = {
                str(row.get("ticker") or "").strip().upper(): str(row.get("reason") or "").strip()
                for row in details if str(row.get("ticker") or "").strip()
            }
            rows = []
            for ticker in tickers:
                reason = by_ticker.get(ticker) or (
                    f"V2 gir en {direction_label.lower()} kvalitetsvurdering enn aktiv modell."
                )
                rows.append(
                    f'<div class="aa-v2-detail-row"><strong>{escape(ticker)}</strong>'
                    f'<span>{escape(reason)}</span></div>'
                )
            return "".join(rows) or '<div class="aa-v2-empty">Ingen</div>'

        with st_module.expander("Vis hvilke aksjer V1.1 og V2 er uenige om", expanded=False):
            if comparison_complete:
                weaker_rows = _detail_rows(weaker_details, weaker_unique, "svakere")
                stronger_rows = _detail_rows(stronger_details, stronger_unique, "sterkere")
                history_html = (
                    f'<div class="aa-v2-history"><strong>Endring siden forrige sammenlignbare kjøring</strong>'
                    f'<span>Nye: {len(new_tickers)}</span><span>Løst: {len(resolved_tickers)}</span>'
                    f'<span>Uendret: {len(unchanged_tickers)}</span></div>'
                    if history_comparable
                    else '<div class="aa-v2-history tone-neutral"><strong>Historisk sammenligning</strong><span>Ingen sammenlignbar tidligere klassifisering.</span></div>'
                )
                st_module.markdown(
                    f'''<section class="aa-v2-detail-panel">
                    <div class="aa-v2-direction"><h4>V2 svakere ({v2_weaker})</h4><p>V2 gir en svakere kvalitetsvurdering enn aktiv modell.</p>{weaker_rows}</div>
                    <div class="aa-v2-direction"><h4>V2 sterkere ({v2_stronger})</h4><p>V2 gir en sterkere kvalitetsvurdering enn aktiv modell. Dette betyr ikke i seg selv at aksjen er en bedre investering.</p>{stronger_rows}</div>
                    {history_html}
                    </section>''',
                    unsafe_allow_html=True,
                )
            else:
                st_module.warning(
                    f"{unclassified} uenigheter mangler komplett og entydig svakere/sterkere-klassifisering. "
                    "Panelet viser derfor ikke historiske nye/løste tall."
                )
            if weakening:
                st_module.markdown(
                    f'''<section class="aa-v2-technical">
                    <strong>Teknisk trend</strong>
                    <p>{weakening} selskaper har svekkende kapitalavkastning. Dette er et eget mål og er ikke det samme som V2 svakere enn aktiv modell.</p>
                    </section>''',
                    unsafe_allow_html=True,
                )
    else:
        st_module.caption("Quality V2 Shadow: ingen komplette evalueringskjøringer registrert ennå.")


    if st_module.button("▶ Kjør kvalitetsvurdering", key="aa_overview_quality_top", width="stretch", type="primary"):
        navigate("quality_valuation"); st_module.rerun()

    st_module.markdown(f'''<section class="aa-portfolio-command">
      <article class="aa-portfolio-value"><span>SUPER PORTEFØLJE</span><p>Shadow-porteføljens beregnede verdi og vektede utvikling.</p><p><small>Sist oppdatert: {escape(str(portfolio.get('last_updated') or 'Ikke tilgjengelig'))}</small></p><strong>{escape(fmt_money(portfolio.get('value')))}</strong><b>{escape(fmt_pct(portfolio.get('return_pct')))} <small>siden start</small></b>{chart}</article>
      <article class="aa-confidence"><span>BESLUTNINGSRO</span><p>Samlet kvalitet på Super Portfolio sitt beslutningsgrunnlag.</p><strong>{escape(str(round(float(confidence)))) if confidence is not None else '–'}</strong><small>{'HØY TILLIT' if confidence is not None and float(confidence) >= 75 else 'SE BESLUTNINGSGRUNNLAG' if confidence is not None else 'IKKE BEREGNET'}</small><div class="aa-confidence-components">{component_html}</div></article>
    </section>
    <section class="aa-portfolio-facts"><div><strong>{portfolio.get('positions', 0)}</strong><span>POSISJONER</span></div><div><strong>{escape(fmt_pct(portfolio.get('cash_pct')).replace('+',''))}</strong><span>KONTANTER</span></div><div><strong>{escape(str((model.get('next_event') or {}).get('value') or '–'))}</strong><span>NESTE RAPPORT</span></div></section>''', unsafe_allow_html=True)

    position_rows = list(portfolio.get("position_rows") or [])
    if position_rows:
        st_module.markdown("### Porteføljen nå")
        quick_rows = []
        for row in position_rows:
            distance = row.get("distance_to_stop_pct")
            quick_rows.append({
                "Aksje": row.get("ticker") or "-",
                "Vekt %": row.get("weight_pct"),
                "Verdi NOK": row.get("value_nok"),
                "P/L NOK": row.get("pnl_nok"),
                "P/L %": row.get("pnl_pct"),
                "Til stop %": distance if distance is not None else None,
                "Status": row.get("status") or "OK",
            })
        try:
            import pandas as pd
            quick_df = pd.DataFrame(quick_rows)
            st_module.dataframe(
                quick_df,
                width="stretch",
                hide_index=True,
                height=min(430, 72 + 35 * max(1, len(quick_df))),
            )
        except Exception:
            st_module.write(quick_rows)

        best = max(position_rows, key=lambda row: _number(row.get("pnl_pct")))
        worst = min(position_rows, key=lambda row: _number(row.get("pnl_pct")))
        st_module.caption(
            f"Beste siden inngang: {best.get('ticker')} {fmt_pct(best.get('pnl_pct'))} · "
            f"Svakest siden inngang: {worst.get('ticker')} {fmt_pct(worst.get('pnl_pct'))}"
        )
    else:
        st_module.markdown('<div class="aa-empty-decisions"><strong>Ingen aktive Super Portfolio-posisjoner</strong><p>Porteføljeposisjoner vises her så snart lagret Super Portfolio-state inneholder aktive beholdninger.</p></div>', unsafe_allow_html=True)

    if st_module.button("🌍 Åpne hele Super Portfolio", key="aa_overview_open_super_portfolio_primary", width="stretch", type="primary"):
        navigate("super_portfolio")
        st_module.rerun()

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
        actions = [("Kjør kvalitetsvurdering", "quality_valuation", "aa_overview_quality"),("Kjør eller åpne rapport", "reports", "aa_overview_reports"),("Åpne Super Portfolio", "super_portfolio", "aa_overview_portfolio"),("Se marked og kandidater", "long_engine", "aa_overview_market"),("Åpne drift", "operations", "aa_overview_operations")]
        for label, route, key in actions:
            if st_module.button(label, key=key, width="stretch", type="primary" if route == "quality_valuation" else "secondary"):
                navigate(route); st_module.rerun()
        st_module.caption("Handlingene åpner eksisterende arbeidsflater og starter ingen analyse automatisk.")
