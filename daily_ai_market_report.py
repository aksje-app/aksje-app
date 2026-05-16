"""
daily_ai_market_report.py

v18.6.1 Daily AI Market Report:
- input-styrt rapport i stedet for ren cache-dump
- markedsvalg, fokus, horisont og topp-N
- unike tickere som standard, slik at én ticker ikke fyller hele rapporten
- ingen auto-trading-kobling
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Iterable

import streamlit as st

from alert_center import collect_common_alerts
from forecast_store import load_forecast_log, load_learning_stats, summarize_alerts


USA_SUFFIXES = (".OL", ".ST", ".CO", ".HE", ".DE", ".PA", ".AS", ".L")


def _today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _market_of_ticker(ticker: str) -> str:
    t = str(ticker or "").upper().strip()
    if t.endswith(".OL"):
        return "Norge"
    if t.endswith(".ST"):
        return "Sverige"
    if t.endswith((".CO", ".HE")):
        return "Norden"
    if "-USD" in t or t.endswith("USDT"):
        return "Crypto"
    if t and not t.endswith(USA_SUFFIXES):
        return "USA"
    return "Annet"


def _extract_forecast_rows(limit: int = 600) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    try:
        for payload in load_forecast_log(limit=limit):
            ticker = str(payload.get("ticker", "")).upper().strip()
            saved_at = payload.get("saved_at") or payload.get("generated_at", "")
            for horizon, item in (payload.get("horizons", {}) or {}).items():
                summary = (item or {}).get("summary", {}) or {}
                if not summary:
                    continue
                rows.append({
                    "ticker": ticker,
                    "market": _market_of_ticker(ticker),
                    "horizon": str(horizon),
                    "saved_at": saved_at,
                    "base_pct": float(summary.get("base_pct", 0) or 0),
                    "bull_pct": float(summary.get("bull_pct", 0) or 0),
                    "bear_pct": float(summary.get("bear_pct", 0) or 0),
                    "confidence": int(summary.get("confidence", 0) or 0),
                    "strength": int(summary.get("forecast_strength", 0) or 0),
                    "risk": summary.get("risk", ""),
                    "label": summary.get("forecast_strength_label", ""),
                })
    except Exception:
        return []

    latest: Dict[tuple, Dict[str, Any]] = {}
    for row in rows:
        latest[(row["ticker"], row["horizon"])] = row
    return list(latest.values())


def _portfolio_candidates_from_session() -> List[str]:
    """Best-effort: collect tickers already visible in portfolio/watchlist/session state."""
    out: List[str] = []
    for key in ("portfolio_positions", "positions", "paper_positions_v15", "paper_trading_positions", "watchlist", "watchlist_tickers"):
        val = st.session_state.get(key)
        if isinstance(val, list):
            for item in val:
                if isinstance(item, dict):
                    t = item.get("ticker") or item.get("symbol")
                else:
                    t = item
                if t:
                    out.append(str(t).upper().strip())
        elif isinstance(val, dict):
            for k, item in val.items():
                if isinstance(item, dict):
                    t = item.get("ticker") or item.get("symbol") or k
                else:
                    t = k
                if t:
                    out.append(str(t).upper().strip())
    # keep order, unique
    seen = set()
    clean = []
    for t in out:
        if t and t not in seen:
            seen.add(t)
            clean.append(t)
    return clean


def _filter_rows(rows: List[Dict[str, Any]], *, focus: str, market: str, horizon: str, manual: str) -> List[Dict[str, Any]]:
    manual_tickers = [x.strip().upper() for x in str(manual or "").replace(";", ",").split(",") if x.strip()]
    portfolio_tickers = _portfolio_candidates_from_session()

    filtered = list(rows)
    if market != "Alle":
        if market == "Multi-market":
            pass
        else:
            filtered = [r for r in filtered if r.get("market") == market]

    if horizon != "Alle":
        filtered = [r for r in filtered if str(r.get("horizon")) == horizon]

    if focus == "Manuelle tickere" and manual_tickers:
        filtered = [r for r in filtered if str(r.get("ticker", "")).upper() in manual_tickers]
    elif focus in ("Min portefølje", "Watchlist") and portfolio_tickers:
        filtered = [r for r in filtered if str(r.get("ticker", "")).upper() in portfolio_tickers]

    return filtered


def _unique_best_per_ticker(rows: Iterable[Dict[str, Any]], *, reverse: bool = True) -> List[Dict[str, Any]]:
    best: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        t = str(r.get("ticker", "")).upper()
        score = (int(r.get("strength", 0) or 0), int(r.get("confidence", 0) or 0), float(r.get("base_pct", 0) or 0))
        if t not in best:
            best[t] = r
            continue
        old = best[t]
        old_score = (int(old.get("strength", 0) or 0), int(old.get("confidence", 0) or 0), float(old.get("base_pct", 0) or 0))
        if (score > old_score and reverse) or (score < old_score and not reverse):
            best[t] = r
    return list(best.values())


def _top(rows: List[Dict[str, Any]], reverse: bool = True, limit: int = 10, unique: bool = True) -> List[Dict[str, Any]]:
    base = _unique_best_per_ticker(rows, reverse=reverse) if unique else rows
    return sorted(
        base,
        key=lambda r: (r.get("strength", 0), r.get("confidence", 0), r.get("base_pct", 0)),
        reverse=reverse,
    )[:limit]


def _fmt_pct(value: Any) -> str:
    try:
        return f"{float(value):+.2f}%"
    except Exception:
        return "0.00%"


def build_daily_market_report(*, focus: str = "Ranking toppkandidater", market: str = "Alle", horizon: str = "Alle", top_n: int = 10, unique: bool = True, manual_tickers: str = "") -> Dict[str, Any]:
    alerts = collect_common_alerts(limit=100)
    alert_summary = summarize_alerts(alerts) if alerts else {
        "counts": {"red": 0, "yellow": 0, "green": 0},
        "total": 0,
    }
    all_forecasts = _extract_forecast_rows(limit=600)
    forecasts = _filter_rows(all_forecasts, focus=focus, market=market, horizon=horizon, manual=manual_tickers)
    learning = load_learning_stats()

    try:
        auto_regime = st.session_state.get("market_regime_result_v1840")
    except Exception:
        auto_regime = None

    if isinstance(auto_regime, dict):
        regime_label = auto_regime.get("label", "Ukjent")
        regime_score = auto_regime.get("score", None)
        regime_confidence = auto_regime.get("confidence", None)
    else:
        regime_label = "Ikke oppdatert"
        regime_score = None
        regime_confidence = None

    counts = alert_summary.get("counts", {})
    try:
        macro_payload = st.session_state.get("macro_rates_breadth_result_v1844")
    except Exception:
        macro_payload = None

    return {
        "date": _today_key(),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "settings": {
            "focus": focus,
            "market": market,
            "horizon": horizon,
            "top_n": top_n,
            "unique": unique,
            "manual_tickers": manual_tickers,
            "available_forecasts_total": len(all_forecasts),
        },
        "regime": {"label": regime_label, "score": regime_score, "confidence": regime_confidence},
        "alerts": {
            "total": int(alert_summary.get("total", len(alerts))),
            "red": int(counts.get("red", 0)),
            "yellow": int(counts.get("yellow", 0)),
            "green": int(counts.get("green", 0)),
            "top": alerts[:10],
        },
        "forecasts": {
            "count": len(forecasts),
            "strongest": _top(forecasts, reverse=True, limit=top_n, unique=unique),
            "weakest": _top(forecasts, reverse=False, limit=top_n, unique=unique),
        },
        "learning": {
            "samples": int((learning.get("global", {}) or {}).get("count", 0) or 0),
            "direction_accuracy": (learning.get("global", {}) or {}).get("direction_accuracy"),
            "inside_band_accuracy": (learning.get("global", {}) or {}).get("inside_band_accuracy"),
            "avg_abs_error_pct": (learning.get("global", {}) or {}).get("avg_abs_error_pct"),
        },
        "macro": macro_payload if isinstance(macro_payload, dict) else {},
    }


def _rows_for_display(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for r in rows:
        out.append({
            "Ticker": r.get("ticker", ""),
            "Marked": r.get("market", ""),
            "Horisont": r.get("horizon", ""),
            "Base": _fmt_pct(r.get("base_pct")),
            "Bull": _fmt_pct(r.get("bull_pct")),
            "Bear": _fmt_pct(r.get("bear_pct")),
            "Confidence": f"{r.get('confidence', 0)}%",
            "Strength": f"{r.get('strength', 0)}/100",
            "Risiko": r.get("risk", ""),
        })
    return out


def render_daily_ai_market_report() -> None:
    st.markdown("### 📈 AI Market Briefing")
    with st.expander("⚙️ Rapportoppsett", expanded=True):
        c1, c2, c3, c4, c5 = st.columns([1.35, 1.0, 0.85, 0.70, 0.75])
        focus = c1.selectbox(
            "Fokus",
            ["Ranking toppkandidater", "Hele markedet", "Min portefølje", "Watchlist", "Manuelle tickere", "Risiko/advarsler"],
            key="daily_report_focus_v1861",
        )
        market = c2.selectbox("Marked", ["Alle", "USA", "Norge", "Sverige", "Norden", "Crypto", "Multi-market"], key="daily_report_market_v1861")
        horizon = c3.selectbox("Horisont", ["Alle", "1d", "1w", "1m", "3m", "6m"], index=3, key="daily_report_horizon_v1861")
        top_n = int(c4.number_input("Topp N", min_value=3, max_value=50, value=10, step=1, key="daily_report_topn_v1861"))
        unique = c5.checkbox("Unike tickere", value=True, key="daily_report_unique_v1861")
        manual_tickers = st.text_input("Manuelle tickere", value="AAPL,MSFT,NVDA", key="daily_report_manual_tickers_v1861", help="Brukes når Fokus = Manuelle tickere.")

        refresh = st.button("🔄 Oppdater AI Market Briefing", key="daily_ai_report_refresh_v1861", use_container_width=True, type="primary")

    report_key = f"daily_ai_market_report::{_today_key()}::{focus}::{market}::{horizon}::{top_n}::{unique}::{manual_tickers}"
    if refresh or report_key not in st.session_state:
        st.session_state[report_key] = build_daily_market_report(focus=focus, market=market, horizon=horizon, top_n=top_n, unique=unique, manual_tickers=manual_tickers)
    report = st.session_state[report_key]

    st.caption("Input-styrt daglig AI-rapport. Ingen auto-trading-kobling.")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Dato", report.get("date", ""))
    c2.metric("Fokus", report.get("settings", {}).get("focus", ""))
    c3.metric("Marked", report.get("settings", {}).get("market", ""))
    c4.metric("Prognoser", report.get("forecasts", {}).get("count", 0), f"av {report.get('settings', {}).get('available_forecasts_total', 0)}")
    c5.metric("Varsler", report.get("alerts", {}).get("total", 0), f"🔴 {report.get('alerts', {}).get('red', 0)} · 🟡 {report.get('alerts', {}).get('yellow', 0)} · 🟢 {report.get('alerts', {}).get('green', 0)}")

    st.markdown("### Kort status")
    regime = report.get("regime", {})
    alerts = report.get("alerts", {})
    learning = report.get("learning", {})
    settings = report.get("settings", {})
    st.write(
        f"Rapporten er bygget for **{settings.get('focus')}** / **{settings.get('market')}** / horisont **{settings.get('horizon')}**. "
        f"Regime: **{regime.get('label', 'Ukjent')}**. "
        f"Varsler: **{alerts.get('red', 0)} røde**, **{alerts.get('yellow', 0)} gule**, **{alerts.get('green', 0)} grønne**. "
        f"Læringsgrunnlag: **{learning.get('samples', 0)}** evaluerte punkter."
    )

    st.markdown("### Topp bullish / sterkeste prognoser")
    strongest = _rows_for_display(report.get("forecasts", {}).get("strongest", []))
    if strongest:
        st.dataframe(strongest, use_container_width=True, hide_index=True)
    else:
        st.info("Ingen prognoser matcher valgt rapportoppsett. Endre marked/horisont eller kjør flere prognoser.")

    st.markdown("### Topp risiko / svakeste prognoser")
    weakest = _rows_for_display(report.get("forecasts", {}).get("weakest", []))
    if weakest:
        st.dataframe(weakest, use_container_width=True, hide_index=True)
    else:
        st.caption("Ingen risikopunkter matcher valgt rapportoppsett.")

    st.markdown("### Viktigste varsler")
    top_alerts = report.get("alerts", {}).get("top", [])
    if top_alerts:
        rows = []
        for a in top_alerts:
            rows.append({
                "Nivå": str(a.get("level", "")).upper(),
                "Kilde": a.get("source", ""),
                "Ticker": a.get("ticker", ""),
                "Horisont": a.get("horizon", ""),
                "Kategori": a.get("category", ""),
                "Melding": a.get("message", ""),
            })
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.success("Ingen viktige varsler akkurat nå.")

    st.markdown("### Hvordan bruke rapporten")
    st.markdown(
        """
        - Velg først marked/fokus før du oppdaterer rapporten.
        - Bruk **Unike tickere** for å unngå at én ticker fyller hele rapporten med ulike horisonter.
        - Bruk sterkeste prognoser som kandidatliste, ikke fasit.
        - Sjekk svakeste prognoser og røde/gule varsler før nye kjøp.
        - Ikke koble dette direkte til auto trading uten backtest.
        """
    )
