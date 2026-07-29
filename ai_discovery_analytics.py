from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from statistics import mean, median
from typing import Any, Iterable

from ai_learning_foundation import build_trade_outcomes


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _max_drawdown(values: Iterable[float]) -> float:
    equity = 100.0
    peak = equity
    worst = 0.0
    for value in values:
        equity *= 1.0 + float(value) / 100.0
        peak = max(peak, equity)
        if peak:
            worst = min(worst, (equity - peak) / peak * 100.0)
    return round(worst, 3)


def _profit_factor(values: list[float]) -> float:
    gains = sum(v for v in values if v > 0)
    losses = abs(sum(v for v in values if v < 0))
    if losses == 0:
        return round(gains, 3) if gains else 0.0
    return round(gains / losses, 3)


def _summarize(name: str, values: list[float]) -> dict:
    wins = [v for v in values if v > 0]
    return {
        "name": name or "Ukjent",
        "observations": len(values),
        "hit_rate_pct": round(len(wins) / len(values) * 100.0, 1) if values else 0.0,
        "avg_return_pct": round(mean(values), 3) if values else 0.0,
        "median_return_pct": round(median(values), 3) if values else 0.0,
        "max_drawdown_pct": _max_drawdown(values),
        "profit_factor": _profit_factor(values),
    }


def _group(outcomes: list[dict], key_fn) -> list[dict]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in outcomes:
        grouped[str(key_fn(row) or "Ukjent")].append(_f(row.get("return_pct")))
    rows = [_summarize(name, vals) for name, vals in grouped.items()]
    return sorted(rows, key=lambda x: (x["avg_return_pct"], x["observations"]), reverse=True)


def _holding_bucket(days: float) -> str:
    if days <= 5:
        return "0-5 dager"
    if days <= 15:
        return "6-15 dager"
    if days <= 30:
        return "16-30 dager"
    if days <= 60:
        return "31-60 dager"
    return "60+ dager"


def _confidence_bucket(value: float) -> str:
    c = int(value)
    if c < 60:
        return "50-59"
    if c < 70:
        return "60-69"
    if c < 80:
        return "70-79"
    if c < 90:
        return "80-89"
    return "90+"


def _parse_time(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _signal_health(outcomes: list[dict], window: int = 30) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in outcomes:
        grouped[str(row.get("signal") or "Ukjent")].append(row)
    rows: list[dict] = []
    for signal, items in grouped.items():
        items = sorted(items, key=lambda x: str(x.get("exit_time") or ""))
        recent = [_f(x.get("return_pct")) for x in items[-window:]]
        previous = [_f(x.get("return_pct")) for x in items[-2 * window:-window]]
        recent_hit = sum(v > 0 for v in recent) / len(recent) * 100.0 if recent else 0.0
        previous_hit = sum(v > 0 for v in previous) / len(previous) * 100.0 if previous else 0.0
        delta = recent_hit - previous_hit if previous else 0.0
        trend = "FORBEDRES" if previous and delta >= 5 else "SVEKKES" if previous and delta <= -5 else "STABIL"
        rows.append({
            "signal": signal,
            "recent_observations": len(recent),
            "recent_hit_rate_pct": round(recent_hit, 1),
            "previous_hit_rate_pct": round(previous_hit, 1),
            "delta_pp": round(delta, 1),
            "trend": trend,
        })
    return sorted(rows, key=lambda x: (x["delta_pp"], x["recent_observations"]), reverse=True)


def _recommendations(report: dict) -> list[str]:
    recs: list[str] = []
    for label, key in [("signal", "signal_leaderboard"), ("marked", "market_leaderboard"), ("sektor", "sector_leaderboard")]:
        rows = report.get(key) or []
        if rows:
            best = rows[0]
            recs.append(f"Beste {label} i måleperioden er {best['name']} med {best['avg_return_pct']:.2f}% snitt og {best['hit_rate_pct']:.1f}% hit rate ({best['observations']} observasjoner).")
            if len(rows) > 1 and rows[-1]["observations"] >= 5:
                weak = rows[-1]
                recs.append(f"{weak['name']} er svakest målt {label}; vurder videre observasjon før eventuell vektendring. Ingen endring utføres automatisk.")
    weakening = [x for x in report.get("signal_health", []) if x.get("trend") == "SVEKKES"]
    if weakening:
        recs.append(f"{weakening[0]['signal']} viser svekkende signalhelse ({weakening[0]['delta_pp']:.1f} prosentpoeng).")
    if not recs:
        recs.append("Datagrunnlaget er foreløpig for lite til sterke anbefalinger. Fortsett passiv innsamling.")
    return recs[:6]


def discovery_analytics_report(portfolio: dict | None = None) -> dict:
    outcomes = build_trade_outcomes(portfolio)
    returns = [_f(x.get("return_pct")) for x in outcomes]
    signal = _group(outcomes, lambda x: x.get("signal"))
    market = _group(outcomes, lambda x: x.get("market") or "Ukjent")
    sector = _group(outcomes, lambda x: x.get("sector") or "Ukjent")
    holding = _group(outcomes, lambda x: _holding_bucket(_f(x.get("holding_days"))))
    confidence = _group(outcomes, lambda x: _confidence_bucket(_f(x.get("confidence"))))
    exit_rows = _group(outcomes, lambda x: x.get("exit_rule") or x.get("exit_reason"))
    strategy = _group(outcomes, lambda x: x.get("strategy") or x.get("signal") or "Ukjent")
    report = {
        "version": "v18.6.79",
        "mode": {
            "data_collection": "ON",
            "analysis": "ON",
            "recommendations": "ON",
            "automatic_optimization": "OFF",
            "automatic_rule_changes": "OFF",
            "automatic_signal_weight_changes": "OFF",
        },
        "metrics": _summarize("Alle handler", returns),
        "signal_leaderboard": signal,
        "signal_health": _signal_health(outcomes),
        "market_leaderboard": market,
        "sector_leaderboard": sector,
        "holding_time_analytics": holding,
        "confidence_analytics": confidence,
        "strategy_comparison": strategy,
        "exit_analytics": exit_rows,
        "trade_replay": outcomes,
    }
    report["recommendations"] = _recommendations(report)
    now = datetime.now().astimezone()
    week_start = now - timedelta(days=7)
    week_rows = [x for x in outcomes if (_parse_time(x.get("exit_time")) or datetime.min.replace(tzinfo=now.tzinfo)) >= week_start]
    report["weekly_report"] = {
        "generated_at": now.isoformat(timespec="seconds"),
        "closed_trades_last_7_days": len(week_rows),
        "observations": report["recommendations"],
        "notice": "Ingen automatiske endringer er gjort.",
    }
    return report


def render_ai_discovery_analytics_tab() -> None:
    import json
    import streamlit as st
    try:
        import pandas as pd
    except Exception:
        pd = None

    report = discovery_analytics_report()
    st.markdown("#### AI Discovery Analytics & Intelligence")
    st.caption("Observerer, rangerer, sammenligner og foreslår. Automatisk optimalisering og regelendring er AV.")

    mode = report["mode"]
    with st.expander("Learning Mode / sikkerhetsgrenser", expanded=False):
        st.json(mode)

    metrics = report["metrics"]
    cols = st.columns(6)
    cols[0].metric("Handler", metrics["observations"])
    cols[1].metric("Hit rate", f"{metrics['hit_rate_pct']:.1f}%")
    cols[2].metric("Snitt", f"{metrics['avg_return_pct']:.2f}%")
    cols[3].metric("Median", f"{metrics['median_return_pct']:.2f}%")
    cols[4].metric("Profit factor", f"{metrics['profit_factor']:.2f}")
    cols[5].metric("Max DD", f"{metrics['max_drawdown_pct']:.2f}%")

    tabs = st.tabs(["Dashboard", "Signaler", "Marked/sektor", "Confidence/holding", "Strategi/exit", "Replay", "Ukesrapport"])

    def show(rows):
        if rows:
            st.dataframe(pd.DataFrame(rows) if pd is not None else rows, use_container_width=True, hide_index=True)
        else:
            st.info("Ingen avsluttede handler tilgjengelig ennå.")

    with tabs[0]:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("##### Beste signaler")
            show(report["signal_leaderboard"][:5])
        with c2:
            st.markdown("##### AI-anbefalinger")
            for item in report["recommendations"]:
                st.info(item)

    with tabs[1]:
        st.markdown("##### Signal Leaderboard")
        show(report["signal_leaderboard"])
        st.markdown("##### Signal Health")
        show(report["signal_health"])

    with tabs[2]:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("##### Market Leaderboard")
            show(report["market_leaderboard"])
        with c2:
            st.markdown("##### Sector Analytics")
            show(report["sector_leaderboard"])

    with tabs[3]:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("##### Confidence Calibration")
            show(report["confidence_analytics"])
        with c2:
            st.markdown("##### Holding Time Analytics")
            show(report["holding_time_analytics"])

    with tabs[4]:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("##### Strategy Comparison")
            show(report["strategy_comparison"])
        with c2:
            st.markdown("##### Exit Analytics")
            show(report["exit_analytics"])

    with tabs[5]:
        rows = report["trade_replay"]
        if not rows:
            st.info("Ingen handler å spille av ennå.")
        else:
            labels = [f"{x['ticker']} · {x.get('entry_time','')} → {x.get('exit_time','')} · {x.get('return_pct',0):.2f}%" for x in rows]
            chosen = st.selectbox("Velg handel", labels, key="ai_disc_analytics_replay_v18679")
            st.json(rows[labels.index(chosen)])

    with tabs[6]:
        weekly = report["weekly_report"]
        st.metric("Avsluttede handler siste 7 dager", weekly["closed_trades_last_7_days"])
        for item in weekly["observations"]:
            st.write(f"- {item}")
        st.success(weekly["notice"])

    st.download_button(
        "Last ned AI Discovery Analytics JSON",
        json.dumps(report, ensure_ascii=False, indent=2),
        "AI_DISCOVERY_ANALYTICS_V18_6_79.json",
        "application/json",
    )
