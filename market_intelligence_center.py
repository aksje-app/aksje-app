"""
market_intelligence_center.py

AI Market Intelligence Center:
- samlet oversikt over varsler, prognoser, learning stats og portefølje/paper-status
- ingen auto-trading-kobling
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import streamlit as st

from alert_center import collect_common_alerts
from forecast_store import load_forecast_log, load_learning_stats, summarize_alerts
from security_metadata import infer_security_listing, resolve_security_metadata


def _safe_pct(value: Any) -> str:
    try:
        return f"{float(value):+.2f}%"
    except Exception:
        return "0.00%"


def _extract_latest_summaries(limit: int = 200) -> List[Dict[str, Any]]:
    rows = []
    try:
        for payload in load_forecast_log(limit=limit):
            ticker = payload.get("ticker", "")
            horizons = payload.get("horizons", {})
            saved_at = payload.get("saved_at") or payload.get("generated_at", "")
            for horizon, item in horizons.items():
                summary = item.get("summary", {})
                if not summary:
                    continue
                rows.append({
                    "ticker": ticker,
                    "horizon": horizon,
                    "saved_at": saved_at,
                    "base_pct": float(summary.get("base_pct", 0)),
                    "bull_pct": float(summary.get("bull_pct", 0)),
                    "bear_pct": float(summary.get("bear_pct", 0)),
                    "confidence": int(summary.get("confidence", 0)),
                    "strength": int(summary.get("forecast_strength", 0)),
                    "risk": summary.get("risk", ""),
                    "label": summary.get("forecast_strength_label", ""),
                })
    except Exception:
        return []

    # Keep newest per ticker+horizon
    latest: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in rows:
        latest[(row["ticker"], row["horizon"])] = row
    return list(latest.values())


def _source_status() -> Dict[str, bool]:
    status = {}
    for key in ["paper_portfolio", "portfolio", "holdings", "positions", "watchlist", "top_picks", "ai_ranking"]:
        try:
            value = st.session_state.get(key)
            status[key] = bool(value)
        except Exception:
            status[key] = False
    return status


def _market_regime_guess(summaries: List[Dict[str, Any]], alerts: List[Dict[str, Any]]) -> str:
    if not summaries:
        return "Ukjent"

    avg_base = sum(x.get("base_pct", 0) for x in summaries) / max(1, len(summaries))
    avg_strength = sum(x.get("strength", 0) for x in summaries) / max(1, len(summaries))
    red_alerts = sum(1 for a in alerts if a.get("level") == "red")

    if red_alerts >= 5:
        return "Stress / høy risiko"
    if avg_base > 2 and avg_strength >= 60:
        return "Bull / positivt"
    if avg_base < -2 or avg_strength < 40:
        return "Bear / svakt"
    return "Nøytralt / blandet"


def _top_rows(summaries: List[Dict[str, Any]], reverse: bool = True, limit: int = 5) -> List[Dict[str, Any]]:
    rows = sorted(summaries, key=lambda r: (r.get("strength", 0), r.get("confidence", 0), r.get("base_pct", 0)), reverse=reverse)
    out = []
    for r in rows[:limit]:
        meta = resolve_security_metadata(r.get("ticker"), r)
        listing = infer_security_listing(r.get("ticker"), r)
        out.append({
            "Ticker": r.get("ticker", ""),
            "Navn": meta.get("name", ""),
            "Land": listing.get("country", ""),
            "Børs": listing.get("exchange", ""),
            "Horisont": r.get("horizon", ""),
            "Base": _safe_pct(r.get("base_pct")),
            "Bull": _safe_pct(r.get("bull_pct")),
            "Bear": _safe_pct(r.get("bear_pct")),
            "Confidence": f"{r.get('confidence', 0)}%",
            "Strength": f"{r.get('strength', 0)}/100",
            "Risiko": r.get("risk", ""),
        })
    return out


def render_market_intelligence_center() -> None:
    """Render top-level AI Market Intelligence Center."""
    alerts = collect_common_alerts(limit=100)
    alert_summary = summarize_alerts(alerts) if alerts else {
        "counts": {"red": 0, "yellow": 0, "green": 0},
        "total": 0,
    }
    summaries = _extract_latest_summaries(limit=300)
    learning = load_learning_stats()
    source_status = _source_status()
    auto_regime_payload = st.session_state.get("market_regime_result_v1840")
    regime = auto_regime_payload.get("label") if isinstance(auto_regime_payload, dict) else _market_regime_guess(summaries, alerts)

    red = int(alert_summary.get("counts", {}).get("red", 0))
    yellow = int(alert_summary.get("counts", {}).get("yellow", 0))
    green = int(alert_summary.get("counts", {}).get("green", 0))
    total_alerts = int(alert_summary.get("total", len(alerts)))

    with st.expander("🧠 AI Market Intelligence Center", expanded=False):
        st.caption("Samlet markedsoversikt basert på prognoser, varsler, portefølje/paper-data og lærende confidence. Ingen auto-trading-kobling.")

        all_tickers = sorted({str(r.get("ticker") or "").upper() for r in summaries if str(r.get("ticker") or "").strip()} | {str(a.get("ticker") or "").upper() for a in alerts if str(a.get("ticker") or "").strip()})
        markets = ["Alle"] + sorted({infer_security_listing(t, {"ticker": t}).get("market", "Ukjent") for t in all_tickers if t})
        horizons = ["Alle"] + sorted({str(r.get("horizon") or "") for r in summaries if str(r.get("horizon") or "").strip()})
        risks = ["Alle"] + sorted({str(r.get("risk") or "Ukjent") for r in summaries if str(r.get("risk") or "").strip()})
        fc1, fc2, fc3, fc4 = st.columns([1.2, .9, .8, .9])
        with fc1:
            ticker_filter = st.selectbox("Ticker", ["Alle"] + all_tickers, key="intelligence_ticker_filter_v1863m")
        with fc2:
            market_filter = st.selectbox("Marked", markets, key="intelligence_market_filter_v1863m")
        with fc3:
            horizon_filter = st.selectbox("Horisont", horizons, key="intelligence_horizon_filter_v1863m")
        with fc4:
            risk_filter = st.selectbox("Risiko", risks, key="intelligence_risk_filter_v1863m")

        filtered_summaries = []
        for row in summaries:
            ticker = str(row.get("ticker") or "").upper()
            if ticker_filter != "Alle" and ticker != ticker_filter:
                continue
            if market_filter != "Alle" and infer_security_listing(ticker, row).get("market") != market_filter:
                continue
            if horizon_filter != "Alle" and str(row.get("horizon") or "") != horizon_filter:
                continue
            if risk_filter != "Alle" and str(row.get("risk") or "Ukjent") != risk_filter:
                continue
            filtered_summaries.append(row)

        filtered_alerts = []
        for alert in alerts:
            ticker = str(alert.get("ticker") or "").upper()
            if ticker_filter != "Alle" and ticker != ticker_filter:
                continue
            if market_filter != "Alle" and infer_security_listing(ticker, alert).get("market") != market_filter:
                continue
            if horizon_filter != "Alle" and str(alert.get("horizon") or "") != horizon_filter:
                continue
            filtered_alerts.append(alert)

        filter_summary = summarize_alerts(filtered_alerts) if filtered_alerts else {"counts": {"red": 0, "yellow": 0, "green": 0}, "total": 0}
        red = int(filter_summary.get("counts", {}).get("red", 0))
        yellow = int(filter_summary.get("counts", {}).get("yellow", 0))
        green = int(filter_summary.get("counts", {}).get("green", 0))
        total_alerts = int(filter_summary.get("total", len(filtered_alerts)))
        regime = auto_regime_payload.get("label") if isinstance(auto_regime_payload, dict) else _market_regime_guess(filtered_summaries, filtered_alerts)
        st.caption(f"Viser {len(filtered_summaries)} av {len(summaries)} prognoser og {len(filtered_alerts)} av {len(alerts)} varsler etter filter.")

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Markedsregime", regime)
        c2.metric("Varsler", total_alerts, f"🔴 {red} · 🟡 {yellow} · 🟢 {green}")
        c3.metric("Prognoser", len(filtered_summaries))
        c4.metric("Learning samples", int(learning.get("global", {}).get("count", 0)))
        active_sources = sum(1 for v in source_status.values() if v)
        c5.metric("Aktive datakilder", active_sources)

        st.markdown("### 🏆 Sterkeste prognoser")
        strong = _top_rows(filtered_summaries, reverse=True, limit=8)
        if strong:
            st.dataframe(strong, use_container_width=True, hide_index=True)
        else:
            st.info("Ingen lagrede prognoser ennå. Kjør prognosemodulen først.")

        st.markdown("### ⚠️ Svakeste / mest risikable prognoser")
        weak = _top_rows(filtered_summaries, reverse=False, limit=8)
        if weak:
            st.dataframe(weak, use_container_width=True, hide_index=True)
        else:
            st.caption("Ingen risikotabell tilgjengelig ennå.")

        st.markdown("### 🚨 Viktigste varsler")
        if filtered_alerts:
            rows = []
            for alert in filtered_alerts[:20]:
                meta = resolve_security_metadata(alert.get("ticker"), alert)
                listing = infer_security_listing(alert.get("ticker"), alert)
                rows.append({
                    "Nivå": alert.get("level", "").upper(),
                    "Kilde": alert.get("source", ""),
                    "Ticker": alert.get("ticker", ""),
                    "Navn": meta.get("name", ""),
                    "Land": listing.get("country", ""),
                    "Børs": listing.get("exchange", ""),
                    "Horisont": alert.get("horizon", ""),
                    "Kategori": alert.get("category", ""),
                    "Melding": alert.get("message", ""),
                })
            st.dataframe(rows, use_container_width=True, hide_index=True)
        else:
            st.success("Ingen aktive varsler.")

        st.markdown("### 📡 Datakilder")
        source_rows = []
        labels = {
            "paper_portfolio": "Paper trading",
            "portfolio": "Portefølje",
            "holdings": "Holdings",
            "positions": "Positions",
            "watchlist": "Watchlist",
            "top_picks": "Top picks",
            "ai_ranking": "AI-ranking",
        }
        for key, active in source_status.items():
            source_rows.append({"Kilde": labels.get(key, key), "Status": "Aktiv" if active else "Ikke funnet"})
        st.dataframe(source_rows, use_container_width=True, hide_index=True)

        st.markdown("### 🧠 Lærende confidence")
        g = learning.get("global", {})
        if g:
            st.write(
                f"Global accuracy: retning {g.get('direction_accuracy', 0)}% · "
                f"innen bull/bear {g.get('inside_band_accuracy', 0)}% · "
                f"snittfeil {g.get('avg_abs_error_pct', 0)}%"
            )
        else:
            st.caption("Lærende confidence har ikke nok historikk ennå.")
