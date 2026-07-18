"""Strategy Lab v18.6.80.

Safe, isolated strategy experimentation. The module does not modify Paper Trading,
production rules, signal weights or live decisions. Strategy definitions and the
latest lab runs are stored under the runtime data root.
"""
from __future__ import annotations

import json
import math
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from storage_architecture import runtime_data_path

try:
    import pandas as pd  # type: ignore
except Exception:  # pragma: no cover
    pd = None  # type: ignore

LAB_DIR = runtime_data_path("strategy_lab")
STRATEGIES_PATH = LAB_DIR / "strategies.json"
RUNS_PATH = LAB_DIR / "latest_runs.json"

DEFAULT_STRATEGIES: List[Dict[str, Any]] = [
    {
        "strategy_id": "MOMENTUM_V1",
        "name": "Momentum",
        "description": "Kjøper når kort trend og momentum er positivt.",
        "entry": {"fast_sma": 20, "slow_sma": 50, "momentum_days": 20, "momentum_min_pct": 2.0},
        "exit": {"stop_loss_pct": 8.0, "take_profit_pct": 20.0, "trailing_stop_pct": 10.0, "max_holding_days": 90},
        "risk": {"position_pct": 100.0},
        "enabled": True,
    },
    {
        "strategy_id": "SWING_V1",
        "name": "Swing",
        "description": "Raskere trendkryss med moderat gevinstmål.",
        "entry": {"fast_sma": 10, "slow_sma": 30, "momentum_days": 10, "momentum_min_pct": 0.5},
        "exit": {"stop_loss_pct": 6.0, "take_profit_pct": 12.0, "trailing_stop_pct": 7.0, "max_holding_days": 35},
        "risk": {"position_pct": 100.0},
        "enabled": True,
    },
    {
        "strategy_id": "AI_GROWTH_V1",
        "name": "AI Growth",
        "description": "Lang trend med høyere momentumkrav og romsligere target.",
        "entry": {"fast_sma": 30, "slow_sma": 100, "momentum_days": 60, "momentum_min_pct": 8.0},
        "exit": {"stop_loss_pct": 10.0, "take_profit_pct": 30.0, "trailing_stop_pct": 12.0, "max_holding_days": 180},
        "risk": {"position_pct": 100.0},
        "enabled": True,
    },
    {
        "strategy_id": "VALUE_TREND_V1",
        "name": "Value Trend",
        "description": "Rolig trendstrategi med lavt momentumkrav og lang horisont.",
        "entry": {"fast_sma": 50, "slow_sma": 150, "momentum_days": 90, "momentum_min_pct": 0.0},
        "exit": {"stop_loss_pct": 12.0, "take_profit_pct": 25.0, "trailing_stop_pct": 15.0, "max_holding_days": 250},
        "risk": {"position_pct": 100.0},
        "enabled": True,
    },
    {
        "strategy_id": "DEFENSIVE_V1",
        "name": "Defensive",
        "description": "Konservativ trendstrategi med strammere risikogrenser.",
        "entry": {"fast_sma": 20, "slow_sma": 100, "momentum_days": 30, "momentum_min_pct": 1.0},
        "exit": {"stop_loss_pct": 5.0, "take_profit_pct": 10.0, "trailing_stop_pct": 6.0, "max_holding_days": 75},
        "risk": {"position_pct": 100.0},
        "enabled": True,
    },
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _ensure_dir() -> None:
    LAB_DIR.mkdir(parents=True, exist_ok=True)


def _atomic_write(path: Path, payload: Any) -> None:
    _ensure_dir()
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def load_strategies() -> List[Dict[str, Any]]:
    _ensure_dir()
    if not STRATEGIES_PATH.exists():
        _atomic_write(STRATEGIES_PATH, DEFAULT_STRATEGIES)
        return deepcopy(DEFAULT_STRATEGIES)
    try:
        raw = json.loads(STRATEGIES_PATH.read_text(encoding="utf-8"))
        if isinstance(raw, list) and raw:
            return [dict(x) for x in raw if isinstance(x, Mapping)]
    except Exception:
        pass
    return deepcopy(DEFAULT_STRATEGIES)


def save_strategies(strategies: Sequence[Mapping[str, Any]]) -> None:
    cleaned = [dict(item) for item in strategies if isinstance(item, Mapping)]
    _atomic_write(STRATEGIES_PATH, cleaned)


def upsert_strategy(strategy: Mapping[str, Any]) -> Dict[str, Any]:
    item = dict(strategy)
    sid = str(item.get("strategy_id") or "").strip().upper().replace(" ", "_")
    if not sid:
        raise ValueError("strategy_id mangler")
    item["strategy_id"] = sid
    item["name"] = str(item.get("name") or sid).strip()
    item["updated_at"] = _now_iso()
    strategies = load_strategies()
    replaced = False
    for idx, existing in enumerate(strategies):
        if str(existing.get("strategy_id")) == sid:
            item.setdefault("created_at", existing.get("created_at") or _now_iso())
            strategies[idx] = item
            replaced = True
            break
    if not replaced:
        item.setdefault("created_at", _now_iso())
        strategies.append(item)
    save_strategies(strategies)
    return item


def _normalise_close(df: Any):
    if pd is None or df is None or not hasattr(df, "empty") or df.empty:
        return None
    out = df.copy()
    if getattr(out.columns, "nlevels", 1) > 1:
        close_col = next((c for c in out.columns if "Close" in [str(x) for x in (c if isinstance(c, tuple) else (c,))]), None)
        if close_col is None:
            return None
        close = out[close_col]
    elif "Close" in out.columns:
        close = out["Close"]
    else:
        return None
    close = pd.to_numeric(close, errors="coerce").dropna()
    if close.empty:
        return None
    return close


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def run_strategy_backtest(df: Any, strategy: Mapping[str, Any], start_value: float = 100000.0) -> Dict[str, Any]:
    """Run one long-only strategy against a daily Close series.

    Signals are evaluated using only information available on the current bar.
    Execution is at that bar's close. This is intentionally transparent and is
    a research simulator, not a production execution model.
    """
    close = _normalise_close(df)
    if close is None or len(close) < 5:
        return {"ok": False, "error": "For lite historikk", "strategy_id": strategy.get("strategy_id")}

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

    frame = pd.DataFrame({"close": close})
    frame["fast"] = frame["close"].rolling(fast).mean()
    frame["slow"] = frame["close"].rolling(slow).mean()
    frame["momentum"] = frame["close"].pct_change(mom_days)

    cash = float(start_value)
    shares = 0.0
    entry_price = 0.0
    entry_date = None
    highest = 0.0
    hold_days = 0
    trades: List[Dict[str, Any]] = []
    equity_rows: List[Dict[str, Any]] = []

    for idx, row in frame.iterrows():
        price = float(row["close"])
        in_position = shares > 0
        if in_position:
            highest = max(highest, price)
            hold_days += 1
            reason = ""
            if stop_loss and price <= entry_price * (1.0 - stop_loss):
                reason = "STOP_LOSS"
            elif trailing and price <= highest * (1.0 - trailing):
                reason = "TRAILING_STOP"
            elif take_profit and price >= entry_price * (1.0 + take_profit):
                reason = "TAKE_PROFIT"
            elif hold_days >= max_hold:
                reason = "TIME_EXIT"
            elif not math.isnan(float(row["fast"])) and not math.isnan(float(row["slow"])) and row["fast"] < row["slow"]:
                reason = "TREND_EXIT"
            if reason:
                proceeds = shares * price
                pnl = proceeds - (shares * entry_price)
                pnl_pct = (price / entry_price - 1.0) * 100.0 if entry_price else 0.0
                cash += proceeds
                trades.append({
                    "type": "SELL", "date": str(idx), "price": price, "shares": shares,
                    "pnl": pnl, "pnl_pct": pnl_pct, "reason": reason,
                    "entry_date": str(entry_date), "holding_days": hold_days,
                })
                shares = 0.0
                entry_price = 0.0
                entry_date = None
                highest = 0.0
                hold_days = 0
        if shares <= 0:
            ready = not (pd.isna(row["fast"]) or pd.isna(row["slow"]) or pd.isna(row["momentum"]))
            if ready and row["fast"] > row["slow"] and row["momentum"] >= mom_min:
                shares = cash / price if price > 0 else 0.0
                if shares > 0:
                    entry_price = price
                    entry_date = idx
                    highest = price
                    hold_days = 0
                    trades.append({"type": "BUY", "date": str(idx), "price": price, "shares": shares, "reason": "ENTRY_RULE"})
                    cash = 0.0
        equity_rows.append({"date": idx, "value": cash + shares * price})

    if shares > 0:
        price = float(close.iloc[-1])
        proceeds = shares * price
        pnl = proceeds - shares * entry_price
        pnl_pct = (price / entry_price - 1.0) * 100.0 if entry_price else 0.0
        cash += proceeds
        trades.append({
            "type": "SELL", "date": str(close.index[-1]), "price": price, "shares": shares,
            "pnl": pnl, "pnl_pct": pnl_pct, "reason": "END_OF_TEST",
            "entry_date": str(entry_date), "holding_days": hold_days,
        })
        equity_rows[-1]["value"] = cash

    equity = pd.DataFrame(equity_rows)
    metrics = calculate_metrics(equity, trades, start_value=start_value)
    return {
        "ok": True,
        "strategy_id": strategy.get("strategy_id"),
        "strategy_name": strategy.get("name"),
        "metrics": metrics,
        "trades": trades,
        "equity": equity,
    }


def calculate_metrics(equity: Any, trades: Sequence[Mapping[str, Any]], start_value: float = 100000.0) -> Dict[str, float]:
    if pd is None or equity is None or equity.empty:
        return {k: 0.0 for k in ("total_return_pct", "cagr_pct", "max_drawdown_pct", "sharpe", "sortino", "win_rate_pct", "profit_factor", "expectancy_pct", "trades")}
    vals = pd.to_numeric(equity["value"], errors="coerce").dropna()
    if vals.empty:
        return {}
    returns = vals.pct_change().dropna()
    total_return = (vals.iloc[-1] / float(start_value) - 1.0) * 100.0
    years = max(len(vals) / 252.0, 1.0 / 252.0)
    cagr = ((vals.iloc[-1] / float(start_value)) ** (1.0 / years) - 1.0) * 100.0 if vals.iloc[-1] > 0 else -100.0
    drawdown = vals / vals.cummax() - 1.0
    max_dd = float(drawdown.min() * 100.0)
    std = float(returns.std(ddof=0)) if len(returns) else 0.0
    sharpe = float((returns.mean() / std) * math.sqrt(252)) if std > 0 else 0.0
    downside = returns[returns < 0]
    downside_std = float(downside.std(ddof=0)) if len(downside) else 0.0
    sortino = float((returns.mean() / downside_std) * math.sqrt(252)) if downside_std > 0 else 0.0
    sells = [t for t in trades if str(t.get("type", "")).upper() == "SELL"]
    pnls_pct = [_safe_float(t.get("pnl_pct"), 0.0) for t in sells]
    wins = [x for x in pnls_pct if x > 0]
    losses = [x for x in pnls_pct if x < 0]
    win_rate = len(wins) / len(pnls_pct) * 100.0 if pnls_pct else 0.0
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = gross_win / gross_loss if gross_loss > 0 else (gross_win if gross_win > 0 else 0.0)
    expectancy = sum(pnls_pct) / len(pnls_pct) if pnls_pct else 0.0
    return {
        "total_return_pct": round(float(total_return), 2),
        "cagr_pct": round(float(cagr), 2),
        "max_drawdown_pct": round(max_dd, 2),
        "sharpe": round(sharpe, 2),
        "sortino": round(sortino, 2),
        "win_rate_pct": round(win_rate, 1),
        "profit_factor": round(float(profit_factor), 2),
        "expectancy_pct": round(float(expectancy), 2),
        "trades": float(len(sells)),
    }


def compare_strategies(df: Any, strategies: Sequence[Mapping[str, Any]], start_value: float = 100000.0) -> List[Dict[str, Any]]:
    results = []
    for strategy in strategies:
        result = run_strategy_backtest(df, strategy, start_value=start_value)
        if result.get("ok"):
            row = {"strategy_id": result.get("strategy_id"), "Strategi": result.get("strategy_name")}
            row.update(result.get("metrics") or {})
            row["_result"] = result
            results.append(row)
    return results


def save_latest_runs(payload: Mapping[str, Any]) -> None:
    serializable = dict(payload)
    for row in serializable.get("results", []) if isinstance(serializable.get("results"), list) else []:
        if isinstance(row, dict) and "_result" in row:
            row.pop("_result", None)
    _atomic_write(RUNS_PATH, serializable)


def render_strategy_lab() -> None:
    import streamlit as st

    st.markdown("#### 🧪 Testing – Strategy Lab")
    st.caption(
        "Isolert forskningsmiljø for å opprette og sammenligne strategier på samme historiske datasett. "
        "Resultater påvirker ikke Paper Trading, live-regler eller signalvekter."
    )
    strategies = load_strategies()
    enabled = [s for s in strategies if bool(s.get("enabled", True))]
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Strategier", len(strategies))
    k2.metric("Aktive i lab", len(enabled))
    k3.metric("Produksjonspåvirkning", "INGEN")
    k4.metric("Learning Loop", "OFF")

    tab_run, tab_library, tab_details = st.tabs(["Sammenlign", "Strategibibliotek", "Detaljer / handler"])
    with tab_run:
        c1, c2, c3 = st.columns([1.0, 0.8, 0.8])
        with c1:
            ticker = st.text_input("Ticker", value="AAPL", key="strategy_lab_ticker_v18680").strip().upper()
        with c2:
            period = st.selectbox("Historikk", ["6mo", "1y", "2y", "5y", "10y"], index=2, key="strategy_lab_period_v18680")
        with c3:
            start_value = st.number_input("Startkapital", min_value=1000.0, value=100000.0, step=10000.0, key="strategy_lab_capital_v18680")
        names = [str(s.get("name")) for s in strategies]
        selected_names = st.multiselect("Strategier", names, default=names[: min(5, len(names))], key="strategy_lab_selected_v18680")
        if st.button("Kjør Strategy Lab", type="primary", use_container_width=True, key="strategy_lab_run_v18680"):
            try:
                import yfinance as yf  # type: ignore
                with st.spinner(f"Henter {ticker} og kjører {len(selected_names)} strategier …"):
                    data = yf.download(ticker, period=period, interval="1d", progress=False, auto_adjust=True)
                    selected = [s for s in strategies if str(s.get("name")) in selected_names]
                    rows = compare_strategies(data, selected, start_value=float(start_value))
                st.session_state["strategy_lab_results_v18680"] = rows
                st.session_state["strategy_lab_meta_v18680"] = {"ticker": ticker, "period": period, "created_at": _now_iso()}
                save_latest_runs({"ticker": ticker, "period": period, "created_at": _now_iso(), "results": [{k: v for k, v in r.items() if k != "_result"} for r in rows]})
            except Exception as exc:
                st.error(f"Strategy Lab feilet: {exc}")
        rows = st.session_state.get("strategy_lab_results_v18680") or []
        if rows:
            display = []
            for r in rows:
                display.append({
                    "Strategi": r.get("Strategi"), "Avkastning %": r.get("total_return_pct"), "CAGR %": r.get("cagr_pct"),
                    "Treff %": r.get("win_rate_pct"), "Profit Factor": r.get("profit_factor"), "Max DD %": r.get("max_drawdown_pct"),
                    "Sharpe": r.get("sharpe"), "Sortino": r.get("sortino"), "Expectancy %": r.get("expectancy_pct"), "Handler": int(r.get("trades", 0)),
                })
            df_display = pd.DataFrame(display) if pd is not None else display
            st.dataframe(df_display, use_container_width=True, hide_index=True)
            if pd is not None:
                chart = pd.DataFrame({r.get("Strategi"): r.get("_result", {}).get("equity", pd.DataFrame()).set_index("date")["value"] for r in rows if r.get("_result", {}).get("equity") is not None})
                if not chart.empty:
                    st.line_chart(chart, use_container_width=True)
                st.download_button("Last ned sammenligning CSV", data=pd.DataFrame(display).to_csv(index=False).encode("utf-8-sig"), file_name=f"strategy_lab_{ticker}.csv", mime="text/csv")
        else:
            st.info("Velg strategier og kjør testen. Samme datasett brukes for alle strategiene.")

    with tab_library:
        st.dataframe(pd.DataFrame([{ "ID": s.get("strategy_id"), "Navn": s.get("name"), "Beskrivelse": s.get("description"), "Aktiv": s.get("enabled", True), "Entry": json.dumps(s.get("entry") or {}, ensure_ascii=False), "Exit": json.dumps(s.get("exit") or {}, ensure_ascii=False)} for s in strategies]) if pd is not None else strategies, use_container_width=True, hide_index=True)
        with st.expander("Opprett eller oppdater strategi", expanded=False):
            c1, c2 = st.columns(2)
            with c1:
                sid = st.text_input("Strategi-ID", value="CUSTOM_STRATEGY_V1", key="strategy_lab_id_v18680")
                name = st.text_input("Navn", value="Egendefinert strategi", key="strategy_lab_name_v18680")
                fast = st.number_input("Fast SMA", min_value=2, value=20, key="strategy_lab_fast_v18680")
                slow = st.number_input("Slow SMA", min_value=3, value=50, key="strategy_lab_slow_v18680")
                mom_days = st.number_input("Momentum-dager", min_value=1, value=20, key="strategy_lab_mom_days_v18680")
                mom_min = st.number_input("Min momentum %", value=2.0, step=0.5, key="strategy_lab_mom_min_v18680")
            with c2:
                stop = st.number_input("Stop loss %", min_value=0.0, value=8.0, step=0.5, key="strategy_lab_stop_v18680")
                target = st.number_input("Take profit %", min_value=0.0, value=20.0, step=1.0, key="strategy_lab_target_v18680")
                trail = st.number_input("Trailing stop %", min_value=0.0, value=10.0, step=0.5, key="strategy_lab_trail_v18680")
                hold = st.number_input("Maks holdingdager", min_value=1, value=90, key="strategy_lab_hold_v18680")
                enabled_value = st.checkbox("Aktiv i lab", value=True, key="strategy_lab_enabled_v18680")
            description = st.text_area("Beskrivelse", value="Teststrategi. Påvirker ikke produksjon.", key="strategy_lab_desc_v18680")
            if st.button("Lagre strategi", key="strategy_lab_save_v18680"):
                try:
                    if int(slow) <= int(fast):
                        raise ValueError("Slow SMA må være større enn Fast SMA")
                    upsert_strategy({
                        "strategy_id": sid, "name": name, "description": description, "enabled": enabled_value,
                        "entry": {"fast_sma": int(fast), "slow_sma": int(slow), "momentum_days": int(mom_days), "momentum_min_pct": float(mom_min)},
                        "exit": {"stop_loss_pct": float(stop), "take_profit_pct": float(target), "trailing_stop_pct": float(trail), "max_holding_days": int(hold)},
                        "risk": {"position_pct": 100.0},
                    })
                    st.success("Strategi lagret i runtime-data.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Kunne ikke lagre strategi: {exc}")

    with tab_details:
        rows = st.session_state.get("strategy_lab_results_v18680") or []
        if not rows:
            st.info("Kjør en sammenligning først.")
        else:
            selected = st.selectbox("Strategi", [r.get("Strategi") for r in rows], key="strategy_lab_detail_v18680")
            row = next((r for r in rows if r.get("Strategi") == selected), None)
            result = (row or {}).get("_result") or {}
            trades = result.get("trades") or []
            if trades:
                st.dataframe(pd.DataFrame(trades) if pd is not None else trades, use_container_width=True, hide_index=True)
            else:
                st.info("Ingen avsluttede handler i valgt periode.")
            st.json({"strategy_id": result.get("strategy_id"), "metrics": result.get("metrics")})
