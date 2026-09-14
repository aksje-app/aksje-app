"""Super Portfolio intelligence v19.22.0 RC16.32b.

Isolated theoretical portfolio layer. Reuses completed Investment Pipeline data,
never submits real orders and never changes the authoritative Autonomy chain.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from io import BytesIO
from math import isfinite
from typing import Any, Mapping, Sequence

from durable_runtime import append_event, read_events, read_json, write_json
from storage_architecture import runtime_data_path, runtime_log_path

VERSION = "v19.22.0-rc16.32b"
STATE_KEY = "super_portfolio/state.json"
STATE_PATH = runtime_data_path("super_portfolio", "state.json")
AUDIT_KEY = "super_portfolio/audit.jsonl"
AUDIT_PATH = runtime_log_path("super_portfolio_audit.jsonl")
LATEST_PIPELINE_KEY = "investment_pipeline/latest_run.json"
LATEST_PIPELINE_PATH = runtime_data_path("investment_pipeline", "latest_run.json")


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _f(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if isfinite(number) else default
    except (TypeError, ValueError):
        return default


def _candidate_price(row: Mapping[str, Any]) -> float:
    raw = row.get("raw") if isinstance(row.get("raw"), Mapping) else {}
    for value in (row.get("price"), row.get("last_price"), raw.get("last_price"), raw.get("price")):
        price = _f(value)
        if price > 0:
            return price
    return 0.0


def _score(row: Mapping[str, Any]) -> float:
    for key in ("autonomy_adjusted_investment_score", "investment_score", "score", "final_score"):
        if row.get(key) is not None:
            return max(0.0, min(100.0, _f(row.get(key))))
    return 0.0


def _risk(row: Mapping[str, Any]) -> float:
    for key in ("risk_score", "portfolio_risk_score"):
        if row.get(key) is not None:
            return max(0.0, min(100.0, _f(row.get(key), 50.0)))
    return 50.0


def _quality(row: Mapping[str, Any]) -> float:
    for key in ("data_quality_score", "data_quality"):
        value = row.get(key)
        if isinstance(value, Mapping):
            value = value.get("score")
        if value is not None:
            return max(0.0, min(100.0, _f(value, 50.0)))
    return 50.0


@dataclass(frozen=True)
class SuperPortfolioConfig:
    target_positions: int = 10
    challenger_count: int = 5
    start_cash: float = 1_000_000.0
    minimum_score: float = 60.0
    maximum_risk: float = 75.0
    warning_drawdown_pct: float = 7.0
    near_stop_drawdown_pct: float = 10.0
    hard_stop_drawdown_pct: float = 15.0
    min_rebalance_pp: float = 1.0
    max_position_pct: float = 15.0
    concentration_soft_pct: float = 40.0
    sector_penalty_per_existing: float = 1.5
    correlation_soft_limit: float = 0.60
    correlation_penalty_scale: float = 8.0


def default_state(config: SuperPortfolioConfig | None = None) -> dict[str, Any]:
    cfg = config or SuperPortfolioConfig()
    return {
        "version": VERSION,
        "created_at": _now(),
        "updated_at": _now(),
        "status": "SHADOW",
        "initial_cash": cfg.start_cash,
        "cash": cfg.start_cash,
        "positions": {},
        "challengers": [],
        "history": [],
        "config": asdict(cfg),
        "source_run_id": "",
    }


def load_state() -> dict[str, Any]:
    value = read_json(STATE_KEY, STATE_PATH, {})
    return dict(value) if isinstance(value, Mapping) and value else default_state()


def save_state(state: Mapping[str, Any]) -> dict[str, Any]:
    value = dict(state)
    value["version"] = VERSION
    value["updated_at"] = _now()
    write_json(STATE_KEY, STATE_PATH, value)
    return value


def load_latest_pipeline() -> dict[str, Any]:
    value = read_json(LATEST_PIPELINE_KEY, LATEST_PIPELINE_PATH, {})
    return dict(value) if isinstance(value, Mapping) else {}


def rank_candidates(candidates: Sequence[Mapping[str, Any]], config: SuperPortfolioConfig | None = None) -> list[dict[str, Any]]:
    cfg = config or SuperPortfolioConfig()
    rows = []
    for source in candidates:
        row = dict(source)
        ticker = str(row.get("ticker") or row.get("symbol") or "").strip().upper()
        if not ticker:
            continue
        score, risk, quality = _score(row), _risk(row), _quality(row)
        price = _candidate_price(row)
        if score < cfg.minimum_score or risk > cfg.maximum_risk or price <= 0:
            continue
        # Portfolio score rewards investment score/quality and penalises risk.
        portfolio_score = 0.72 * score + 0.18 * quality + 0.10 * (100.0 - risk)
        rows.append({
            "ticker": ticker,
            "market": str(row.get("market") or row.get("country") or ""),
            "sector": str(row.get("sector") or "Ukjent"),
            "price": price,
            "investment_score": score,
            "risk_score": risk,
            "quality_score": quality,
            "portfolio_score": round(portfolio_score, 4),
            "raw_candidate": row,
        })
    rows.sort(key=lambda item: (-item["portfolio_score"], item["risk_score"], item["ticker"]))
    return rows


def apply_concentration_penalties(ranked: Sequence[Mapping[str, Any]], config: SuperPortfolioConfig | None = None) -> list[dict[str, Any]]:
    """Apply soft sector/correlation penalties without imposing hard quotas."""
    cfg = config or SuperPortfolioConfig()
    out: list[dict[str, Any]] = []
    sector_counts: dict[str, int] = {}
    selected_tickers: list[str] = []
    for source in ranked:
        row = dict(source)
        sector = str(row.get("sector") or "Ukjent")
        same_count = sector_counts.get(sector, 0)
        projected_pct = 100.0 * (same_count + 1) / max(1, cfg.target_positions)
        sector_penalty = 0.0 if same_count == 0 else cfg.sector_penalty_per_existing * same_count
        sector_penalty += max(0.0, projected_pct - cfg.concentration_soft_pct) * 0.08

        raw = row.get("raw_candidate") if isinstance(row.get("raw_candidate"), Mapping) else {}
        corr_map = raw.get("portfolio_correlations") if isinstance(raw.get("portfolio_correlations"), Mapping) else {}
        max_corr = 0.0
        for ticker in selected_tickers:
            max_corr = max(max_corr, abs(_f(corr_map.get(ticker), 0.0)))
        correlation_penalty = max(0.0, max_corr - cfg.correlation_soft_limit) * cfg.correlation_penalty_scale

        row["sector_penalty"] = round(sector_penalty, 4)
        row["correlation_penalty"] = round(correlation_penalty, 4)
        row["max_portfolio_correlation"] = round(max_corr, 4)
        row["portfolio_score_adjusted"] = round(max(0.0, _f(row.get("portfolio_score")) - sector_penalty - correlation_penalty), 4)
        out.append(row)
        sector_counts[sector] = same_count + 1
        selected_tickers.append(str(row.get("ticker") or ""))
    out.sort(key=lambda item: (-_f(item.get("portfolio_score_adjusted")), _f(item.get("risk_score"), 100.0), str(item.get("ticker") or "")))
    return out


def ranking_velocity(ticker: str, current_rank: int, history: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    ranks: list[int] = []
    key = str(ticker or "").upper()
    for snapshot in history:
        for row in snapshot.get("ranking") or []:
            if str(row.get("ticker") or "").upper() == key:
                try:
                    ranks.append(int(row.get("rank")))
                except (TypeError, ValueError):
                    pass
                break
    if not ranks:
        return {"rank_change": 0, "rank_velocity": 0.0, "rank_arrow": "→"}
    rank_change = ranks[0] - int(current_rank)
    velocity = rank_change / max(1, len(ranks))
    if rank_change >= 10:
        arrow = "↑↑↑"
    elif rank_change >= 4:
        arrow = "↑↑"
    elif rank_change > 0:
        arrow = "↑"
    elif rank_change <= -10:
        arrow = "↓↓↓"
    elif rank_change <= -4:
        arrow = "↓↓"
    elif rank_change < 0:
        arrow = "↓"
    else:
        arrow = "→"
    return {"rank_change": rank_change, "rank_velocity": round(velocity, 2), "rank_arrow": arrow}


def portfolio_health(positions: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    rows = list(positions)
    if not rows:
        return {"score": 0.0, "icon": "🔴", "label": "EMPTY", "components": {}}
    quality = sum(_f(p.get("portfolio_score_adjusted"), _f(p.get("portfolio_score"), 50.0)) for p in rows) / len(rows)
    risk = 100.0 - sum(_f(p.get("risk_score"), 50.0) for p in rows) / len(rows)
    sectors: dict[str, int] = {}
    for p in rows:
        sector = str(p.get("sector") or "Ukjent")
        sectors[sector] = sectors.get(sector, 0) + 1
    max_share = max(sectors.values()) / len(rows)
    diversification = max(0.0, min(100.0, 120.0 - max_share * 100.0))
    stop_map = {"SAFE": 100.0, "WATCH": 70.0, "NEAR STOP": 35.0, "STOP TRIGGERED": 0.0}
    stop_safety = sum(stop_map.get(str(p.get("stop_status") or "SAFE"), 60.0) for p in rows) / len(rows)
    score = max(0.0, min(100.0, 0.38 * quality + 0.24 * risk + 0.23 * diversification + 0.15 * stop_safety))
    if score >= 80:
        icon, label = "🟢", "STRONG"
    elif score >= 65:
        icon, label = "🟡", "OK"
    elif score >= 50:
        icon, label = "🟠", "WEAK"
    else:
        icon, label = "🔴", "RISK"
    return {"score": round(score, 1), "icon": icon, "label": label, "components": {"quality": round(quality,1), "risk": round(risk,1), "diversification": round(diversification,1), "stop_safety": round(stop_safety,1)}}


def stop_pressure(position: Mapping[str, Any], history: Sequence[Mapping[str, Any]], config: SuperPortfolioConfig | None = None) -> dict[str, Any]:
    cfg = config or SuperPortfolioConfig()
    ticker = str(position.get("ticker") or "").upper()
    current_distance = _f(position.get("distance_to_hard_stop_pct"), cfg.hard_stop_drawdown_pct)
    previous_distance = None
    for snapshot in reversed(list(history)):
        for row in snapshot.get("positions") or []:
            if str(row.get("ticker") or "").upper() == ticker:
                previous_distance = _f(row.get("distance_to_hard_stop_pct"), current_distance)
                break
        if previous_distance is not None:
            break
    change = 0.0 if previous_distance is None else current_distance - previous_distance
    if change < -1.5:
        arrow = "↓↓"
    elif change < -0.25:
        arrow = "↓"
    elif change > 1.5:
        arrow = "↑↑"
    elif change > 0.25:
        arrow = "↑"
    else:
        arrow = "→"
    if current_distance <= 1.5:
        pressure, icon = "CRITICAL", "🔴"
    elif current_distance <= 4.0 and change < 0:
        pressure, icon = "HIGH", "🟠"
    elif current_distance <= 7.0 or change <= -2.0:
        pressure, icon = "ELEVATED", "🟡"
    else:
        pressure, icon = "LOW", "🟢"
    return {"pressure": pressure, "pressure_icon": icon, "direction_arrow": arrow, "distance_change_pct": round(change, 2), "previous_distance_to_stop_pct": None if previous_distance is None else round(previous_distance, 2)}


def ai_would_do_today(positions: Mapping[str, Mapping[str, Any]], target: Mapping[str, float], min_rebalance_pp: float = 1.0) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    current = {str(k): dict(v) for k, v in positions.items()}
    for ticker, target_weight in target.items():
        old = current.get(str(ticker), {})
        old_weight = _f(old.get("target_weight_pct"))
        delta = _f(target_weight) - old_weight
        if not old:
            action = "BUY"
        elif abs(delta) < min_rebalance_pp:
            continue
        else:
            action = "ADD" if delta > 0 else "REDUCE"
        actions.append({"action": action, "ticker": str(ticker), "from_pct": round(old_weight,2), "to_pct": round(_f(target_weight),2), "delta_pct": round(delta,2), "advisory_only": True})
    for ticker, old in current.items():
        if ticker not in target:
            old_weight = _f(old.get("target_weight_pct"))
            actions.append({"action": "SELL", "ticker": ticker, "from_pct": round(old_weight,2), "to_pct": 0.0, "delta_pct": round(-old_weight,2), "advisory_only": True})
    action_order = {"SELL": 0, "REDUCE": 1, "BUY": 2, "ADD": 3}
    actions.sort(key=lambda row: (action_order.get(row["action"], 9), -abs(_f(row.get("delta_pct"))), row["ticker"]))
    return actions


def target_weights(ranked: Sequence[Mapping[str, Any]], config: SuperPortfolioConfig | None = None) -> dict[str, float]:
    cfg = config or SuperPortfolioConfig()
    selected = list(ranked)[: cfg.target_positions]
    if not selected:
        return {}
    # Risk-adjusted score weights, capped, then renormalised.
    raw = {}
    for row in selected:
        risk_factor = max(0.25, 1.0 - _f(row.get("risk_score"), 50.0) / 140.0)
        raw[str(row["ticker"])] = max(0.01, _f(row.get("portfolio_score_adjusted"), _f(row.get("portfolio_score"))) * risk_factor)
    total = sum(raw.values()) or 1.0
    weights = {ticker: 100.0 * value / total for ticker, value in raw.items()}
    # Iterative cap avoids one name dominating. Remaining weight is redistributed.
    for _ in range(5):
        over = {k: v for k, v in weights.items() if v > cfg.max_position_pct}
        if not over:
            break
        excess = sum(v - cfg.max_position_pct for v in over.values())
        for k in over:
            weights[k] = cfg.max_position_pct
        under = [k for k, v in weights.items() if v < cfg.max_position_pct - 1e-9]
        base = sum(weights[k] for k in under)
        if not under or base <= 0:
            break
        for k in under:
            weights[k] += excess * weights[k] / base
    norm = sum(weights.values()) or 1.0
    return {k: round(v * 100.0 / norm, 2) for k, v in weights.items()}


def _stop_status(position: Mapping[str, Any], config: SuperPortfolioConfig) -> dict[str, Any]:
    current = _f(position.get("last_price"))
    peak = max(_f(position.get("peak_price")), current)
    entry = _f(position.get("entry_price"))
    drawdown = ((current / peak) - 1.0) * 100.0 if peak > 0 and current > 0 else 0.0
    pnl = ((current / entry) - 1.0) * 100.0 if entry > 0 and current > 0 else 0.0
    dd_abs = abs(min(0.0, drawdown))
    if dd_abs >= config.hard_stop_drawdown_pct:
        label, icon = "STOP TRIGGERED", "🔴"
    elif dd_abs >= config.near_stop_drawdown_pct:
        label, icon = "NEAR STOP", "🟠"
    elif dd_abs >= config.warning_drawdown_pct:
        label, icon = "WATCH", "🟡"
    else:
        label, icon = "SAFE", "🟢"
    distance = max(0.0, config.hard_stop_drawdown_pct - dd_abs)
    return {"stop_status": label, "stop_icon": icon, "drawdown_from_peak_pct": round(drawdown, 2), "pnl_pct": round(pnl, 2), "distance_to_hard_stop_pct": round(distance, 2)}


def evaluate(*, pipeline: Mapping[str, Any] | None = None, persist: bool = True) -> dict[str, Any]:
    pipeline = dict(pipeline or load_latest_pipeline())
    state = load_state()
    config_data = state.get("config") if isinstance(state.get("config"), Mapping) else {}
    allowed = set(SuperPortfolioConfig.__dataclass_fields__)
    cfg = SuperPortfolioConfig(**{k: v for k, v in config_data.items() if k in allowed})
    base_ranked = rank_candidates(list(pipeline.get("candidates") or pipeline.get("proposals") or []), cfg)
    ranked = apply_concentration_penalties(base_ranked, cfg)
    history = list(state.get("history") or [])
    for index, row in enumerate(ranked, start=1):
        row["rank"] = index
        row.update(ranking_velocity(str(row.get("ticker") or ""), index, history))
    weights = target_weights(ranked, cfg)
    by_ticker = {row["ticker"]: row for row in ranked}
    previous = dict(state.get("positions") or {})
    advisory = ai_would_do_today(previous, weights, cfg.min_rebalance_pp)
    positions: dict[str, dict[str, Any]] = {}
    changes: list[dict[str, Any]] = []
    now = _now()
    for ticker, weight in weights.items():
        row = by_ticker[ticker]
        old = dict(previous.get(ticker) or {})
        entry_price = _f(old.get("entry_price")) or row["price"]
        entry_date = str(old.get("entry_date") or now)
        peak = max(_f(old.get("peak_price")), row["price"])
        pos = {
            "ticker": ticker, "market": row["market"], "sector": row["sector"],
            "entry_date": entry_date, "entry_price": entry_price, "last_price": row["price"], "peak_price": peak,
            "target_weight_pct": weight, "investment_score": row["investment_score"], "portfolio_score": row["portfolio_score"],
            "portfolio_score_adjusted": row.get("portfolio_score_adjusted", row["portfolio_score"]),
            "sector_penalty": row.get("sector_penalty", 0.0), "correlation_penalty": row.get("correlation_penalty", 0.0),
            "max_portfolio_correlation": row.get("max_portfolio_correlation", 0.0),
            "rank": row.get("rank"), "rank_change": row.get("rank_change", 0), "rank_velocity": row.get("rank_velocity", 0.0), "rank_arrow": row.get("rank_arrow", "→"),
            "risk_score": row["risk_score"], "quality_score": row["quality_score"],
        }
        pos.update(_stop_status(pos, cfg))
        pressure = stop_pressure(pos, history, cfg)
        pos.update({"stop_pressure": pressure["pressure"], "stop_pressure_icon": pressure["pressure_icon"], "stop_direction_arrow": pressure["direction_arrow"], "stop_distance_change_pct": pressure["distance_change_pct"]})
        positions[ticker] = pos
        old_weight = _f(old.get("target_weight_pct"))
        if not old:
            changes.append({"action": "BUY", "ticker": ticker, "from_pct": 0.0, "to_pct": weight})
        elif abs(weight - old_weight) >= cfg.min_rebalance_pp:
            changes.append({"action": "ADD" if weight > old_weight else "REDUCE", "ticker": ticker, "from_pct": old_weight, "to_pct": weight})
    for ticker, old in previous.items():
        if ticker not in positions:
            changes.append({"action": "SELL", "ticker": ticker, "from_pct": _f(old.get("target_weight_pct")), "to_pct": 0.0})
    challengers = ranked[cfg.target_positions: cfg.target_positions + cfg.challenger_count]
    health = portfolio_health(list(positions.values()))
    ranking_snapshot = [{"ticker": row.get("ticker"), "rank": row.get("rank"), "score": row.get("portfolio_score_adjusted"), "rank_arrow": row.get("rank_arrow")} for row in ranked[: max(cfg.target_positions + cfg.challenger_count, 30)]]
    snapshot = {
        "at": now,
        "source_run_id": str(pipeline.get("run_id") or pipeline.get("report_id") or ""),
        "positions": [{k: v for k, v in p.items() if k != "raw_candidate"} for p in positions.values()],
        "ranking": ranking_snapshot,
        "portfolio_health": health,
        "ai_would_do_today": advisory,
        "changes": changes,
    }
    state.update({
        "positions": positions,
        "challengers": [{k: v for k, v in row.items() if k != "raw_candidate"} for row in challengers],
        "source_run_id": snapshot["source_run_id"],
        "portfolio_health": health,
        "ai_would_do_today": advisory,
    })
    history.append(snapshot)
    state["history"] = history[-180:]
    if persist:
        save_state(state)
        append_event(AUDIT_KEY, AUDIT_PATH, {"timestamp": now, "event": "EVALUATE", "changes": changes, "portfolio_health": health, "source_run_id": snapshot["source_run_id"]})
    return {"state": state, "ranked": ranked, "changes": changes, "snapshot": snapshot, "portfolio_health": health, "ai_would_do_today": advisory}


def manual_exit(ticker: str, note: str = "") -> dict[str, Any]:
    state = load_state(); positions = dict(state.get("positions") or {})
    key = str(ticker or "").strip().upper()
    row = positions.pop(key, None)
    if not row:
        return {"ok": False, "reason": "Position not found"}
    event = {"timestamp": _now(), "event": "MANUAL_EXIT", "ticker": key, "price": row.get("last_price"), "pnl_pct": row.get("pnl_pct"), "note": str(note or "")}
    state["positions"] = positions
    state.setdefault("manual_exits", []).append(event)
    save_state(state); append_event(AUDIT_KEY, AUDIT_PATH, event)
    return {"ok": True, **event}


def build_pdf(state: Mapping[str, Any] | None = None) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib import colors
    data = dict(state or load_state())
    out = BytesIO(); doc = SimpleDocTemplate(out, pagesize=A4, rightMargin=12*mm, leftMargin=12*mm, topMargin=12*mm, bottomMargin=12*mm)
    styles = getSampleStyleSheet(); story = [Paragraph("AI Super Portfolio", styles["Title"]), Paragraph(f"{VERSION} · Shadow mode · {data.get('updated_at','-')}", styles["Normal"]), Spacer(1, 8)]
    health = data.get("portfolio_health") if isinstance(data.get("portfolio_health"), Mapping) else {}
    if health:
        story.append(Paragraph(f"Portfolio Health: {health.get('icon','')} {_f(health.get('score')):.1f}/100 · {health.get('label','-')}", styles["Heading2"]))
        components = health.get("components") if isinstance(health.get("components"), Mapping) else {}
        story.append(Paragraph(" · ".join(f"{k}: {_f(v):.1f}" for k, v in components.items()), styles["Normal"]))
        story.append(Spacer(1, 6))
    rows = [["Aksje", "Vekt", "Fra inn", "AI", "Rank", "Stop", "Press"]]
    for p in (data.get("positions") or {}).values():
        rows.append([p.get("ticker"), f"{_f(p.get('target_weight_pct')):.2f}%", f"{_f(p.get('pnl_pct')):+.2f}%", f"{_f(p.get('portfolio_score_adjusted'), _f(p.get('portfolio_score'))):.1f}", f"#{p.get('rank','-')} {p.get('rank_arrow','→')}", f"{p.get('stop_icon','')} {p.get('stop_status','')}", f"{p.get('stop_pressure_icon','')} {p.get('stop_pressure','-')} {p.get('stop_direction_arrow','→')}"])
    table = Table(rows, repeatRows=1, colWidths=[24*mm, 21*mm, 23*mm, 20*mm, 25*mm, 36*mm, 42*mm])
    table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.lightgrey),("GRID",(0,0),(-1,-1),0.25,colors.grey),("FONTSIZE",(0,0),(-1,-1),8),("VALIGN",(0,0),(-1,-1),"MIDDLE")]))
    story.append(table); story.append(Spacer(1, 10)); story.append(Paragraph("Challengers", styles["Heading2"]))
    challenger_text = ", ".join(f"{r.get('ticker')} ({_f(r.get('portfolio_score_adjusted'), _f(r.get('portfolio_score'))):.1f}, {r.get('rank_arrow','→')})" for r in data.get("challengers") or []) or "Ingen"
    story.append(Paragraph(challenger_text, styles["Normal"])); story.append(Spacer(1, 8))
    story.append(Paragraph("AI WOULD DO TODAY (advisory only)", styles["Heading2"]))
    actions = data.get("ai_would_do_today") or []
    if actions:
        for action in actions[:12]:
            story.append(Paragraph(f"{action.get('action')} {action.get('ticker')}: {_f(action.get('from_pct')):.1f}% → {_f(action.get('to_pct')):.1f}%", styles["Normal"]))
    else:
        story.append(Paragraph("Ingen foreslåtte endringer.", styles["Normal"]))
    doc.build(story)
    return out.getvalue()


def publish_pdf_report(state: Mapping[str, Any] | None = None) -> dict[str, Any]:
    from public_report_store import publish_durable_pdf
    from report_delivery import public_report_url
    run = {"report_id": f"SUPER-{datetime.now().strftime('%Y%m%d-%H%M%S')}", "public_pdf_name": f"SuperPortfolio_{datetime.now().strftime('%Y-%m-%d_%H%M')}.pdf"}
    publish_durable_pdf(run, build_pdf(state), document_kind="super_portfolio")
    run["report_url"] = public_report_url(run)
    return run


def notify_changes(changes: Sequence[Mapping[str, Any]], state: Mapping[str, Any] | None = None) -> tuple[bool, str]:
    if not changes:
        return True, "no changes"
    from notifier import normalize_notification_result, send_pushover_alert
    report = publish_pdf_report(state)
    data = dict(state or load_state())
    health = data.get("portfolio_health") if isinstance(data.get("portfolio_health"), Mapping) else {}
    lines = ["🌍 AI SUPER PORTFOLIO", f"🔄 {len(changes)} endring(er)"]
    if health:
        lines.append(f"{health.get('icon','')} Health {_f(health.get('score')):.1f}/100")
    icons = {"BUY":"🟢","ADD":"🔵","REDUCE":"🟠","SELL":"🔴"}
    for c in list(changes)[:8]:
        lines.append(f"{icons.get(str(c.get('action')), '•')} {c.get('action')} {c.get('ticker')} { _f(c.get('from_pct')):.1f}% → {_f(c.get('to_pct')):.1f}%")
    response = send_pushover_alert("\n".join(lines), title="Super Portfolio endret", url=report.get("report_url") or None, url_title="Åpne PDF")
    return normalize_notification_result(response)


def audit_rows(limit: int = 500) -> list[dict[str, Any]]:
    return read_events(AUDIT_KEY, AUDIT_PATH, limit=limit)
