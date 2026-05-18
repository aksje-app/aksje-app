"""
alert_center.py

Felles varselsenter:
- prognosevarsler
- porteføljevarsler
- paper trading/watchlist/ranking-varsler hvis data finnes
- ingen auto-trading-kobling
"""

from __future__ import annotations
import logging

from typing import Any, Dict, List

import streamlit as st

from forecast_store import load_alerts, summarize_alerts
from security_metadata import filter_tickers_for_market, infer_security_listing, market_matches_filter, resolve_security_metadata, standard_market_options


def _level_icon(level: str) -> str:
    level = (level or "").lower()
    if level == "red":
        return "🔴"
    if level == "yellow":
        return "🟡"
    if level == "green":
        return "🟢"
    return "⚪"


def _normalize_alert(alert: Dict[str, Any], source: str = "Prognose") -> Dict[str, Any]:
    row = dict(alert)
    row.setdefault("source", source)
    row.setdefault("level", "yellow")
    row.setdefault("category", "varsel")
    row.setdefault("ticker", "")
    row.setdefault("horizon", "")
    row.setdefault("message", "")
    return row


def _category_label(category: Any) -> str:
    labels = {
        "manual_event_risk": "Hendelsesrisiko",
        "good_reward_risk": "God reward/risk",
        "strong_opportunity": "Sterk mulighet",
        "source_active": "Datakilde aktiv",
        "weak_forecast": "Svak prognose",
        "bear_risk": "Bear-risiko",
    }
    raw = str(category or "varsel")
    return labels.get(raw, raw.replace("_", " ").strip().title())


def _alert_market(alert: Dict[str, Any]) -> str:
    return infer_security_listing(alert.get("ticker"), alert).get("market", "Ukjent")


def collect_common_alerts(limit: int = 100) -> List[Dict[str, Any]]:
    """Collect alerts from forecast log and simple app-state sources."""
    alerts: List[Dict[str, Any]] = []

    try:
        for alert in load_alerts(limit=limit):
            alerts.append(_normalize_alert(alert, source="Prognose"))
    except Exception as e:
        logging.warning("Silenced exception restored in v18.6.3: %s", e)

    try:
        for key, source in [
            ("paper_portfolio", "Paper trading"),
            ("portfolio", "Portefølje"),
            ("holdings", "Portefølje"),
            ("positions", "Portefølje"),
            ("watchlist", "Watchlist"),
            ("top_picks", "AI-ranking"),
            ("ai_ranking", "AI-ranking"),
        ]:
            if key not in st.session_state:
                continue
            value = st.session_state.get(key)
            blob = str(value)
            if not blob or blob in ("{}", "[]", "None"):
                continue
            alerts.append(_normalize_alert({
                "level": "green",
                "category": "source_active",
                "ticker": "",
                "horizon": "",
                "message": f"{source} er tilgjengelig for prognose-/risikovarsler.",
            }, source=source))
    except Exception as e:
        logging.warning("Silenced exception restored in v18.6.3: %s", e)

    seen = set()
    deduped: List[Dict[str, Any]] = []
    priority = {"red": 3, "yellow": 2, "green": 1}
    for alert in alerts:
        key = (
            alert.get("source"),
            alert.get("level"),
            alert.get("ticker"),
            alert.get("horizon"),
            alert.get("category"),
            alert.get("message"),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(alert)

    deduped.sort(key=lambda a: priority.get((a.get("level") or "").lower(), 0), reverse=True)
    return deduped[:limit]


def render_common_alert_center(location: str = "top") -> None:
    """Render one common alert center for the whole app."""
    alerts = collect_common_alerts(limit=100)
    summary = summarize_alerts(alerts) if alerts else {
        "counts": {"red": 0, "yellow": 0, "green": 0},
        "total": 0,
        "top_level": "green",
    }

    counts = summary.get("counts", {})
    red = int(counts.get("red", 0))
    yellow = int(counts.get("yellow", 0))
    green = int(counts.get("green", 0))
    total = int(summary.get("total", len(alerts)))

    if total == 0:
        st.info("🟢 Varselsenter: Ingen aktive prognose-/porteføljevarsler.")
        return

    headline = f"🚨 Varselsenter · 🔴 {red} · 🟡 {yellow} · 🟢 {green}"

    with st.expander(headline, expanded=(red > 0)):
        st.caption("Felles varsler fra prognose, portefølje, paper trading, watchlist og ranking der data finnes. Dette er beslutningsstøtte, ikke ordre.")

        raw_tickers = sorted({str(a.get("ticker") or "").upper() for a in alerts if str(a.get("ticker") or "").strip()})
        source_values = ["Alle"] + sorted({str(a.get("source") or "Ukjent") for a in alerts})
        horizon_values = ["Alle"] + sorted({str(a.get("horizon") or "") for a in alerts if str(a.get("horizon") or "").strip()})
        market_values = standard_market_options(include_sources=True)

        f1, f2, f3, f4, f5 = st.columns([1.15, .9, .8, .9, .9])
        with f1:
            market_filter = st.selectbox("Marked", market_values, key=f"alert_market_filter_{location}_v1863m")
        ticker_values = filter_tickers_for_market(raw_tickers, market_filter)
        with f2:
            ticker_filter = st.selectbox("Ticker", ["Alle"] + ticker_values, key=f"alert_ticker_filter_{location}_v1863n")
        with f3:
            level_filter = st.selectbox("Nivå", ["Alle", "Rød", "Gul", "Grønn"], key=f"alert_level_filter_{location}_v1863m")
        with f4:
            source_filter = st.selectbox("Kilde", source_values, key=f"alert_source_filter_{location}_v1863m")
        with f5:
            horizon_filter = st.selectbox("Horisont", horizon_values, key=f"alert_horizon_filter_{location}_v1863m")

        level_lookup = {"Rød": "red", "Gul": "yellow", "Grønn": "green"}
        filtered_alerts = []
        for alert in alerts:
            ticker = str(alert.get("ticker") or "").upper()
            if ticker_filter != "Alle" and ticker != ticker_filter:
                continue
            if not market_matches_filter(ticker, market_filter, alert):
                continue
            if level_filter != "Alle" and str(alert.get("level") or "").lower() != level_lookup.get(level_filter):
                continue
            if source_filter != "Alle" and str(alert.get("source") or "Ukjent") != source_filter:
                continue
            if horizon_filter != "Alle" and str(alert.get("horizon") or "") != horizon_filter:
                continue
            filtered_alerts.append(alert)

        st.caption(f"Viser {len(filtered_alerts)} av {len(alerts)} varsler etter filter.")

        by_source: Dict[str, int] = {}
        for alert in filtered_alerts:
            src = alert.get("source", "Ukjent")
            by_source[src] = by_source.get(src, 0) + 1

        if by_source:
            st.write("Kilder:")
            st.write(" · ".join([f"{src}: {count}" for src, count in sorted(by_source.items())]))

        rows = []
        for alert in filtered_alerts[:80]:
            meta = resolve_security_metadata(alert.get("ticker"), alert)
            listing = infer_security_listing(alert.get("ticker"), alert)
            rows.append({
                "Nivå": f"{_level_icon(alert.get('level'))} {alert.get('level', '').upper()}",
                "Kilde": alert.get("source", ""),
                "Ticker": alert.get("ticker", ""),
                "Navn": meta.get("name", ""),
                "Land": listing.get("country", ""),
                "Børs": listing.get("exchange", ""),
                "Horisont": alert.get("horizon", ""),
                "Kategori": _category_label(alert.get("category", "")),
                "Melding": alert.get("message", ""),
            })

        if rows:
            st.dataframe(rows, use_container_width=True, hide_index=True)
        else:
            st.info("Ingen varsler matcher valgte filter.")
