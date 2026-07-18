"""Professional Backtesting Engine v18.6.81.

Isolated research simulator for Strategy Lab. It never modifies Paper Trading,
production rules, signal weights, or live orders. The engine adds realistic
execution assumptions, benchmark comparison, risk metrics, and reproducible
runtime reports.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from storage_architecture import runtime_data_path
from strategy_lab import load_strategies

try:
    import pandas as pd  # type: ignore
except Exception:  # pragma: no cover
    pd = None  # type: ignore

BACKTEST_DIR = runtime_data_path("backtesting")
LATEST_REPORT_PATH = BACKTEST_DIR / "latest_backtest.json"


@dataclass(frozen=True)
class ExecutionAssumptions:
    start_capital: float = 100000.0
    commission_pct: float = 0.05
    slippage_pct: float = 0.10
    risk_free_rate_pct: float = 3.0
    position_pct: float = 100.0
    execution_mode: str = "NEXT_OPEN"


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        value = float(value)
        return value if math.isfinite(value) else default
    except Exception:
        return default


def _atomic_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def _normalise_ohlc(data: Any):
    if pd is None or data is None or not hasattr(data, "empty") or data.empty:
        return None
    frame = data.copy()
    if getattr(frame.columns, "nlevels", 1) > 1:
        flattened = {}
        for col in frame.columns:
            parts = [str(x) for x in (col if isinstance(col, tuple) else (col,))]
            for wanted in ("Open", "High", "Low", "Close", "Volume"):
                if wanted in parts and wanted not in flattened:
                    flattened[wanted] = frame[col]
        frame = pd.DataFrame(flattened, index=frame.index)
    rename = {str(c).lower(): c for c in frame.columns}
    required = {}
    for wanted in ("open", "high", "low", "close"):
        source = rename.get(wanted)
        if source is None and wanted != "close":
            source = rename.get("close")
        if source is None:
            return None
        required[wanted] = pd.to_numeric(frame[source], errors="coerce")
    required["volume"] = pd.to_numeric(frame[rename["volume"]], errors="coerce") if "volume" in rename else 0.0
    out = pd.DataFrame(required, index=frame.index).dropna(subset=["close"])
    out = out[~out.index.duplicated(keep="last")].sort_index()
    return out if len(out) >= 10 else None


def validate_market_data(data: Any) -> Dict[str, Any]:
    frame = _normalise_ohlc(data)
    if frame is None:
        return {"ok": False, "quality_score": 0, "issues": ["For lite eller ugyldig OHLC-historikk"]}
    issues: List[str] = []
    if frame.index.has_duplicates:
        issues.append("Dupliserte datoer")
    non_positive = int((frame["close"] <= 0).sum())
    if non_positive:
        issues.append(f"{non_positive} ikke-positive sluttkurser")
    jumps = frame["close"].pct_change().abs()
    extreme = int((jumps > 0.50).sum())
    if extreme:
        issues.append(f"{extreme} ekstreme dagsbevegelser over 50 %")
    missing_ratio = float(frame[["open", "high", "low", "close"]].isna().mean().mean())
    if missing_ratio > 0.01:
        issues.append(f"Manglende OHLC-data: {missing_ratio:.1%}")
    score = max(0, 100 - non_positive * 10 - extreme * 3 - int(missing_ratio * 100))
    return {
        "ok": score >= 60 and non_positive == 0,
        "quality_score": score,
        "issues": issues,
        "rows": int(len(frame)),
        "start": str(frame.index[0]),
        "end": str(frame.index[-1]),
    }


def _trade_cost(notional: float, assumptions: ExecutionAssumptions) -> float:
    return abs(notional) * max(0.0, assumptions.commission_pct) / 100.0


def _fill_price(raw_price: float, side: str, assumptions: ExecutionAssumptions) -> float:
    slip = max(0.0, assumptions.slippage_pct) / 100.0
    return raw_price * (1.0 + slip if side == "BUY" else 1.0 - slip)


def run_backtest(
    data: Any,
    strategy: Mapping[str, Any],
    assumptions: Optional[ExecutionAssumptions] = None,
) -> Dict[str, Any]:
    """Run a long-only, one-position backtest without look-ahead execution.

    Signals are calculated at close. In NEXT_OPEN mode, fills occur at the next
    bar's open. Stops are evaluated against daily low/high and filled no better
    than the configured trigger after slippage.
    """
    if pd is None:
        return {"ok": False, "error": "pandas mangler"}
    assumptions = assumptions or ExecutionAssumptions()
    frame = _normalise_ohlc(data)
    quality = validate_market_data(data)
    if frame is None or not quality.get("ok"):
        return {"ok": False, "error": "; ".join(quality.get("issues") or ["Ugyldig datasett"]), "data_quality": quality}

    entry = dict(strategy.get("entry") or {})
    exit_cfg = dict(strategy.get("exit") or {})
    fast = max(2, int(_safe_float(entry.get("fast_sma"), 20)))
    slow = max(fast + 1, int(_safe_float(entry.get("slow_sma"), 50)))
    mom_days = max(1, int(_safe_float(entry.get("momentum_days"), 20)))
    mom_min = _safe_float(entry.get("momentum_min_pct"), 0.0) / 100.0
    stop_loss = max(0.0, _safe_float(exit_cfg.get("stop_loss_pct"), 8.0) / 100.0)
    take_profit = max(0.0, _safe_float(exit_cfg.get("take_profit_pct"), 20.0) / 100.0)
    trailing = max(0.0, _safe_float(exit_cfg.get("trailing_stop_pct"), 10.0) / 100.0)
    max_hold = max(1, int(_safe_float(exit_cfg.get("max_holding_days"), 90)))

    frame["fast"] = frame["close"].rolling(fast).mean()
    frame["slow"] = frame["close"].rolling(slow).mean()
    frame["momentum"] = frame["close"].pct_change(mom_days)
    frame["entry_signal"] = (frame["fast"] > frame["slow"]) & (frame["momentum"] >= mom_min)
    frame["trend_exit"] = frame["fast"] < frame["slow"]

    cash = float(assumptions.start_capital)
    shares = 0.0
    entry_price = entry_cost = highest = initial_risk_per_share = 0.0
    entry_date = None
    hold_bars = 0
    pending_entry = False
    pending_exit = ""
    trades: List[Dict[str, Any]] = []
    equity_rows: List[Dict[str, Any]] = []
    exposure_bars = 0

    for i, (idx, row) in enumerate(frame.iterrows()):
        open_px, high_px, low_px, close_px = map(float, (row["open"], row["high"], row["low"], row["close"]))

        # Execute signals generated on the prior close.
        if pending_exit and shares > 0:
            fill = _fill_price(open_px, "SELL", assumptions)
            proceeds = shares * fill
            cost = _trade_cost(proceeds, assumptions)
            pnl = proceeds - cost - entry_cost - shares * entry_price
            risk_amount = shares * initial_risk_per_share
            trades.append({
                "type": "SELL", "date": str(idx), "price": round(fill, 6), "shares": shares,
                "commission": round(cost, 2), "pnl": round(pnl, 2),
                "pnl_pct": round((fill / entry_price - 1.0) * 100.0, 2) if entry_price else 0.0,
                "r_multiple": round(pnl / risk_amount, 2) if risk_amount > 0 else 0.0,
                "reason": pending_exit, "entry_date": str(entry_date), "holding_days": hold_bars,
            })
            cash += proceeds - cost
            shares = 0.0
            entry_price = entry_cost = highest = initial_risk_per_share = 0.0
            entry_date = None
            hold_bars = 0
            pending_exit = ""

        if pending_entry and shares <= 0:
            fill = _fill_price(open_px, "BUY", assumptions)
            allocation = cash * min(100.0, max(0.0, assumptions.position_pct)) / 100.0
            estimated_cost = _trade_cost(allocation, assumptions)
            shares = max(0.0, (allocation - estimated_cost) / fill) if fill > 0 else 0.0
            notional = shares * fill
            cost = _trade_cost(notional, assumptions)
            if shares > 0 and notional + cost <= cash + 1e-6:
                cash -= notional + cost
                entry_price, entry_cost, highest, entry_date, hold_bars = fill, cost, fill, idx, 0
                initial_risk_per_share = entry_price * stop_loss if stop_loss > 0 else entry_price * 0.01
                trades.append({"type": "BUY", "date": str(idx), "price": round(fill, 6), "shares": shares, "commission": round(cost, 2), "reason": "ENTRY_RULE"})
            pending_entry = False

        if shares > 0:
            exposure_bars += 1
            hold_bars += 1
            highest = max(highest, high_px)
            stop_trigger = entry_price * (1.0 - stop_loss) if stop_loss else None
            trail_trigger = highest * (1.0 - trailing) if trailing else None
            target_trigger = entry_price * (1.0 + take_profit) if take_profit else None
            intraday_reason = ""
            trigger_price = 0.0
            # Conservative priority when multiple levels are touched in one daily bar.
            if stop_trigger and low_px <= stop_trigger:
                intraday_reason, trigger_price = "STOP_LOSS", min(open_px, stop_trigger)
            elif trail_trigger and low_px <= trail_trigger:
                intraday_reason, trigger_price = "TRAILING_STOP", min(open_px, trail_trigger)
            elif target_trigger and high_px >= target_trigger:
                intraday_reason, trigger_price = "TAKE_PROFIT", max(open_px, target_trigger)
            if intraday_reason:
                fill = _fill_price(trigger_price, "SELL", assumptions)
                proceeds = shares * fill
                cost = _trade_cost(proceeds, assumptions)
                pnl = proceeds - cost - entry_cost - shares * entry_price
                risk_amount = shares * initial_risk_per_share
                trades.append({
                    "type": "SELL", "date": str(idx), "price": round(fill, 6), "shares": shares,
                    "commission": round(cost, 2), "pnl": round(pnl, 2),
                    "pnl_pct": round((fill / entry_price - 1.0) * 100.0, 2),
                    "r_multiple": round(pnl / risk_amount, 2) if risk_amount > 0 else 0.0,
                    "reason": intraday_reason, "entry_date": str(entry_date), "holding_days": hold_bars,
                })
                cash += proceeds - cost
                shares = 0.0
                entry_price = entry_cost = highest = initial_risk_per_share = 0.0
                entry_date = None
                hold_bars = 0
            elif hold_bars >= max_hold:
                pending_exit = "TIME_EXIT"
            elif bool(row["trend_exit"]):
                pending_exit = "TREND_EXIT"

        if shares <= 0 and not pending_entry and not pending_exit and bool(row["entry_signal"]):
            pending_entry = True

        equity_rows.append({"date": idx, "value": cash + shares * close_px, "cash": cash, "exposed": shares > 0})

    if shares > 0:
        idx = frame.index[-1]
        fill = _fill_price(float(frame.iloc[-1]["close"]), "SELL", assumptions)
        proceeds = shares * fill
        cost = _trade_cost(proceeds, assumptions)
        pnl = proceeds - cost - entry_cost - shares * entry_price
        risk_amount = shares * initial_risk_per_share
        cash += proceeds - cost
        trades.append({
            "type": "SELL", "date": str(idx), "price": round(fill, 6), "shares": shares,
            "commission": round(cost, 2), "pnl": round(pnl, 2),
            "pnl_pct": round((fill / entry_price - 1.0) * 100.0, 2),
            "r_multiple": round(pnl / risk_amount, 2) if risk_amount > 0 else 0.0,
            "reason": "END_OF_TEST", "entry_date": str(entry_date), "holding_days": hold_bars,
        })
        equity_rows[-1]["value"] = cash
        equity_rows[-1]["cash"] = cash
        equity_rows[-1]["exposed"] = False

    equity = pd.DataFrame(equity_rows).set_index("date")
    metrics = calculate_professional_metrics(equity, trades, assumptions, exposure_bars, len(frame))
    benchmark = calculate_benchmark(frame, assumptions.start_capital)
    monthly = calculate_monthly_returns(equity)
    return {
        "ok": True,
        "created_at": _now_iso(),
        "strategy_id": strategy.get("strategy_id"),
        "strategy_name": strategy.get("name"),
        "assumptions": asdict(assumptions),
        "data_quality": quality,
        "metrics": metrics,
        "benchmark": benchmark,
        "trades": trades,
        "equity": equity.reset_index(),
        "monthly_returns": monthly,
    }


def calculate_professional_metrics(equity: Any, trades: Sequence[Mapping[str, Any]], assumptions: ExecutionAssumptions, exposure_bars: int, total_bars: int) -> Dict[str, float]:
    vals = pd.to_numeric(equity["value"], errors="coerce").dropna()
    returns = vals.pct_change().dropna()
    years = max(len(vals) / 252.0, 1.0 / 252.0)
    total_return = vals.iloc[-1] / assumptions.start_capital - 1.0
    cagr = (vals.iloc[-1] / assumptions.start_capital) ** (1.0 / years) - 1.0 if vals.iloc[-1] > 0 else -1.0
    drawdown = vals / vals.cummax() - 1.0
    max_dd = float(drawdown.min()) if len(drawdown) else 0.0
    rf_daily = (1.0 + assumptions.risk_free_rate_pct / 100.0) ** (1.0 / 252.0) - 1.0
    excess = returns - rf_daily
    std = float(returns.std(ddof=0)) if len(returns) else 0.0
    downside = returns[returns < rf_daily] - rf_daily
    downside_std = float(downside.std(ddof=0)) if len(downside) else 0.0
    sharpe = float(excess.mean() / std * math.sqrt(252)) if std > 0 else 0.0
    sortino = float(excess.mean() / downside_std * math.sqrt(252)) if downside_std > 0 else 0.0
    calmar = float(cagr / abs(max_dd)) if max_dd < 0 else 0.0
    sells = [t for t in trades if str(t.get("type")).upper() == "SELL"]
    pnls = [_safe_float(t.get("pnl")) for t in sells]
    pnl_pct = [_safe_float(t.get("pnl_pct")) for t in sells]
    r_vals = [_safe_float(t.get("r_multiple")) for t in sells]
    wins = [x for x in pnls if x > 0]
    losses = [x for x in pnls if x < 0]
    gross_profit, gross_loss = sum(wins), abs(sum(losses))
    costs = sum(_safe_float(t.get("commission")) for t in trades)
    return {
        "ending_value": round(float(vals.iloc[-1]), 2),
        "total_return_pct": round(total_return * 100.0, 2),
        "cagr_pct": round(cagr * 100.0, 2),
        "volatility_pct": round(std * math.sqrt(252) * 100.0, 2),
        "max_drawdown_pct": round(max_dd * 100.0, 2),
        "sharpe": round(sharpe, 2),
        "sortino": round(sortino, 2),
        "calmar": round(calmar, 2),
        "win_rate_pct": round(len(wins) / len(sells) * 100.0, 1) if sells else 0.0,
        "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss > 0 else round(gross_profit, 2),
        "expectancy_pct": round(sum(pnl_pct) / len(pnl_pct), 2) if pnl_pct else 0.0,
        "avg_r_multiple": round(sum(r_vals) / len(r_vals), 2) if r_vals else 0.0,
        "best_r_multiple": round(max(r_vals), 2) if r_vals else 0.0,
        "worst_r_multiple": round(min(r_vals), 2) if r_vals else 0.0,
        "exposure_pct": round(exposure_bars / max(1, total_bars) * 100.0, 1),
        "trades": float(len(sells)),
        "total_costs": round(costs, 2),
        "avg_holding_days": round(sum(_safe_float(t.get("holding_days")) for t in sells) / len(sells), 1) if sells else 0.0,
    }


def calculate_benchmark(frame: Any, start_capital: float) -> Dict[str, Any]:
    close = frame["close"].dropna()
    if close.empty:
        return {}
    curve = close / float(close.iloc[0]) * float(start_capital)
    years = max(len(curve) / 252.0, 1.0 / 252.0)
    total = curve.iloc[-1] / start_capital - 1.0
    cagr = (curve.iloc[-1] / start_capital) ** (1.0 / years) - 1.0
    dd = curve / curve.cummax() - 1.0
    return {
        "total_return_pct": round(float(total * 100.0), 2),
        "cagr_pct": round(float(cagr * 100.0), 2),
        "max_drawdown_pct": round(float(dd.min() * 100.0), 2),
        "equity": pd.DataFrame({"date": curve.index, "value": curve.values}).to_dict("records"),
    }


def calculate_monthly_returns(equity: Any) -> List[Dict[str, Any]]:
    if equity is None or equity.empty:
        return []
    values = equity["value"].copy()
    try:
        values.index = pd.to_datetime(values.index)
        monthly = values.resample("ME").last().pct_change().dropna() * 100.0
    except Exception:
        monthly = values.resample("M").last().pct_change().dropna() * 100.0
    return [{"month": str(idx.date()), "return_pct": round(float(value), 2)} for idx, value in monthly.items()]


def save_report(report: Mapping[str, Any]) -> None:
    payload = dict(report)
    for key in ("equity",):
        value = payload.get(key)
        if hasattr(value, "to_dict"):
            payload[key] = value.to_dict("records")
    _atomic_write(LATEST_REPORT_PATH, payload)


def render_backtesting_engine() -> None:
    import streamlit as st

    st.markdown("#### 📐 Backtesting Engine")
    st.caption(
        "Reproduserbar historisk simulering med neste-dags utførelse, kurtasje, slippage, benchmark og profesjonelle risiko-/avkastningsmål. "
        "Motoren er isolert fra Paper Trading og produksjonsregler."
    )
    strategies = load_strategies()
    names = [str(s.get("name")) for s in strategies]
    c1, c2, c3 = st.columns([1.0, 1.0, 1.0])
    with c1:
        ticker = st.text_input("Ticker", value="AAPL", key="bt_ticker_v18681").strip().upper()
        strategy_name = st.selectbox("Strategi", names, key="bt_strategy_v18681")
        period = st.selectbox("Historikk", ["1y", "2y", "5y", "10y", "max"], index=2, key="bt_period_v18681")
    with c2:
        capital = st.number_input("Startkapital", min_value=1000.0, value=100000.0, step=10000.0, key="bt_capital_v18681")
        commission = st.number_input("Kurtasje % per handel", min_value=0.0, value=0.05, step=0.01, format="%.2f", key="bt_commission_v18681")
        slippage = st.number_input("Slippage %", min_value=0.0, value=0.10, step=0.05, format="%.2f", key="bt_slippage_v18681")
    with c3:
        risk_free = st.number_input("Risikofri rente %", min_value=0.0, value=3.0, step=0.25, key="bt_rf_v18681")
        position_pct = st.slider("Kapital per posisjon %", 10, 100, 100, 5, key="bt_position_v18681")
        st.text_input("Utførelsesmodell", value="Signal ved close → handel neste open", disabled=True, key="bt_exec_label_v18681")

    if st.button("Kjør profesjonell backtest", type="primary", use_container_width=True, key="bt_run_v18681"):
        try:
            import yfinance as yf  # type: ignore
            with st.spinner(f"Henter {ticker} og simulerer {strategy_name} …"):
                data = yf.download(ticker, period=period, interval="1d", progress=False, auto_adjust=True)
                strategy = next(s for s in strategies if str(s.get("name")) == strategy_name)
                assumptions = ExecutionAssumptions(float(capital), float(commission), float(slippage), float(risk_free), float(position_pct))
                report = run_backtest(data, strategy, assumptions)
            st.session_state["backtest_report_v18681"] = report
            if report.get("ok"):
                save_report({k: v for k, v in report.items() if k != "equity"} | {"ticker": ticker, "period": period})
        except Exception as exc:
            st.session_state["backtest_report_v18681"] = {"ok": False, "error": str(exc)}

    report = st.session_state.get("backtest_report_v18681")
    if not report:
        st.info("Velg ticker, strategi og realistiske kostnadsforutsetninger, og kjør backtesten.")
        return
    if not report.get("ok"):
        st.error(f"Backtest feilet: {report.get('error', 'ukjent feil')}")
        return

    metrics = report.get("metrics") or {}
    benchmark = report.get("benchmark") or {}
    quality = report.get("data_quality") or {}
    r1 = st.columns(5)
    r1[0].metric("Avkastning", f"{metrics.get('total_return_pct', 0):.2f} %", delta=f"Benchmark {benchmark.get('total_return_pct', 0):.2f} %")
    r1[1].metric("CAGR", f"{metrics.get('cagr_pct', 0):.2f} %")
    r1[2].metric("Max Drawdown", f"{metrics.get('max_drawdown_pct', 0):.2f} %")
    r1[3].metric("Sharpe / Sortino", f"{metrics.get('sharpe', 0):.2f} / {metrics.get('sortino', 0):.2f}")
    r1[4].metric("Calmar", f"{metrics.get('calmar', 0):.2f}")
    r2 = st.columns(5)
    r2[0].metric("Treffprosent", f"{metrics.get('win_rate_pct', 0):.1f} %")
    r2[1].metric("Profit Factor", f"{metrics.get('profit_factor', 0):.2f}")
    r2[2].metric("Expectancy", f"{metrics.get('expectancy_pct', 0):.2f} %")
    r2[3].metric("Gj.snitt R", f"{metrics.get('avg_r_multiple', 0):.2f}R")
    r2[4].metric("Eksponering", f"{metrics.get('exposure_pct', 0):.1f} %")

    tab_curve, tab_trades, tab_risk, tab_audit = st.tabs(["Equity / benchmark", "Handler", "Risiko og måned", "Audit"])
    with tab_curve:
        eq = pd.DataFrame(report.get("equity") or [])
        bm = pd.DataFrame(benchmark.get("equity") or [])
        if not eq.empty:
            eq["date"] = pd.to_datetime(eq["date"])
            chart = eq.set_index("date")[["value"]].rename(columns={"value": "Strategi"})
            if not bm.empty:
                bm["date"] = pd.to_datetime(bm["date"])
                chart = chart.join(bm.set_index("date")[["value"]].rename(columns={"value": "Kjøp og hold"}), how="outer")
            st.line_chart(chart, use_container_width=True)
    with tab_trades:
        trades = pd.DataFrame(report.get("trades") or [])
        st.dataframe(trades, use_container_width=True, hide_index=True)
        if not trades.empty:
            st.download_button("Last ned handler CSV", trades.to_csv(index=False).encode("utf-8-sig"), f"backtest_trades_{ticker}.csv", "text/csv")
    with tab_risk:
        monthly = pd.DataFrame(report.get("monthly_returns") or [])
        if not monthly.empty:
            st.dataframe(monthly, use_container_width=True, hide_index=True)
            st.bar_chart(monthly.set_index("month")["return_pct"], use_container_width=True)
        st.json({k: metrics.get(k) for k in ("volatility_pct", "best_r_multiple", "worst_r_multiple", "avg_holding_days", "total_costs", "ending_value", "trades")})
    with tab_audit:
        st.success(f"Datakvalitet: {quality.get('quality_score', 0)}/100")
        if quality.get("issues"):
            st.warning(" • ".join(quality.get("issues") or []))
        st.json({
            "strategy_id": report.get("strategy_id"),
            "created_at": report.get("created_at"),
            "assumptions": report.get("assumptions"),
            "data_quality": quality,
            "look_ahead_protection": "Signal ved close, utførelse tidligst neste open",
            "production_impact": "NONE",
        })
        export = {k: v for k, v in report.items() if k != "equity"}
        st.download_button("Last ned komplett rapport JSON", json.dumps(export, ensure_ascii=False, indent=2, default=str).encode("utf-8"), f"backtest_{ticker}.json", "application/json")
