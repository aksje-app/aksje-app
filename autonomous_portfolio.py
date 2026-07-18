"""Autonomous Learning Portfolio Foundation v18.6.88.

A fully isolated, theoretical portfolio that can execute simulated BUY, HOLD,
REDUCE and SELL decisions from the latest Investment Pipeline output. It uses a
fixed, user-controlled parameter set. Self-modifying parameters are explicitly
out of scope for this version.
"""
from __future__ import annotations

import io
import json
import math
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from storage_architecture import runtime_data_path

VERSION = "v18.6.89"
ROOT = runtime_data_path("autonomous_portfolio")
PORTFOLIO_PATH = ROOT / "portfolio.json"
PARAMETERS_PATH = ROOT / "parameters.json"
TRADES_PATH = ROOT / "trades.json"
DECISIONS_PATH = ROOT / "decisions.json"
NOTIFICATIONS_PATH = ROOT / "notifications.json"
AUDIT_PATH = ROOT / "audit.jsonl"
PERFORMANCE_PATH = ROOT / "performance.json"
LATEST_PIPELINE_PATH = runtime_data_path("investment_pipeline") / "latest_run.json"


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _read(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def _append_audit(event: str, payload: Mapping[str, Any]) -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    row = {"timestamp": _now(), "version": VERSION, "event": event, "payload": dict(payload)}
    with AUDIT_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def _f(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except Exception:
        return default


@dataclass
class AutonomousParameters:
    initial_cash: float = 500000.0
    minimum_investment_score: float = 78.0
    minimum_data_quality: float = 55.0
    maximum_risk_score: float = 65.0
    maximum_position_pct: float = 5.0
    maximum_sector_pct: float = 20.0
    maximum_open_positions: int = 12
    reserve_cash_pct: float = 10.0
    stop_loss_pct: float = 8.0
    trailing_stop_pct: float = 10.0
    take_profit_pct: float = 22.0
    score_exit_threshold: float = 55.0
    maximum_drawdown_pct: float = 12.0
    daily_loss_limit_pct: float = 4.0
    allow_additions: bool = False
    notify_trades: bool = True
    notify_risk_events: bool = True

    def normalized(self) -> "AutonomousParameters":
        return AutonomousParameters(
            initial_cash=max(1000.0, _f(self.initial_cash, 500000.0)),
            minimum_investment_score=max(0.0, min(100.0, _f(self.minimum_investment_score, 78.0))),
            minimum_data_quality=max(0.0, min(100.0, _f(self.minimum_data_quality, 55.0))),
            maximum_risk_score=max(0.0, min(100.0, _f(self.maximum_risk_score, 65.0))),
            maximum_position_pct=max(0.1, min(25.0, _f(self.maximum_position_pct, 5.0))),
            maximum_sector_pct=max(1.0, min(100.0, _f(self.maximum_sector_pct, 20.0))),
            maximum_open_positions=max(1, min(100, int(self.maximum_open_positions))),
            reserve_cash_pct=max(0.0, min(95.0, _f(self.reserve_cash_pct, 10.0))),
            stop_loss_pct=max(0.1, min(50.0, _f(self.stop_loss_pct, 8.0))),
            trailing_stop_pct=max(0.1, min(50.0, _f(self.trailing_stop_pct, 10.0))),
            take_profit_pct=max(0.1, min(300.0, _f(self.take_profit_pct, 22.0))),
            score_exit_threshold=max(0.0, min(100.0, _f(self.score_exit_threshold, 55.0))),
            maximum_drawdown_pct=max(0.5, min(80.0, _f(self.maximum_drawdown_pct, 12.0))),
            daily_loss_limit_pct=max(0.1, min(50.0, _f(self.daily_loss_limit_pct, 4.0))),
            allow_additions=bool(self.allow_additions),
            notify_trades=bool(self.notify_trades),
            notify_risk_events=bool(self.notify_risk_events),
        )


def load_parameters() -> AutonomousParameters:
    raw = _read(PARAMETERS_PATH, {})
    try:
        return AutonomousParameters(**{k: raw[k] for k in AutonomousParameters.__dataclass_fields__ if k in raw}).normalized()
    except Exception:
        return AutonomousParameters()


def save_parameters(params: AutonomousParameters) -> AutonomousParameters:
    params = params.normalized()
    previous = _read(PARAMETERS_PATH, {})
    _write(PARAMETERS_PATH, asdict(params))
    if previous and previous != asdict(params):
        _append_audit("PARAMETERS_CHANGED_BY_USER", {"before": previous, "after": asdict(params)})
    return params


def default_portfolio(params: AutonomousParameters | None = None) -> dict[str, Any]:
    p = (params or load_parameters()).normalized()
    return {
        "version": VERSION,
        "account_id": "AUTONOMOUS-LEARNING-PORTFOLIO",
        "mode": "THEORETICAL_ONLY",
        "status": "PAUSED",
        "created_at": _now(),
        "updated_at": _now(),
        "initial_cash": p.initial_cash,
        "cash": p.initial_cash,
        "positions": {},
        "realized_pnl": 0.0,
        "high_watermark": p.initial_cash,
        "last_equity": p.initial_cash,
        "last_run_id": None,
        "pause_reason": "Ikke aktivert av bruker",
    }


def load_portfolio() -> dict[str, Any]:
    params = load_parameters()
    value = _read(PORTFOLIO_PATH, None)
    if not isinstance(value, dict):
        value = default_portfolio(params)
        _write(PORTFOLIO_PATH, value)
    value.setdefault("positions", {})
    return value


def _candidate_price(candidate: Mapping[str, Any], existing: Mapping[str, Any] | None = None) -> float:
    raw = candidate.get("raw") if isinstance(candidate.get("raw"), Mapping) else {}
    for key in ("price", "current_price", "last_price", "close", "regularMarketPrice", "last"):
        value = _f(candidate.get(key, raw.get(key)), 0.0)
        if value > 0:
            return value
    if existing:
        value = _f(existing.get("last_price", existing.get("average_price")), 0.0)
        if value > 0:
            return value
    return 0.0


def portfolio_equity(portfolio: Mapping[str, Any]) -> float:
    positions = portfolio.get("positions") or {}
    market_value = sum(_f(p.get("quantity")) * _f(p.get("last_price", p.get("average_price"))) for p in positions.values())
    return _f(portfolio.get("cash")) + market_value


def _sector_value(portfolio: Mapping[str, Any], sector: str) -> float:
    return sum(
        _f(p.get("quantity")) * _f(p.get("last_price", p.get("average_price")))
        for p in (portfolio.get("positions") or {}).values()
        if str(p.get("sector") or "Unknown") == sector
    )


def _notification(kind: str, title: str, message: str, payload: Mapping[str, Any]) -> None:
    rows = _read(NOTIFICATIONS_PATH, [])
    if not isinstance(rows, list):
        rows = []
    rows.insert(0, {"timestamp": _now(), "kind": kind, "title": title, "message": message, "payload": dict(payload), "delivery": "LOCAL_QUEUE"})
    _write(NOTIFICATIONS_PATH, rows[:1000])
    try:
        from notification_service import send_pushover_notification
        send_pushover_notification(title, message)
        rows[0]["delivery"] = "PUSHOVER_ATTEMPTED"
        _write(NOTIFICATIONS_PATH, rows[:1000])
    except Exception:
        pass


def _record_trade(trade: dict[str, Any]) -> None:
    trades = _read(TRADES_PATH, [])
    if not isinstance(trades, list):
        trades = []
    trades.insert(0, trade)
    _write(TRADES_PATH, trades)
    _append_audit("SIMULATED_TRADE", trade)


def _record_decisions(rows: Sequence[Mapping[str, Any]]) -> None:
    current = _read(DECISIONS_PATH, [])
    if not isinstance(current, list):
        current = []
    _write(DECISIONS_PATH, list(rows) + current[:5000])


def _sell(portfolio: dict[str, Any], ticker: str, price: float, reason: str, run_id: str, params: AutonomousParameters) -> dict[str, Any] | None:
    pos = (portfolio.get("positions") or {}).get(ticker)
    if not pos or price <= 0:
        return None
    quantity = _f(pos.get("quantity"))
    proceeds = quantity * price
    cost = quantity * _f(pos.get("average_price"))
    pnl = proceeds - cost
    portfolio["cash"] = _f(portfolio.get("cash")) + proceeds
    portfolio["realized_pnl"] = _f(portfolio.get("realized_pnl")) + pnl
    del portfolio["positions"][ticker]
    trade = {
        "trade_id": f"AT-{datetime.now().strftime('%Y%m%d%H%M%S%f')}", "timestamp": _now(), "run_id": run_id,
        "action": "SELL", "ticker": ticker, "price": round(price, 4), "quantity": round(quantity, 8),
        "value": round(proceeds, 2), "pnl": round(pnl, 2), "pnl_pct": round((price / _f(pos.get('average_price'), price) - 1) * 100, 2),
        "reason": reason, "strategy": pos.get("strategy"), "mode": "THEORETICAL_ONLY",
    }
    _record_trade(trade)
    if params.notify_trades:
        _notification("TRADE", f"AUTONOMOUS SELL {ticker}", f"{reason}. Teoretisk resultat {trade['pnl_pct']:+.2f}% ({pnl:+.2f}).", trade)
    return trade


def run_autonomous_cycle(candidates: Sequence[Mapping[str, Any]], run_id: str | None = None) -> dict[str, Any]:
    params = load_parameters().normalized()
    portfolio = load_portfolio()
    run_id = run_id or f"ALP-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    decisions: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    exited_this_cycle: set[str] = set()
    candidate_map = {str(c.get("ticker") or "").upper(): c for c in candidates if str(c.get("ticker") or "").strip()}

    # Mark positions and evaluate hard exits first.
    for ticker, pos in list((portfolio.get("positions") or {}).items()):
        candidate = candidate_map.get(ticker, {})
        price = _candidate_price(candidate, pos)
        if price <= 0:
            decisions.append({"timestamp": _now(), "run_id": run_id, "ticker": ticker, "action": "HOLD", "reason": "Mangler ny pris; eksisterende markering beholdes"})
            continue
        pos["last_price"] = price
        pos["highest_price"] = max(_f(pos.get("highest_price"), price), price)
        avg = _f(pos.get("average_price"), price)
        score = _f(candidate.get("investment_score"), 100.0)
        reason = None
        if price <= avg * (1 - params.stop_loss_pct / 100):
            reason = "STOP LOSS"
        elif price <= _f(pos.get("highest_price"), price) * (1 - params.trailing_stop_pct / 100):
            reason = "TRAILING STOP"
        elif price >= avg * (1 + params.take_profit_pct / 100):
            reason = "TAKE PROFIT"
        elif candidate and score < params.score_exit_threshold:
            reason = f"Investment Score falt til {score:.1f}"
        if reason:
            trade = _sell(portfolio, ticker, price, reason, run_id, params)
            if trade:
                trades.append(trade)
                exited_this_cycle.add(ticker)
                decisions.append({"timestamp": _now(), "run_id": run_id, "ticker": ticker, "action": "SELL", "reason": reason, "price": price, "score": score})
        else:
            decisions.append({"timestamp": _now(), "run_id": run_id, "ticker": ticker, "action": "HOLD", "reason": "Ingen exitregel utløst", "price": price, "score": score})

    equity_before_buys = portfolio_equity(portfolio)
    high = max(_f(portfolio.get("high_watermark"), equity_before_buys), equity_before_buys)
    drawdown = max(0.0, (1 - equity_before_buys / high) * 100) if high else 0.0
    if drawdown >= params.maximum_drawdown_pct:
        portfolio["status"] = "PAUSED"
        portfolio["pause_reason"] = f"Maks drawdown overskredet ({drawdown:.2f}%)"
        if params.notify_risk_events:
            _notification("RISK", "AUTONOMOUS PORTFOLIO PAUSED", portfolio["pause_reason"], {"drawdown_pct": drawdown, "run_id": run_id})
        _append_audit("PORTFOLIO_AUTO_PAUSED", {"reason": portfolio["pause_reason"], "run_id": run_id})

    # New buys only when explicitly active.
    if portfolio.get("status") == "ACTIVE":
        ranked = sorted(candidates, key=lambda c: _f(c.get("investment_score")), reverse=True)
        for candidate in ranked:
            ticker = str(candidate.get("ticker") or "").upper()
            if not ticker:
                continue
            if ticker in exited_this_cycle:
                decisions.append({"timestamp": _now(), "run_id": run_id, "ticker": ticker, "action": "SKIP", "reason": "Ingen gjeninntreden i samme beslutningssyklus"})
                continue
            score = _f(candidate.get("investment_score"))
            quality = _f(candidate.get("data_quality"))
            risk = _f(candidate.get("risk_score"), 100)
            price = _candidate_price(candidate)
            if ticker in portfolio["positions"] and not params.allow_additions:
                continue
            rejection = None
            if score < params.minimum_investment_score:
                rejection = f"Score {score:.1f} under terskel"
            elif quality < params.minimum_data_quality:
                rejection = f"Datakvalitet {quality:.1f} under terskel"
            elif risk > params.maximum_risk_score:
                rejection = f"Risiko {risk:.1f} over grense"
            elif price <= 0:
                rejection = "Mangler gyldig markedspris"
            elif len(portfolio["positions"]) >= params.maximum_open_positions:
                rejection = "Maks antall åpne posisjoner"
            if rejection:
                decisions.append({"timestamp": _now(), "run_id": run_id, "ticker": ticker, "action": "SKIP", "reason": rejection, "score": score})
                continue

            equity = portfolio_equity(portfolio)
            reserve = equity * params.reserve_cash_pct / 100
            available = max(0.0, _f(portfolio.get("cash")) - reserve)
            proposed = min(params.maximum_position_pct, max(0.5, _f(candidate.get("proposed_position_pct"), params.maximum_position_pct)))
            target_value = equity * proposed / 100
            sector = str(candidate.get("sector") or "Unknown")
            sector_room = max(0.0, equity * params.maximum_sector_pct / 100 - _sector_value(portfolio, sector))
            value = min(target_value, available, sector_room)
            quantity = math.floor(value / price * 10000) / 10000 if price > 0 else 0
            value = quantity * price
            if quantity <= 0 or value < 100:
                decisions.append({"timestamp": _now(), "run_id": run_id, "ticker": ticker, "action": "SKIP", "reason": "Utilstrekkelig kapital eller sektorrom", "score": score})
                continue

            portfolio["cash"] = _f(portfolio.get("cash")) - value
            portfolio["positions"][ticker] = {
                "ticker": ticker, "name": candidate.get("name", ticker), "sector": sector,
                "quantity": quantity, "average_price": price, "last_price": price, "highest_price": price,
                "opened_at": _now(), "strategy": candidate.get("strategy_match", "Unknown"),
                "entry_score": score, "entry_risk_score": risk, "entry_data_quality": quality,
                "source_run_id": run_id,
            }
            trade = {
                "trade_id": f"AT-{datetime.now().strftime('%Y%m%d%H%M%S%f')}", "timestamp": _now(), "run_id": run_id,
                "action": "BUY", "ticker": ticker, "price": round(price, 4), "quantity": quantity,
                "value": round(value, 2), "pnl": 0.0, "reason": f"Score {score:.1f}, risiko {risk:.1f}, datakvalitet {quality:.1f}",
                "strategy": candidate.get("strategy_match"), "mode": "THEORETICAL_ONLY",
            }
            _record_trade(trade)
            trades.append(trade)
            decisions.append({"timestamp": _now(), "run_id": run_id, "ticker": ticker, "action": "BUY", "reason": trade["reason"], "price": price, "score": score})
            if params.notify_trades:
                _notification("TRADE", f"AUTONOMOUS BUY {ticker}", f"Teoretisk kjøp {quantity:g} @ {price:.2f}. {trade['reason']}", trade)

    equity = portfolio_equity(portfolio)
    portfolio["updated_at"] = _now()
    portfolio["last_run_id"] = run_id
    portfolio["last_equity"] = equity
    portfolio["high_watermark"] = max(_f(portfolio.get("high_watermark"), equity), equity)
    _write(PORTFOLIO_PATH, portfolio)
    _record_decisions(decisions)
    perf = calculate_performance(portfolio)
    _write(PERFORMANCE_PATH, perf)
    _append_audit("AUTONOMOUS_CYCLE_COMPLETED", {"run_id": run_id, "decisions": len(decisions), "trades": len(trades), "equity": equity, "status": portfolio.get("status")})
    return {"run_id": run_id, "portfolio": portfolio, "decisions": decisions, "trades": trades, "performance": perf}


def calculate_performance(portfolio: Mapping[str, Any] | None = None) -> dict[str, Any]:
    portfolio = dict(portfolio or load_portfolio())
    trades = _read(TRADES_PATH, [])
    sells = [t for t in trades if t.get("action") == "SELL"] if isinstance(trades, list) else []
    wins = [t for t in sells if _f(t.get("pnl")) > 0]
    losses = [t for t in sells if _f(t.get("pnl")) < 0]
    gross_profit = sum(_f(t.get("pnl")) for t in wins)
    gross_loss = abs(sum(_f(t.get("pnl")) for t in losses))
    equity = portfolio_equity(portfolio)
    initial = _f(portfolio.get("initial_cash"), 1.0)
    high = max(_f(portfolio.get("high_watermark"), equity), equity)
    return {
        "updated_at": _now(), "equity": round(equity, 2), "cash": round(_f(portfolio.get("cash")), 2),
        "total_return_pct": round((equity / initial - 1) * 100, 2) if initial else 0.0,
        "realized_pnl": round(_f(portfolio.get("realized_pnl")), 2),
        "open_positions": len(portfolio.get("positions") or {}), "closed_trades": len(sells),
        "win_rate_pct": round(len(wins) / len(sells) * 100, 2) if sells else 0.0,
        "profit_factor": round(gross_profit / gross_loss, 3) if gross_loss else (999.0 if gross_profit else 0.0),
        "drawdown_pct": round(max(0.0, (1 - equity / high) * 100), 2) if high else 0.0,
    }


def set_status(active: bool, reason: str = "Brukerhandling") -> dict[str, Any]:
    portfolio = load_portfolio()
    portfolio["status"] = "ACTIVE" if active else "PAUSED"
    portfolio["pause_reason"] = "" if active else reason
    portfolio["updated_at"] = _now()
    _write(PORTFOLIO_PATH, portfolio)
    _append_audit("PORTFOLIO_STATUS_CHANGED", {"status": portfolio["status"], "reason": reason})
    return portfolio


def reset_portfolio(confirmation: str) -> dict[str, Any]:
    if confirmation.strip().upper() != "RESET":
        raise ValueError("Skriv RESET for å bekrefte.")
    params = load_parameters()
    portfolio = default_portfolio(params)
    _write(PORTFOLIO_PATH, portfolio)
    for path in (TRADES_PATH, DECISIONS_PATH, NOTIFICATIONS_PATH, PERFORMANCE_PATH):
        _write(path, [] if path != PERFORMANCE_PATH else calculate_performance(portfolio))
    _append_audit("PORTFOLIO_RESET", {"initial_cash": params.initial_cash})
    return portfolio


def build_evaluation_bundle() -> bytes:
    """Create a compact ZIP that can be uploaded to ChatGPT for evaluation."""
    manifest = {
        "version": VERSION, "created_at": _now(), "purpose": "Module evaluation",
        "contains": ["portfolio", "parameters", "trades", "decisions", "performance", "notifications", "audit", "latest_pipeline"],
        "privacy_note": "Review before sharing. The bundle is intended to contain trading simulation data, not credentials.",
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for name, path in (
            ("portfolio.json", PORTFOLIO_PATH), ("parameters.json", PARAMETERS_PATH), ("trades.json", TRADES_PATH),
            ("decisions.json", DECISIONS_PATH), ("performance.json", PERFORMANCE_PATH), ("notifications.json", NOTIFICATIONS_PATH),
            ("audit.jsonl", AUDIT_PATH), ("latest_pipeline.json", LATEST_PIPELINE_PATH),
        ):
            if path.exists():
                zf.writestr(name, path.read_bytes())
    return buffer.getvalue()


def render_autonomous_portfolio() -> None:
    import pandas as pd
    import streamlit as st

    st.markdown("#### 🧠 Autonomous Learning Portfolio")
    st.caption("Separat, teoretisk portefølje med faste brukerdefinerte regler. Ingen meglerkobling, ingen ekte handler og kontrollert parameterlæring er tilgjengelig i egen fane i v18.6.89.")
    params = load_parameters()
    portfolio = load_portfolio()
    perf = calculate_performance(portfolio)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Status", portfolio.get("status", "PAUSED"))
    c2.metric("Porteføljeverdi", f"{perf['equity']:,.0f}")
    c3.metric("Avkastning", f"{perf['total_return_pct']:+.2f}%")
    c4.metric("Åpne posisjoner", perf["open_positions"])
    c5.metric("Drawdown", f"{perf['drawdown_pct']:.2f}%")

    a, b, c = st.columns(3)
    if portfolio.get("status") == "ACTIVE":
        if a.button("Pause autonom portefølje", use_container_width=True, key="alp_pause_v18688"):
            set_status(False, "Pauset av bruker"); st.rerun()
    else:
        if a.button("Aktiver autonom simulering", type="primary", use_container_width=True, key="alp_activate_v18688"):
            set_status(True, "Aktivert av bruker"); st.rerun()
    if b.button("Kjør én teoretisk beslutningssyklus", use_container_width=True, key="alp_cycle_v18688"):
        pipeline = _read(LATEST_PIPELINE_PATH, {})
        candidates = pipeline.get("candidates") or pipeline.get("proposals") or []
        if not candidates:
            st.error("Ingen kandidater funnet. Kjør Investment Pipeline først.")
        else:
            result = run_autonomous_cycle(candidates, str(pipeline.get("run_id") or "MANUAL"))
            st.success(f"Syklus fullført: {len(result['trades'])} teoretiske handler, {len(result['decisions'])} beslutninger.")
            st.rerun()
    c.download_button("Last ned evalueringspakke", build_evaluation_bundle(), file_name=f"autonomous_learning_evaluation_{datetime.now().strftime('%Y%m%d_%H%M')}.zip", mime="application/zip", use_container_width=True, key="alp_eval_bundle_v18688")

    with st.expander("Faste parametere", expanded=False):
        p1, p2, p3, p4 = st.columns(4)
        initial_cash = p1.number_input("Startkapital", 1000.0, 100000000.0, float(params.initial_cash), 10000.0, key="alp_initial_v18688")
        min_score = p2.slider("Minimum Investment Score", 0.0, 100.0, float(params.minimum_investment_score), 1.0, key="alp_minscore_v18688")
        min_quality = p3.slider("Minimum datakvalitet", 0.0, 100.0, float(params.minimum_data_quality), 1.0, key="alp_quality_v18688")
        max_risk = p4.slider("Maks risikoscore", 0.0, 100.0, float(params.maximum_risk_score), 1.0, key="alp_risk_v18688")
        q1, q2, q3, q4 = st.columns(4)
        max_pos = q1.slider("Maks posisjon %", 0.5, 25.0, float(params.maximum_position_pct), 0.5, key="alp_pos_v18688")
        max_sector = q2.slider("Maks sektor %", 1.0, 100.0, float(params.maximum_sector_pct), 1.0, key="alp_sector_v18688")
        max_open = q3.number_input("Maks åpne posisjoner", 1, 100, int(params.maximum_open_positions), 1, key="alp_open_v18688")
        reserve = q4.slider("Kontantreserve %", 0.0, 95.0, float(params.reserve_cash_pct), 1.0, key="alp_reserve_v18688")
        r1, r2, r3, r4 = st.columns(4)
        stop = r1.slider("Stop loss %", 0.5, 50.0, float(params.stop_loss_pct), 0.5, key="alp_stop_v18688")
        trail = r2.slider("Trailing stop %", 0.5, 50.0, float(params.trailing_stop_pct), 0.5, key="alp_trail_v18688")
        target = r3.slider("Take profit %", 0.5, 300.0, float(params.take_profit_pct), 0.5, key="alp_target_v18688")
        score_exit = r4.slider("Score-exit under", 0.0, 100.0, float(params.score_exit_threshold), 1.0, key="alp_scoreexit_v18688")
        s1, s2 = st.columns(2)
        max_dd = s1.slider("Maks drawdown %", 0.5, 80.0, float(params.maximum_drawdown_pct), 0.5, key="alp_dd_v18688")
        notify = s2.checkbox("Varsle ved teoretiske handler", params.notify_trades, key="alp_notify_v18688")
        if st.button("Lagre parametere", key="alp_save_params_v18688"):
            save_parameters(AutonomousParameters(initial_cash=initial_cash, minimum_investment_score=min_score, minimum_data_quality=min_quality, maximum_risk_score=max_risk, maximum_position_pct=max_pos, maximum_sector_pct=max_sector, maximum_open_positions=int(max_open), reserve_cash_pct=reserve, stop_loss_pct=stop, trailing_stop_pct=trail, take_profit_pct=target, score_exit_threshold=score_exit, maximum_drawdown_pct=max_dd, notify_trades=notify, notify_risk_events=True))
            st.success("Parameterne er lagret. De endres ikke automatisk av systemet.")

    positions = list((portfolio.get("positions") or {}).values())
    st.markdown("##### Åpne posisjoner")
    if positions:
        rows = []
        for p in positions:
            avg, last, qty = _f(p.get("average_price")), _f(p.get("last_price")), _f(p.get("quantity"))
            rows.append({"Ticker": p.get("ticker"), "Sektor": p.get("sector"), "Antall": qty, "Snitt": avg, "Siste": last, "Verdi": qty * last, "P/L %": (last / avg - 1) * 100 if avg else 0, "Strategi": p.get("strategy"), "Åpnet": p.get("opened_at")})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("Ingen åpne teoretiske posisjoner.")

    trades = _read(TRADES_PATH, [])
    decisions = _read(DECISIONS_PATH, [])
    t1, t2, t3, t4 = st.tabs(["Handler", "Beslutninger", "Kontrollert læring", "Audit og deling"])
    with t1:
        if trades:
            st.dataframe(pd.DataFrame(trades[:500]), use_container_width=True, hide_index=True)
            st.download_button("Eksporter handler JSON", json.dumps(trades, ensure_ascii=False, indent=2), "autonomous_trades.json", "application/json", key="alp_trades_json_v18688")
        else:
            st.caption("Ingen handler registrert.")
    with t2:
        if decisions:
            st.dataframe(pd.DataFrame(decisions[:1000]), use_container_width=True, hide_index=True)
        else:
            st.caption("Ingen beslutninger registrert.")
    with t3:
        from controlled_parameter_learning import render_controlled_learning
        render_controlled_learning()
    with t4:
        st.info("For evaluering: last ned evalueringspakken og last den opp i ChatGPT. Den inneholder parametere, portefølje, handler, beslutninger, ytelse, varslingslogg, audit og siste pipeline-kjøring.")
        st.warning("Kontroller pakken før deling. Ikke legg API-nøkler, Pushover-token eller andre hemmeligheter i runtime-filene.")
        confirm = st.text_input("Skriv RESET for å nullstille kontoen", key="alp_reset_text_v18688")
        if st.button("Nullstill autonom konto", key="alp_reset_v18688"):
            try:
                reset_portfolio(confirm); st.success("Kontoen er nullstilt."); st.rerun()
            except ValueError as exc:
                st.error(str(exc))
