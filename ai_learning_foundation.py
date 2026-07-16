from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from statistics import mean, median
from typing import Any

from paper_store import load_portfolio


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def build_trade_outcomes(portfolio: dict | None = None) -> list[dict]:
    portfolio = portfolio or load_portfolio()
    buys: dict[str, list[dict]] = defaultdict(list)
    outcomes: list[dict] = []
    for trade in portfolio.get("trades", []) or []:
        ticker = str(trade.get("ticker") or "").upper()
        typ = str(trade.get("type") or "").upper()
        if not ticker:
            continue
        if typ == "BUY":
            buys[ticker].append(dict(trade))
            continue
        if typ != "SELL" or not buys[ticker]:
            continue
        buy = buys[ticker].pop(0)
        entry = _f(buy.get("price"))
        exit_price = _f(trade.get("price"))
        ret = ((exit_price - entry) / entry * 100.0) if entry else _f(trade.get("pnl_pct"))
        try:
            t0 = datetime.fromisoformat(str(buy.get("time") or buy.get("opened_at") or ""))
            t1 = datetime.fromisoformat(str(trade.get("time") or ""))
            holding_days = max(0.0, (t1 - t0).total_seconds() / 86400.0)
        except Exception:
            holding_days = 0.0
        reason = str(trade.get("reason") or "SELL")
        outcomes.append({
            "ticker": ticker,
            "entry_time": buy.get("time", ""),
            "exit_time": trade.get("time", ""),
            "entry_price": entry,
            "exit_price": exit_price,
            "return_pct": round(ret, 3),
            "holding_days": round(holding_days, 2),
            "confidence": int(_f(buy.get("confidence"))),
            "signal": str(buy.get("reason") or buy.get("rule_used") or "BUY"),
            "exit_reason": reason,
            "exit_rule": str(trade.get("rule_used") or reason),
            "market": buy.get("market", ""),
            "sector": buy.get("sector", ""),
            "status": "READY",
        })
    return outcomes


def _max_drawdown(values: list[float]) -> float:
    equity = 100.0
    peak = equity
    worst = 0.0
    for value in values:
        equity *= 1 + value / 100.0
        peak = max(peak, equity)
        dd = (equity - peak) / peak * 100.0 if peak else 0.0
        worst = min(worst, dd)
    return round(worst, 3)


def learning_report(portfolio: dict | None = None) -> dict:
    outcomes = build_trade_outcomes(portfolio)
    returns = [_f(x.get("return_pct")) for x in outcomes]
    wins = [x for x in returns if x > 0]
    grouped_signal: dict[str, list[float]] = defaultdict(list)
    grouped_exit: dict[str, list[float]] = defaultdict(list)
    grouped_conf: dict[str, list[float]] = defaultdict(list)
    for row in outcomes:
        grouped_signal[str(row.get("signal") or "Ukjent")].append(_f(row.get("return_pct")))
        grouped_exit[str(row.get("exit_rule") or "Ukjent")].append(_f(row.get("return_pct")))
        c = int(_f(row.get("confidence")))
        bucket = f"{(c // 10) * 10}-{min(100, (c // 10) * 10 + 9)}"
        grouped_conf[bucket].append(_f(row.get("return_pct")))

    def summarize(grouped: dict[str, list[float]]) -> list[dict]:
        rows = []
        for name, vals in grouped.items():
            rows.append({
                "name": name,
                "observations": len(vals),
                "hit_rate_pct": round(sum(1 for v in vals if v > 0) / len(vals) * 100, 1) if vals else 0,
                "avg_return_pct": round(mean(vals), 3) if vals else 0,
                "median_return_pct": round(median(vals), 3) if vals else 0,
                "max_drawdown_pct": _max_drawdown(vals),
            })
        return sorted(rows, key=lambda x: (x["avg_return_pct"], x["observations"]), reverse=True)

    avg = mean(returns) if returns else 0.0
    downside = [min(0.0, x) for x in returns]
    downside_dev = (mean([x * x for x in downside]) ** 0.5) if downside else 0.0
    sharpe_proxy = avg / downside_dev if downside_dev else 0.0
    return {
        "version": "v18.6.75",
        "learning_loop": "OFF",
        "data_collection": "ON",
        "analysis": "ON",
        "automatic_rule_changes": "OFF",
        "metrics": {
            "observation_count": len(outcomes),
            "hit_rate_pct": round(len(wins) / len(returns) * 100, 1) if returns else 0,
            "average_return_pct": round(avg, 3),
            "median_return_pct": round(median(returns), 3) if returns else 0,
            "max_drawdown_pct": _max_drawdown(returns),
            "sharpe_proxy": round(sharpe_proxy, 3),
        },
        "learning_queue": outcomes,
        "signal_scorecard": summarize(grouped_signal),
        "confidence_calibration": summarize(grouped_conf),
        "exit_analytics": summarize(grouped_exit),
    }


def render_learning_foundation_tab() -> None:
    import json
    import streamlit as st
    try:
        import pandas as pd
    except Exception:
        pd = None

    st.markdown("#### AI Learning Foundation")
    st.caption("Passiv læring: datainnsamling, analyse og rapportering er aktive. Ingen handelsregler eller signalvekter endres automatisk.")
    report = learning_report()
    metrics = report["metrics"]
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Observasjoner", metrics["observation_count"])
    c2.metric("Hit rate", f"{metrics['hit_rate_pct']:.1f}%")
    c3.metric("Snitt", f"{metrics['average_return_pct']:.2f}%")
    c4.metric("Median", f"{metrics['median_return_pct']:.2f}%")
    c5.metric("Max DD", f"{metrics['max_drawdown_pct']:.2f}%")
    c6.metric("Sharpe proxy", f"{metrics['sharpe_proxy']:.2f}")

    tabs = st.tabs(["Learning Queue", "Signal Scorecard", "Confidence", "Exit Analytics", "Audit/Replay"])
    datasets = [report["learning_queue"], report["signal_scorecard"], report["confidence_calibration"], report["exit_analytics"]]
    for tab, rows in zip(tabs[:4], datasets):
        with tab:
            if rows:
                st.dataframe(pd.DataFrame(rows) if pd is not None else rows, use_container_width=True, hide_index=True)
            else:
                st.info("Ingen avsluttede handler tilgjengelig ennå.")
    with tabs[4]:
        queue = report["learning_queue"]
        if not queue:
            st.info("Ingen handler å spille av ennå.")
        else:
            labels = [f"{row['ticker']} · {row['entry_time']} → {row['exit_time']} · {row['return_pct']:.2f}%" for row in queue]
            selected = st.selectbox("Velg avsluttet handel", labels)
            st.json(queue[labels.index(selected)])
    st.download_button("Last ned Learning Foundation JSON", json.dumps(report, ensure_ascii=False, indent=2), "AI_LEARNING_FOUNDATION_REPORT.json", "application/json")
