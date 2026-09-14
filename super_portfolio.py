"""Super Portfolio foundation v19.22.0 RC16.32a.

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

VERSION = "v19.22.0-rc16.32a"
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


def target_weights(ranked: Sequence[Mapping[str, Any]], config: SuperPortfolioConfig | None = None) -> dict[str, float]:
    cfg = config or SuperPortfolioConfig()
    selected = list(ranked)[: cfg.target_positions]
    if not selected:
        return {}
    # Risk-adjusted score weights, capped, then renormalised.
    raw = {}
    for row in selected:
        risk_factor = max(0.25, 1.0 - _f(row.get("risk_score"), 50.0) / 140.0)
        raw[str(row["ticker"])] = max(0.01, _f(row.get("portfolio_score")) * risk_factor)
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
    cfg = SuperPortfolioConfig()
    state = load_state()
    ranked = rank_candidates(list(pipeline.get("candidates") or pipeline.get("proposals") or []), cfg)
    weights = target_weights(ranked, cfg)
    by_ticker = {row["ticker"]: row for row in ranked}
    previous = dict(state.get("positions") or {})
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
            "risk_score": row["risk_score"], "quality_score": row["quality_score"],
        }
        pos.update(_stop_status(pos, cfg))
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
    snapshot = {
        "at": now,
        "source_run_id": str(pipeline.get("run_id") or pipeline.get("report_id") or ""),
        "positions": [{k: v for k, v in p.items() if k != "raw_candidate"} for p in positions.values()],
        "changes": changes,
    }
    state.update({"positions": positions, "challengers": [{k: v for k, v in row.items() if k != "raw_candidate"} for row in challengers], "source_run_id": snapshot["source_run_id"]})
    history = list(state.get("history") or [])
    history.append(snapshot)
    state["history"] = history[-180:]
    if persist:
        save_state(state)
        append_event(AUDIT_KEY, AUDIT_PATH, {"timestamp": now, "event": "EVALUATE", "changes": changes, "source_run_id": snapshot["source_run_id"]})
    return {"state": state, "ranked": ranked, "changes": changes, "snapshot": snapshot}


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
    rows = [["Aksje", "Marked", "Vekt", "Fra inn", "Score", "Risiko", "Stop"]]
    for p in (data.get("positions") or {}).values():
        rows.append([p.get("ticker"), p.get("market"), f"{_f(p.get('target_weight_pct')):.2f}%", f"{_f(p.get('pnl_pct')):+.2f}%", f"{_f(p.get('portfolio_score')):.1f}", f"{_f(p.get('risk_score')):.1f}", f"{p.get('stop_icon','')} {p.get('stop_status','')}"])
    table = Table(rows, repeatRows=1, colWidths=[27*mm, 25*mm, 22*mm, 25*mm, 20*mm, 20*mm, 35*mm])
    table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.lightgrey),("GRID",(0,0),(-1,-1),0.25,colors.grey),("FONTSIZE",(0,0),(-1,-1),8),("VALIGN",(0,0),(-1,-1),"MIDDLE")]))
    story.append(table); story.append(Spacer(1, 10)); story.append(Paragraph("Challengers", styles["Heading2"]))
    challenger_text = ", ".join(f"{r.get('ticker')} ({_f(r.get('portfolio_score')):.1f})" for r in data.get("challengers") or []) or "Ingen"
    story.append(Paragraph(challenger_text, styles["Normal"])); doc.build(story)
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
    lines = ["🌍 AI SUPER PORTFOLIO", f"🔄 {len(changes)} endring(er)"]
    icons = {"BUY":"🟢","ADD":"🔵","REDUCE":"🟠","SELL":"🔴"}
    for c in list(changes)[:8]:
        lines.append(f"{icons.get(str(c.get('action')), '•')} {c.get('action')} {c.get('ticker')} { _f(c.get('from_pct')):.1f}% → {_f(c.get('to_pct')):.1f}%")
    response = send_pushover_alert("\n".join(lines), title="Super Portfolio endret", url=report.get("report_url") or None, url_title="Åpne PDF")
    return normalize_notification_result(response)


def audit_rows(limit: int = 500) -> list[dict[str, Any]]:
    return read_events(AUDIT_KEY, AUDIT_PATH, limit=limit)
