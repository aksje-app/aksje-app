from __future__ import annotations

import io
import json
import re
from collections import defaultdict, deque
from datetime import datetime
from itertools import combinations
from statistics import mean, median
from typing import Any

from paper_store import load_portfolio

VERSION = "v18.6.79"


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _dt(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except Exception:
        return None


def _tokens(trade: dict) -> list[str]:
    aliases = {
        "momentum": "Momentum", "trend": "Trend", "volume": "Volum", "volum": "Volum",
        "insider": "Insider", "ownership": "Ownership", "eierskap": "Ownership",
        "sentiment": "Sentiment", "rsi": "RSI", "analyst": "Analyst", "analytiker": "Analyst",
        "breakout": "Breakout", "quality": "Quality", "kvalitet": "Quality",
        "volatility": "Lav volatilitet", "volatilitet": "Lav volatilitet",
    }
    text_parts = [str(trade.get(k) or "") for k in ("reason", "rule_used", "measured_value", "trade_explanation")]
    raw = trade.get("signals") or trade.get("features") or trade.get("context")
    if isinstance(raw, dict):
        text_parts.extend(str(k) for k, v in raw.items() if bool(v))
    elif isinstance(raw, (list, tuple, set)):
        text_parts.extend(str(x) for x in raw)
    text = " ".join(text_parts).lower()
    found = {label for key, label in aliases.items() if re.search(rf"\b{re.escape(key)}\b", text)}
    return sorted(found) or [str(trade.get("rule_used") or trade.get("reason") or "BUY")[:80]]


def build_trade_outcomes(portfolio: dict | None = None) -> list[dict]:
    """Match BUY lots to SELL quantities (FIFO), including partial exits."""
    portfolio = portfolio or load_portfolio()
    lots: dict[str, deque[dict]] = defaultdict(deque)
    outcomes: list[dict] = []
    trades = sorted((dict(t) for t in (portfolio.get("trades", []) or [])), key=lambda t: str(t.get("time") or ""))
    for trade in trades:
        ticker = str(trade.get("ticker") or "").upper().strip()
        typ = str(trade.get("type") or "").upper().strip()
        if not ticker:
            continue
        qty = abs(_f(trade.get("shares") or trade.get("quantity")))
        if typ == "BUY":
            lots[ticker].append({"trade": trade, "remaining": qty or 1.0})
            continue
        if typ != "SELL" or not lots[ticker]:
            continue
        remaining_sell = qty or sum(x["remaining"] for x in lots[ticker])
        while remaining_sell > 1e-9 and lots[ticker]:
            lot = lots[ticker][0]
            matched = min(remaining_sell, lot["remaining"])
            buy = lot["trade"]
            entry, exit_price = _f(buy.get("price")), _f(trade.get("price"))
            ret = ((exit_price - entry) / entry * 100.0) if entry else _f(trade.get("pnl_pct"))
            t0, t1 = _dt(buy.get("time") or buy.get("opened_at")), _dt(trade.get("time"))
            holding_days = max(0.0, (t1 - t0).total_seconds() / 86400.0) if t0 and t1 else 0.0
            risk = _f(buy.get("initial_risk_amount") or buy.get("risk_amount"))
            pnl_amount = (exit_price - entry) * matched
            r_multiple = pnl_amount / risk if risk else _f(trade.get("r_multiple"))
            signals = _tokens(buy)
            outcomes.append({
                "ticker": ticker, "entry_time": buy.get("time", ""), "exit_time": trade.get("time", ""),
                "entry_price": round(entry, 4), "exit_price": round(exit_price, 4), "shares": round(matched, 6),
                "return_pct": round(ret, 3), "pnl_amount": round(pnl_amount, 2), "r_multiple": round(r_multiple, 3),
                "holding_days": round(holding_days, 2), "confidence": int(_f(buy.get("confidence"))),
                "signals": signals, "signal": " + ".join(signals),
                "exit_reason": str(trade.get("reason") or "SELL"),
                "exit_rule": str(trade.get("rule_used") or trade.get("reason") or "SELL"),
                "market": buy.get("market", ""), "sector": buy.get("sector", "") or "Ukjent",
                "entry_explanation": buy.get("trade_explanation", ""),
                "exit_explanation": trade.get("trade_explanation", ""), "status": "READY",
            })
            lot["remaining"] -= matched
            remaining_sell -= matched
            if lot["remaining"] <= 1e-9:
                lots[ticker].popleft()
    return outcomes


def _max_drawdown(values: list[float]) -> float:
    equity = peak = 100.0
    worst = 0.0
    for value in values:
        equity *= 1 + value / 100.0
        peak = max(peak, equity)
        worst = min(worst, ((equity - peak) / peak * 100.0) if peak else 0.0)
    return round(worst, 3)


def _summary(name: str, rows: list[dict]) -> dict:
    vals = [_f(x.get("return_pct")) for x in rows]
    wins = [v for v in vals if v > 0]
    losses = [v for v in vals if v < 0]
    gross_profit, gross_loss = sum(wins), abs(sum(losses))
    return {
        "name": name, "observations": len(rows),
        "hit_rate_pct": round(len(wins) / len(vals) * 100, 1) if vals else 0.0,
        "avg_return_pct": round(mean(vals), 3) if vals else 0.0,
        "median_return_pct": round(median(vals), 3) if vals else 0.0,
        "avg_r_multiple": round(mean([_f(x.get("r_multiple")) for x in rows]), 3) if rows else 0.0,
        "avg_holding_days": round(mean([_f(x.get("holding_days")) for x in rows]), 2) if rows else 0.0,
        "profit_factor": round(gross_profit / gross_loss, 3) if gross_loss else (999.0 if gross_profit else 0.0),
        "max_drawdown_pct": _max_drawdown(vals),
    }


def _group(outcomes: list[dict], key_fn) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in outcomes:
        for key in key_fn(row):
            grouped[str(key or "Ukjent")].append(row)
    return sorted((_summary(k, v) for k, v in grouped.items()), key=lambda x: (x["avg_return_pct"], x["observations"]), reverse=True)


def _insights(report: dict) -> list[str]:
    insights: list[str] = []
    for label, key in (("signal", "signal_scorecard"), ("signalkombinasjon", "combination_analysis"), ("sektor", "sector_analysis"), ("exit-regel", "exit_analytics")):
        rows = [r for r in report.get(key, []) if r.get("observations", 0) >= 2]
        if rows:
            best = max(rows, key=lambda r: (r["avg_return_pct"], r["hit_rate_pct"]))
            insights.append(f"Beste {label} i datagrunnlaget er {best['name']} med {best['hit_rate_pct']:.1f}% treff og {best['avg_return_pct']:.2f}% gjennomsnittlig avkastning ({best['observations']} observasjoner).")
    conf = report.get("confidence_calibration", [])
    if len(conf) >= 2:
        insights.append("Confidence-kalibreringen bør vurderes mot faktisk treffprosent; høyere score er bare nyttig dersom realisert treffprosent også stiger.")
    if not insights:
        insights.append("Datagrunnlaget er foreløpig for lite til robuste mønstre. Samle flere avsluttede handler før konklusjoner brukes i beslutningsstøtte.")
    insights.append("Learning Loop er AV: innsikten endrer ingen regler, vekter eller handler automatisk.")
    return insights


def learning_report(portfolio: dict | None = None) -> dict:
    outcomes = build_trade_outcomes(portfolio)
    vals = [_f(x.get("return_pct")) for x in outcomes]
    wins, losses = [v for v in vals if v > 0], [v for v in vals if v < 0]
    gross_profit, gross_loss = sum(wins), abs(sum(losses))
    combinations_rows = _group(outcomes, lambda r: [" + ".join(c) for n in (2, 3) for c in combinations(r.get("signals") or [], n)])
    metrics = {
        "trade_count": len(outcomes), "winners": len(wins), "losers": len(losses),
        "hit_rate_pct": round(len(wins) / len(vals) * 100, 1) if vals else 0.0,
        "average_return_pct": round(mean(vals), 3) if vals else 0.0,
        "average_win_pct": round(mean(wins), 3) if wins else 0.0,
        "average_loss_pct": round(mean(losses), 3) if losses else 0.0,
        "profit_factor": round(gross_profit / gross_loss, 3) if gross_loss else (999.0 if gross_profit else 0.0),
        "expectancy_pct": round(mean(vals), 3) if vals else 0.0,
        "average_holding_days": round(mean([_f(x.get("holding_days")) for x in outcomes]), 2) if outcomes else 0.0,
        "average_r_multiple": round(mean([_f(x.get("r_multiple")) for x in outcomes]), 3) if outcomes else 0.0,
        "max_drawdown_pct": _max_drawdown(vals),
        "best_trade_pct": round(max(vals), 3) if vals else 0.0, "worst_trade_pct": round(min(vals), 3) if vals else 0.0,
    }
    report = {
        "version": VERSION, "learning_loop": "OFF", "analysis": "ON", "automatic_rule_changes": "OFF",
        "metrics": metrics, "trade_outcomes": outcomes,
        "signal_scorecard": _group(outcomes, lambda r: r.get("signals") or ["Ukjent"]),
        "combination_analysis": combinations_rows,
        "exit_analytics": _group(outcomes, lambda r: [r.get("exit_rule") or "Ukjent"]),
        "sector_analysis": _group(outcomes, lambda r: [r.get("sector") or "Ukjent"]),
        "confidence_calibration": _group(outcomes, lambda r: [f"{min(90, int(_f(r.get('confidence'))) // 10 * 10)}-{min(100, min(90, int(_f(r.get('confidence'))) // 10 * 10) + 9)}"]),
    }
    report["insights"] = _insights(report)
    return report


def _excel_bytes(report: dict) -> bytes | None:
    try:
        import pandas as pd
        out = io.BytesIO()
        with pd.ExcelWriter(out, engine="openpyxl") as writer:
            pd.DataFrame([report["metrics"]]).to_excel(writer, "Nokkeltall", index=False)
            for name, key in (("Handler", "trade_outcomes"), ("Signaler", "signal_scorecard"), ("Kombinasjoner", "combination_analysis"), ("Exits", "exit_analytics"), ("Sektorer", "sector_analysis"), ("Confidence", "confidence_calibration")):
                pd.DataFrame(report[key]).to_excel(writer, name[:31], index=False)
        return out.getvalue()
    except Exception:
        return None


def render_learning_foundation_tab() -> None:
    import streamlit as st
    try:
        import pandas as pd
    except Exception:
        pd = None

    st.markdown("#### 📈 Analyse – AI Discovery Analytics")
    st.caption("Passiv resultat- og mønsteranalyse av Paper Trading. Learning Loop er AV; ingen handelsregler eller signalvekter endres automatisk.")
    report = learning_report()
    m = report["metrics"]
    cols = st.columns(6)
    for col, label, value in zip(cols, ["Handler", "Treff", "Profit factor", "Expectancy", "Snitt R", "Holding"], [m["trade_count"], f"{m['hit_rate_pct']:.1f}%", f"{m['profit_factor']:.2f}", f"{m['expectancy_pct']:.2f}%", f"{m['average_r_multiple']:.2f}R", f"{m['average_holding_days']:.1f} d"]):
        col.metric(label, value)
    st.caption(f"Vinnere/tapere: {m['winners']}/{m['losers']} · Snitt gevinst {m['average_win_pct']:.2f}% · Snitt tap {m['average_loss_pct']:.2f}% · Max DD {m['max_drawdown_pct']:.2f}%")

    tabs = st.tabs(["Oversikt", "Signal Scorecard", "Kombinasjoner", "Exit Analytics", "Sektorer", "Confidence", "Replay", "AI Insights", "Eksport"])
    with tabs[0]:
        rows = report["trade_outcomes"]
        st.dataframe(pd.DataFrame(rows) if pd is not None else rows, width="stretch", hide_index=True) if rows else st.info("Ingen avsluttede handler tilgjengelig ennå.")
    for tab, key in zip(tabs[1:6], ["signal_scorecard", "combination_analysis", "exit_analytics", "sector_analysis", "confidence_calibration"]):
        with tab:
            rows = report[key]
            st.dataframe(pd.DataFrame(rows) if pd is not None else rows, width="stretch", hide_index=True) if rows else st.info("Ikke nok data for denne analysen ennå.")
    with tabs[6]:
        queue = report["trade_outcomes"]
        if not queue:
            st.info("Ingen handler å spille av ennå.")
        else:
            labels = [f"{r['ticker']} · {r['entry_time']} → {r['exit_time']} · {r['return_pct']:.2f}%" for r in queue]
            row = queue[labels.index(st.selectbox("Velg avsluttet handel", labels))]
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Entry", row["entry_price"]); c2.metric("Exit", row["exit_price"]); c3.metric("Resultat", f"{row['return_pct']:.2f}%"); c4.metric("R", f"{row['r_multiple']:.2f}R")
            st.json(row)
    with tabs[7]:
        for insight in report["insights"]:
            st.info(insight)
    with tabs[8]:
        st.download_button("Last ned JSON", json.dumps(report, ensure_ascii=False, indent=2), "AI_DISCOVERY_ANALYTICS_v18_6_79.json", "application/json")
        if pd is not None:
            csv_data = pd.DataFrame(report["trade_outcomes"]).to_csv(index=False).encode("utf-8-sig")
            st.download_button("Last ned CSV", csv_data, "AI_DISCOVERY_TRADES_v18_6_79.csv", "text/csv")
        xlsx = _excel_bytes(report)
        if xlsx:
            st.download_button("Last ned Excel", xlsx, "AI_DISCOVERY_ANALYTICS_v18_6_79.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        st.caption("PDF/utskrift: bruk nettleserens Skriv ut → Lagre som PDF fra denne fanen.")
